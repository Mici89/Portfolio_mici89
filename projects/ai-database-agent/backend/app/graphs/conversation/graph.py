from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agents.database_action import ConversationIntentRouter
from app.core.exceptions import AuthorizationError
from app.models import (
    ConversationContextResolution,
    ConversationMessageResponse,
    ConversationRoutingDecision,
    QuerySession,
    UserPrincipal,
)
from app.services.conversation_context import ConversationContextMerger
from app.services.database_action import DatabaseActionService
from app.services.query_session import QuerySessionService

from .state import ConversationGraphState


class ConversationGraphRunner:
    """Parent graph that owns routing, context merge, and sub-workflow dispatch."""

    def __init__(
        self,
        router: ConversationIntentRouter,
        context_merger: ConversationContextMerger,
        query_session_service: QuerySessionService,
        database_action_service: DatabaseActionService,
        checkpoint_path: Path,
    ) -> None:
        self.router = router
        self.context_merger = context_merger
        self.query_session_service = query_session_service
        self.database_action_service = database_action_service
        self.checkpoint_path = checkpoint_path

    async def run(
        self,
        *,
        workflow_id: str,
        session_id: str,
        message: str,
        principal: UserPrincipal,
    ) -> ConversationMessageResponse:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(
            str(self.checkpoint_path)
        ) as checkpointer:
            await checkpointer.setup()
            graph = self._build_graph().compile(
                checkpointer=checkpointer,
                name="conversation-parent-graph",
            )
            final_state = await graph.ainvoke(
                {
                    "workflow_id": workflow_id,
                    "session_id": session_id,
                    "message": message,
                    "principal": principal.model_dump(mode="json"),
                },
                config={
                    "configurable": {"thread_id": workflow_id},
                    "recursion_limit": 12,
                },
            )
        return ConversationMessageResponse.model_validate(
            final_state["response"]
        )

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(ConversationGraphState)
        graph.add_node("load_conversation_session", self._load_session)
        graph.add_node("route_conversation_intent", self._route_intent)
        graph.add_node("merge_conversation_context", self._merge_context)
        graph.add_node("query_subgraph", self._run_query)
        graph.add_node("action_subgraph", self._run_action)
        graph.add_edge(START, "load_conversation_session")
        graph.add_edge(
            "load_conversation_session",
            "route_conversation_intent",
        )
        graph.add_edge(
            "route_conversation_intent",
            "merge_conversation_context",
        )
        graph.add_conditional_edges(
            "merge_conversation_context",
            self._route_workflow,
            {
                "query": "query_subgraph",
                "action": "action_subgraph",
            },
        )
        graph.add_edge("query_subgraph", END)
        graph.add_edge("action_subgraph", END)
        return graph

    async def _load_session(
        self,
        state: ConversationGraphState,
    ) -> dict[str, Any]:
        session = await self.query_session_service.get(state["session_id"])
        return {"session": session.model_dump(mode="json")}

    async def _route_intent(
        self,
        state: ConversationGraphState,
    ) -> dict[str, Any]:
        session = QuerySession.model_validate(state["session"])
        routing = await self.router.route(
            state["message"], QuerySessionService.conversation_context(session)
        )
        return {"routing": routing.model_dump(mode="json")}

    async def _merge_context(
        self,
        state: ConversationGraphState,
    ) -> dict[str, Any]:
        session = QuerySession.model_validate(state["session"])
        routing = ConversationRoutingDecision.model_validate(
            state["routing"]
        )
        resolution = self.context_merger.resolve(
            routing,
            session.current_intent,
        )
        return {
            "context_resolution": resolution.model_dump(mode="json")
        }

    async def _run_query(
        self,
        state: ConversationGraphState,
    ) -> dict[str, Any]:
        routing = ConversationRoutingDecision.model_validate(
            state["routing"]
        )
        resolution = ConversationContextResolution.model_validate(
            state["context_resolution"]
        )
        query = await self.query_session_service.add_turn(
            state["session_id"],
            state["message"],
            context_resolution=resolution,
        )
        response = ConversationMessageResponse(
            kind="query",
            routing=routing,
            query=query,
            workflow_engine="langgraph",
            workflow_thread_id=state["workflow_id"],
        )
        return {"response": response.model_dump(mode="json")}

    async def _run_action(
        self,
        state: ConversationGraphState,
    ) -> dict[str, Any]:
        principal = UserPrincipal.model_validate(state["principal"])
        if principal.role != "database_operator":
            raise AuthorizationError(
                "数据库写操作需要数据库操作员登录后才能生成和执行"
            )
        session = QuerySession.model_validate(state["session"])
        routing = ConversationRoutingDecision.model_validate(
            state["routing"]
        )
        resolution = ConversationContextResolution.model_validate(
            state["context_resolution"]
        )
        action = await self.database_action_service.plan(
            state["session_id"],
            state["message"],
            principal,
            self._action_context(session, resolution),
        )
        response = ConversationMessageResponse(
            kind="action",
            routing=routing,
            action=action,
            workflow_engine="langgraph",
            workflow_thread_id=state["workflow_id"],
        )
        return {"response": response.model_dump(mode="json")}

    @staticmethod
    def _route_workflow(
        state: ConversationGraphState,
    ) -> Literal["query", "action"]:
        routing = ConversationRoutingDecision.model_validate(
            state["routing"]
        )
        return routing.kind

    @staticmethod
    def _action_context(
        session: QuerySession,
        resolution: ConversationContextResolution,
    ) -> dict[str, object]:
        return QuerySessionService.conversation_context(session, resolution) or {
            "context_resolution": resolution.model_dump(mode="json")
        }
