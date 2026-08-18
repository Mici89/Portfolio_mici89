from datetime import UTC, datetime
from uuid import uuid4

from app.agents.database_action import ConversationIntentRouter
from app.graphs.conversation import ConversationGraphRunner
from app.models import (
    ConversationContextResolution,
    ConversationMessageResponse,
    QuerySession,
    UserPrincipal,
)
from app.services.conversation_context import ConversationContextMerger
from app.services.database_action import DatabaseActionService
from app.services.query_session import QuerySessionService


class ConversationService:
    def __init__(
        self,
        router: ConversationIntentRouter,
        context_merger: ConversationContextMerger,
        query_session_service: QuerySessionService,
        database_action_service: DatabaseActionService,
        graph_runner: ConversationGraphRunner | None = None,
    ) -> None:
        self.router = router
        self.context_merger = context_merger
        self.query_session_service = query_session_service
        self.database_action_service = database_action_service
        self.graph_runner = graph_runner

    async def send(
        self,
        session_id: str,
        message: str,
        principal: UserPrincipal,
    ) -> ConversationMessageResponse:
        if self.graph_runner is not None:
            return await self.graph_runner.run(
                workflow_id=self._new_workflow_id(),
                session_id=session_id,
                message=message,
                principal=principal,
            )
        session = await self.query_session_service.get(session_id)
        routing = await self.router.route(
            message, QuerySessionService.conversation_context(session)
        )
        resolution = self.context_merger.resolve(routing, session.current_intent)
        if routing.kind == "action":
            if principal is None or principal.role != "database_operator":
                from app.core.exceptions import AuthorizationError

                raise AuthorizationError("数据库写操作需要数据库操作员登录后才能生成和执行")
            action_context = self._action_context(session, resolution)
            action = await self.database_action_service.plan(
                session_id,
                message,
                principal,
                action_context,
            )
            return ConversationMessageResponse(
                kind="action",
                routing=routing,
                action=action,
            )
        query = await self.query_session_service.add_turn(
            session_id,
            message,
            context_resolution=resolution,
        )
        return ConversationMessageResponse(
            kind="query",
            routing=routing,
            query=query,
        )

    @staticmethod
    def _new_workflow_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return f"conversation_{timestamp}_{uuid4().hex[:8]}"

    @staticmethod
    def _action_context(
        session: QuerySession,
        resolution: ConversationContextResolution,
    ) -> dict[str, object]:
        return QuerySessionService.conversation_context(session, resolution) or {
            "context_resolution": resolution.model_dump(mode="json")
        }
