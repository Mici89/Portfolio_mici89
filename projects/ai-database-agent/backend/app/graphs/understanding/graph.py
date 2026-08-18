import asyncio
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.adapters.database import DatabaseAdapterFactory
from app.agents.database_understanding import (
    DatabaseUnderstandingAgent,
    TableUnderstandingExecution,
)
from app.agents.sql_execution import SQLExecutionAgent
from app.graphs.workflow import inspect_workflow, workflow_config
from app.models import (
    DatabaseSnapshot,
    EvidenceRequest,
    EvidenceStep,
    GeneratedSqlQuery,
    LLMTokenUsage,
    TableUnderstandingPayload,
    WorkflowStatus,
)
from app.services.database_connection import DatabaseConnectionService

from .state import UnderstandingGraphState


class UnderstandingGraphRunner:
    """LangGraph orchestration for iterative schema understanding and evidence."""

    def __init__(
        self,
        agent: DatabaseUnderstandingAgent,
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
        run_id: str,
        snapshot: DatabaseSnapshot,
        table_name: str,
        sql_execution_agent: SQLExecutionAgent | None = None,
    ) -> TableUnderstandingExecution:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        execution_agent = sql_execution_agent or await self._execution_agent(snapshot)
        graph = self._build_graph(execution_agent)
        async with AsyncSqliteSaver.from_conn_string(
            str(self.checkpoint_path)
        ) as checkpointer:
            await checkpointer.setup()
            compiled = graph.compile(
                checkpointer=checkpointer,
                name="database-understanding-graph",
            )
            final_state = await compiled.ainvoke(
                self._initial_state(run_id, snapshot, table_name),
                config=workflow_config(
                    run_id,
                    recursion_limit=self.agent.max_evidence_rounds * 4 + 10,
                ),
            )
        return self._execution_from_state(final_state)

    async def status(self, run_id: str) -> WorkflowStatus:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(
            str(self.checkpoint_path)
        ) as checkpointer:
            await checkpointer.setup()
            graph = self._build_graph(None).compile(
                checkpointer=checkpointer,
                name="database-understanding-graph",
            )
            return await inspect_workflow(
                graph,
                workflow_id=run_id,
                workflow_kind="understanding",
            )

    async def resume(
        self,
        run_id: str,
    ) -> tuple[TableUnderstandingExecution, DatabaseSnapshot, str]:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(
            str(self.checkpoint_path)
        ) as checkpointer:
            await checkpointer.setup()
            inspection_graph = self._build_graph(None).compile(
                checkpointer=checkpointer,
                name="database-understanding-graph",
            )
            checkpoint = await inspection_graph.aget_state(
                workflow_config(run_id)
            )
            snapshot = DatabaseSnapshot.model_validate(
                checkpoint.values["snapshot"]
            )
            execution_agent = await self._execution_agent(snapshot)
            graph = self._build_graph(execution_agent).compile(
                checkpointer=checkpointer,
                name="database-understanding-graph",
            )
            final_state = await graph.ainvoke(
                None,
                config=workflow_config(
                    run_id,
                    recursion_limit=self.agent.max_evidence_rounds * 4 + 10,
                ),
            )
        return (
            self._execution_from_state(final_state),
            snapshot,
            str(final_state["table_name"]),
        )

    def _build_graph(
        self,
        execution_agent: SQLExecutionAgent | None,
    ) -> StateGraph:
        async def execute_evidence_sql(
            state: UnderstandingGraphState,
        ) -> dict[str, Any]:
            return await self._execute_sql(state, execution_agent)

        async def finalize_understanding(
            state: UnderstandingGraphState,
        ) -> dict[str, Any]:
            return await self._finalize(state, execution_agent)

        graph = StateGraph(UnderstandingGraphState)
        graph.add_node("analyze_schema_and_evidence", self._analyze)
        graph.add_node("generate_evidence_sql", self._generate_sql)
        graph.add_node("execute_evidence_sql", execute_evidence_sql)
        graph.add_node("finalize_understanding", finalize_understanding)
        graph.add_edge(START, "analyze_schema_and_evidence")
        graph.add_conditional_edges(
            "analyze_schema_and_evidence",
            lambda state: self._route_after_analysis(state, execution_agent),
            {
                "generate": "generate_evidence_sql",
                "finalize": "finalize_understanding",
            },
        )
        graph.add_conditional_edges(
            "generate_evidence_sql",
            self._route_after_generation,
            {
                "execute": "execute_evidence_sql",
                "finalize": "finalize_understanding",
            },
        )
        graph.add_edge("execute_evidence_sql", "analyze_schema_and_evidence")
        graph.add_edge("finalize_understanding", END)
        return graph

    async def _analyze(
        self,
        state: UnderstandingGraphState,
    ) -> dict[str, Any]:
        snapshot = DatabaseSnapshot.model_validate(state["snapshot"])
        steps = [
            EvidenceStep.model_validate(item)
            for item in state.get("evidence_steps", [])
        ]
        context = self.agent.context_builder.build(
            snapshot,
            state["table_name"],
            steps,
            state["max_evidence_rounds"],
        )
        analysis, provider, model, round_usage = await self.agent.analyze_once(
            snapshot,
            state["table_name"],
            context,
        )
        usage = self.agent.add_usage(
            LLMTokenUsage.model_validate(state["usage"]),
            round_usage,
        )
        return {
            "analysis": analysis.model_dump(mode="json"),
            "pending_requests": [
                request.model_dump(mode="json")
                for request in analysis.evidence_requests
            ],
            "provider": provider,
            "model": model,
            "usage": usage.model_dump(mode="json"),
        }

    async def _generate_sql(
        self,
        state: UnderstandingGraphState,
    ) -> dict[str, Any]:
        assert self.agent.sql_generation_agent is not None
        requests = self._requests(state)
        generation = await self.agent.sql_generation_agent.generate(
            DatabaseSnapshot.model_validate(state["snapshot"]),
            state["table_name"],
            requests,
        )
        usage = self.agent.add_usage(
            LLMTokenUsage.model_validate(state["usage"]),
            generation.usage,
        )
        queries = [
            query.model_dump(mode="json")
            for query in generation.plan.queries
        ]
        return {
            "generated_queries": queries,
            "usage": usage.model_dump(mode="json"),
            "termination_reason": (
                "" if queries else "sql_generation_stalled"
            ),
        }

    async def _execute_sql(
        self,
        state: UnderstandingGraphState,
        execution_agent: SQLExecutionAgent | None,
    ) -> dict[str, Any]:
        assert execution_agent is not None
        requests = self._requests(state)
        queries = [
            GeneratedSqlQuery.model_validate(item)
            for item in state["generated_queries"]
        ]
        results = await asyncio.gather(
            *[execution_agent.execute(query) for query in queries]
        )
        round_number = state["evidence_round_count"] + 1
        steps = [
            EvidenceStep.model_validate(item)
            for item in state.get("evidence_steps", [])
        ]
        steps.extend(
            EvidenceStep(
                round_number=round_number,
                request=requests[query.request_index],
                query=query,
                result=result,
            )
            for query, result in zip(queries, results, strict=True)
        )
        return {
            "evidence_steps": [
                step.model_dump(mode="json") for step in steps
            ],
            "evidence_round_count": round_number,
            "generated_queries": [],
        }

    async def _finalize(
        self,
        state: UnderstandingGraphState,
        execution_agent: SQLExecutionAgent | None,
    ) -> dict[str, Any]:
        analysis = TableUnderstandingPayload.model_validate(state["analysis"])
        deferred = list(analysis.evidence_requests)
        reason = state.get("termination_reason") or self._termination_reason(
            state,
            execution_agent,
        )
        completion_status = "best_effort" if deferred else "completed"
        if deferred:
            analysis = analysis.model_copy(
                update={
                    "evidence_requests": [],
                    "limitations": [
                        *analysis.limitations,
                        self.agent.termination_limitation(reason),
                    ][:8],
                }
            )
        return {
            "analysis": analysis.model_dump(mode="json"),
            "completion_status": completion_status,
            "termination_reason": reason,
            "deferred_evidence_requests": [
                request.model_dump(mode="json") for request in deferred
            ],
            "evidence_scope": (
                "schema_and_query_evidence"
                if state.get("evidence_steps")
                else "schema_only"
            ),
        }

    def _route_after_analysis(
        self,
        state: UnderstandingGraphState,
        execution_agent: SQLExecutionAgent | None,
    ) -> Literal["generate", "finalize"]:
        if not self._requests(state):
            return "finalize"
        if (
            self.agent.sql_generation_agent is None
            or execution_agent is None
        ):
            return "finalize"
        if state["evidence_round_count"] >= state["max_evidence_rounds"]:
            return "finalize"
        return "generate"

    @staticmethod
    def _route_after_generation(
        state: UnderstandingGraphState,
    ) -> Literal["execute", "finalize"]:
        return "execute" if state.get("generated_queries") else "finalize"

    def _termination_reason(
        self,
        state: UnderstandingGraphState,
        execution_agent: SQLExecutionAgent | None,
    ) -> str:
        if self._requests(state):
            if (
                self.agent.sql_generation_agent is None
                or execution_agent is None
            ):
                return "evidence_loop_unavailable"
            if state["evidence_round_count"] >= state["max_evidence_rounds"]:
                return "round_limit_reached"
        return (
            "evidence_resolved"
            if state.get("evidence_steps")
            else "schema_sufficient"
        )

    async def _execution_agent(
        self,
        snapshot: DatabaseSnapshot,
    ) -> SQLExecutionAgent | None:
        if self.agent.sql_execution_agent is not None:
            return self.agent.sql_execution_agent
        if self.connection_service is None or self.adapter_factory is None:
            return None
        config = await self.connection_service.resolve_snapshot(snapshot)
        return SQLExecutionAgent(
            self.adapter_factory.create(config),
            max_rows=50,
        )

    def _initial_state(
        self,
        run_id: str,
        snapshot: DatabaseSnapshot,
        table_name: str,
    ) -> UnderstandingGraphState:
        return {
            "run_id": run_id,
            "snapshot": snapshot.model_dump(mode="json"),
            "table_name": table_name,
            "evidence_steps": [],
            "evidence_round_count": 0,
            "max_evidence_rounds": self.agent.max_evidence_rounds,
            "usage": LLMTokenUsage().model_dump(mode="json"),
            "provider": "",
            "model": "",
            "termination_reason": "",
        }

    @staticmethod
    def _requests(
        state: UnderstandingGraphState,
    ) -> list[EvidenceRequest]:
        return [
            EvidenceRequest.model_validate(item)
            for item in state.get("pending_requests", [])
        ]

    @staticmethod
    def _execution_from_state(
        state: UnderstandingGraphState,
    ) -> TableUnderstandingExecution:
        return TableUnderstandingExecution(
            analysis=TableUnderstandingPayload.model_validate(state["analysis"]),
            provider=state["provider"],
            model=state["model"],
            usage=LLMTokenUsage.model_validate(state["usage"]),
            evidence_scope=state["evidence_scope"],
            evidence_steps=[
                EvidenceStep.model_validate(item)
                for item in state.get("evidence_steps", [])
            ],
            completion_status=state["completion_status"],
            termination_reason=state["termination_reason"],
            evidence_round_count=state["evidence_round_count"],
            max_evidence_rounds=state["max_evidence_rounds"],
            deferred_evidence_requests=[
                EvidenceRequest.model_validate(item)
                for item in state.get("deferred_evidence_requests", [])
            ],
        )
