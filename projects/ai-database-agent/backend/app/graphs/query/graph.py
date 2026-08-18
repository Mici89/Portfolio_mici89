from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.adapters.database import DatabaseAdapterFactory
from app.agents.database_query import DatabaseQueryAgent
from app.agents.database_query.agent import DatabaseQueryExecution
from app.agents.sql_execution import SQLExecutionAgent
from app.graphs.workflow import inspect_workflow, workflow_config
from app.models import (
    DatabaseSnapshot,
    GeneratedSqlQuery,
    LLMTokenUsage,
    QueryAttempt,
    QueryExplanation,
    QueryPlan,
    QueryResultAssessment,
    QuerySemanticSource,
    SqlExecutionResult,
    WorkflowStatus,
)
from app.services.database_connection import DatabaseConnectionService
from app.services.effective_semantics import EffectiveSemanticContext

from .state import QueryGraphState


class QueryGraphRunner:
    """Durable LangGraph orchestration for the read-only query workflow."""

    def __init__(
        self,
        agent: DatabaseQueryAgent,
        checkpoint_path: Path,
        connection_service: DatabaseConnectionService | None = None,
        adapter_factory: DatabaseAdapterFactory | None = None,
    ) -> None:
        self.agent = agent
        self.checkpoint_path = checkpoint_path
        self.connection_service = connection_service
        self.adapter_factory = adapter_factory

    async def run(
        self,
        *,
        query_id: str,
        snapshot: DatabaseSnapshot,
        question: str,
        semantics: EffectiveSemanticContext,
        conversation_context: dict[str, object] | None,
    ) -> DatabaseQueryExecution:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        initial_state = self._initial_state(
            query_id,
            snapshot,
            question,
            semantics,
            conversation_context,
        )
        async with AsyncSqliteSaver.from_conn_string(
            str(self.checkpoint_path)
        ) as checkpointer:
            await checkpointer.setup()
            graph = self._build_graph().compile(
                checkpointer=checkpointer,
                name="database-query-graph",
            )
            final_state = await graph.ainvoke(
                initial_state,
                config=workflow_config(
                    query_id,
                    recursion_limit=self.agent.max_attempts * 5 + 10,
                ),
            )
        return self._execution_from_state(final_state)

    async def status(self, query_id: str) -> WorkflowStatus:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(
            str(self.checkpoint_path)
        ) as checkpointer:
            await checkpointer.setup()
            graph = self._build_graph().compile(
                checkpointer=checkpointer,
                name="database-query-graph",
            )
            return await inspect_workflow(
                graph,
                workflow_id=query_id,
                workflow_kind="query",
            )

    async def resume(
        self,
        query_id: str,
    ) -> tuple[DatabaseQueryExecution, DatabaseSnapshot, str]:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(
            str(self.checkpoint_path)
        ) as checkpointer:
            await checkpointer.setup()
            graph = self._build_graph().compile(
                checkpointer=checkpointer,
                name="database-query-graph",
            )
            final_state = await graph.ainvoke(
                None,
                config=workflow_config(
                    query_id,
                    recursion_limit=self.agent.max_attempts * 5 + 10,
                ),
            )
        return (
            self._execution_from_state(final_state),
            DatabaseSnapshot.model_validate(final_state["snapshot"]),
            str(final_state["question"]),
        )

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(QueryGraphState)
        graph.add_node("plan_query", self._plan_query)
        graph.add_node("execute_select", self._execute_select)
        graph.add_node("record_execution_failure", self._record_execution_failure)
        graph.add_node("assess_result", self._assess_result)
        graph.add_node("prepare_replan", self._prepare_replan)
        graph.add_node("explain_result", self._explain_result)
        graph.add_node("finalize_failure", self._finalize_failure)
        graph.add_edge(START, "plan_query")
        graph.add_edge("plan_query", "execute_select")
        graph.add_conditional_edges(
            "execute_select",
            self._route_after_execution,
            {
                "assess": "assess_result",
                "failure": "record_execution_failure",
            },
        )
        graph.add_conditional_edges(
            "record_execution_failure",
            self._route_after_failure,
            {
                "retry": "plan_query",
                "finish": "finalize_failure",
            },
        )
        graph.add_conditional_edges(
            "assess_result",
            self._route_after_assessment,
            {
                "replan": "prepare_replan",
                "explain": "explain_result",
            },
        )
        graph.add_edge("prepare_replan", "plan_query")
        graph.add_edge("explain_result", END)
        graph.add_edge("finalize_failure", END)
        return graph

    async def _plan_query(self, state: QueryGraphState) -> dict[str, Any]:
        snapshot = DatabaseSnapshot.model_validate(state["snapshot"])
        plan, provider, model, plan_usage = await self.agent.plan_once(
            snapshot,
            state["question"],
            state["semantic_payload"],
            self._field_map(state["field_sources"]),
            self._field_map(state["field_meanings"]),
            state.get("repair_context"),
            state.get("conversation_context"),
        )
        usage = self.agent.add_usage(
            LLMTokenUsage.model_validate(state["usage"]),
            plan_usage,
        )
        return {
            "plan": plan.model_dump(mode="json"),
            "provider": provider,
            "model": model,
            "usage": usage.model_dump(mode="json"),
        }

    async def _execute_select(self, state: QueryGraphState) -> dict[str, Any]:
        plan = QueryPlan.model_validate(state["plan"])
        execution_agent = await self._execution_agent(
            DatabaseSnapshot.model_validate(state["snapshot"])
        )
        result = await execution_agent.execute(
            GeneratedSqlQuery(
                request_index=0,
                purpose=plan.sql_purpose,
                sql=plan.sql,
            )
        )
        return {"result": result.model_dump(mode="json")}

    async def _record_execution_failure(
        self,
        state: QueryGraphState,
    ) -> dict[str, Any]:
        plan = QueryPlan.model_validate(state["plan"])
        result = SqlExecutionResult.model_validate(state["result"])
        assessment = QueryResultAssessment(
            verdict="replan",
            confidence=1,
            reason=result.error or "SQL执行失败",
            issues=[result.error or "SQL执行失败"],
            next_action="根据数据库错误修正SQL并重新执行。",
        )
        attempts = self._attempts(state)
        attempts.append(
            QueryAttempt(
                attempt_number=state["attempt_number"],
                plan=plan,
                result=result,
                assessment=assessment,
            )
        )
        retry = state["attempt_number"] < state["max_attempts"]
        return {
            "attempts": [attempt.model_dump(mode="json") for attempt in attempts],
            "assessment": assessment.model_dump(mode="json"),
            "repair_context": {
                "attempt_history": self.agent.attempt_history(attempts),
                "previous_sql": plan.sql,
                "execution_status": result.status,
                "database_error": result.error,
                "instruction": assessment.next_action,
            },
            "attempt_number": state["attempt_number"] + (1 if retry else 0),
            "next_step": "retry" if retry else "finish",
        }

    async def _assess_result(self, state: QueryGraphState) -> dict[str, Any]:
        plan = QueryPlan.model_validate(state["plan"])
        result = SqlExecutionResult.model_validate(state["result"])
        attempts = self._attempts(state)
        assessment, assessment_usage = await self.agent.assess_result(
            state["question"],
            plan,
            result.model_dump(mode="json"),
            attempts,
            state.get("conversation_context"),
        )
        attempts.append(
            QueryAttempt(
                attempt_number=state["attempt_number"],
                plan=plan,
                result=result,
                assessment=assessment,
            )
        )
        usage = self.agent.add_usage(
            LLMTokenUsage.model_validate(state["usage"]),
            assessment_usage,
        )
        return {
            "attempts": [attempt.model_dump(mode="json") for attempt in attempts],
            "assessment": assessment.model_dump(mode="json"),
            "usage": usage.model_dump(mode="json"),
        }

    async def _prepare_replan(self, state: QueryGraphState) -> dict[str, Any]:
        attempts = self._attempts(state)
        assessment = QueryResultAssessment.model_validate(state["assessment"])
        return {
            "repair_context": self.agent.result_repair_context(
                attempts,
                assessment,
            ),
            "attempt_number": state["attempt_number"] + 1,
        }

    async def _explain_result(self, state: QueryGraphState) -> dict[str, Any]:
        plan = QueryPlan.model_validate(state["plan"])
        result = SqlExecutionResult.model_validate(state["result"])
        used_sources = self._used_sources(state, plan)
        explanation, explanation_usage = await self.agent.explain_result(
            state["question"],
            plan,
            result.model_dump(mode="json"),
            used_sources,
            state.get("conversation_context"),
        )
        assessment = QueryResultAssessment.model_validate(state["assessment"])
        if assessment.verdict == "replan":
            explanation = explanation.model_copy(
                update={
                    "limitations": [
                        *explanation.limitations,
                        (
                            f"查询闭环已达到{state['max_attempts']}轮上限："
                            f"{assessment.reason}"
                        ),
                    ]
                }
            )
        usage = self.agent.add_usage(
            LLMTokenUsage.model_validate(state["usage"]),
            explanation_usage,
        )
        return {
            "explanation": explanation.model_dump(mode="json"),
            "usage": usage.model_dump(mode="json"),
            "used_semantic_sources": [
                source.model_dump(mode="json") for source in used_sources
            ],
            "next_step": "finish",
        }

    async def _finalize_failure(self, state: QueryGraphState) -> dict[str, Any]:
        attempts = self._attempts(state)
        last_result = attempts[-1].result
        used_tables = set(attempts[-1].plan.intent.tables)
        sources = [
            source
            for source in self._semantic_sources(state)
            if source.table_name in used_tables
        ]
        explanation = QueryExplanation(
            answer="查询未能成功执行。",
            observations=[],
            data_scope="没有返回可解释的查询结果。",
            limitations=[last_result.error or "SQL执行失败"],
        )
        return {
            "explanation": explanation.model_dump(mode="json"),
            "used_semantic_sources": [
                source.model_dump(mode="json") for source in sources
            ],
            "next_step": "finish",
        }

    async def _execution_agent(
        self,
        snapshot: DatabaseSnapshot,
    ) -> SQLExecutionAgent:
        if self.agent.sql_execution_agent is not None:
            return self.agent.sql_execution_agent
        if self.connection_service is None or self.adapter_factory is None:
            raise RuntimeError("Query Graph没有可用的数据库执行Adapter")
        config = await self.connection_service.resolve_snapshot(snapshot)
        return SQLExecutionAgent(
            self.adapter_factory.create(config),
            max_rows=100,
        )

    @staticmethod
    def _route_after_execution(
        state: QueryGraphState,
    ) -> Literal["assess", "failure"]:
        return (
            "assess"
            if SqlExecutionResult.model_validate(state["result"]).status == "executed"
            else "failure"
        )

    @staticmethod
    def _route_after_failure(
        state: QueryGraphState,
    ) -> Literal["retry", "finish"]:
        return "retry" if state["next_step"] == "retry" else "finish"

    @staticmethod
    def _route_after_assessment(
        state: QueryGraphState,
    ) -> Literal["replan", "explain"]:
        assessment = QueryResultAssessment.model_validate(state["assessment"])
        if (
            assessment.verdict == "replan"
            and state["attempt_number"] < state["max_attempts"]
        ):
            return "replan"
        return "explain"

    def _initial_state(
        self,
        query_id: str,
        snapshot: DatabaseSnapshot,
        question: str,
        semantics: EffectiveSemanticContext,
        conversation_context: dict[str, object] | None,
    ) -> QueryGraphState:
        return {
            "query_id": query_id,
            "snapshot": snapshot.model_dump(mode="json"),
            "question": question,
            "conversation_context": conversation_context,
            "semantic_payload": semantics.payload,
            "semantic_sources": [
                source.model_dump(mode="json") for source in semantics.sources
            ],
            "field_sources": self._serialize_field_map(semantics.field_sources),
            "field_meanings": self._serialize_field_map(semantics.field_meanings),
            "attempts": [],
            "attempt_number": 1,
            "max_attempts": self.agent.max_attempts,
            "repair_context": None,
            "provider": "",
            "model": "",
            "usage": LLMTokenUsage().model_dump(mode="json"),
        }

    @staticmethod
    def _serialize_field_map(
        values: dict[tuple[str, str], str],
    ) -> list[dict[str, str]]:
        return [
            {"table_name": key[0], "column_name": key[1], "value": value}
            for key, value in sorted(values.items())
        ]

    @staticmethod
    def _field_map(values: list[dict[str, str]]) -> dict[tuple[str, str], str]:
        return {
            (item["table_name"], item["column_name"]): item["value"]
            for item in values
        }

    @staticmethod
    def _attempts(state: QueryGraphState) -> list[QueryAttempt]:
        return [
            QueryAttempt.model_validate(attempt)
            for attempt in state.get("attempts", [])
        ]

    @staticmethod
    def _semantic_sources(state: QueryGraphState) -> list[QuerySemanticSource]:
        return [
            QuerySemanticSource.model_validate(source)
            for source in state["semantic_sources"]
        ]

    def _used_sources(
        self,
        state: QueryGraphState,
        plan: QueryPlan,
    ) -> list[QuerySemanticSource]:
        return [
            source
            for source in self._semantic_sources(state)
            if source.table_name in plan.intent.tables
        ]

    @staticmethod
    def _execution_from_state(state: QueryGraphState) -> DatabaseQueryExecution:
        return DatabaseQueryExecution(
            attempts=[
                QueryAttempt.model_validate(attempt)
                for attempt in state["attempts"]
            ],
            explanation=QueryExplanation.model_validate(state["explanation"]),
            semantic_sources=[
                QuerySemanticSource.model_validate(source)
                for source in state.get("used_semantic_sources", [])
            ],
            provider=state["provider"],
            model=state["model"],
            usage=LLMTokenUsage.model_validate(state["usage"]),
        )
