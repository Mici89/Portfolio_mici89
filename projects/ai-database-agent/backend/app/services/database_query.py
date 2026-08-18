from datetime import UTC, datetime
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.adapters.database import DatabaseAdapterFactory
from app.agents.database_query import DatabaseQueryAgent
from app.agents.sql_execution import SQLExecutionAgent
from app.core.exceptions import (
    DatabaseQueryRunNotFoundError,
    WorkflowResumeRequiredError,
)
from app.graphs.query import QueryGraphRunner
from app.models import (
    DatabaseQueryRun,
    DatabaseSnapshot,
    NaturalLanguageQueryRequest,
    WorkflowStatus,
)
from app.repositories.database_query import DatabaseQueryRunRepository
from app.repositories.database_snapshot import DatabaseSnapshotRepository
from app.services.database_connection import DatabaseConnectionService
from app.services.effective_semantics import EffectiveSemanticResolver


class DatabaseQueryService:
    def __init__(
        self,
        snapshot_repository: DatabaseSnapshotRepository,
        query_repository: DatabaseQueryRunRepository,
        semantic_resolver: EffectiveSemanticResolver,
        agent: DatabaseQueryAgent,
        connection_service: DatabaseConnectionService | None = None,
        adapter_factory: DatabaseAdapterFactory | None = None,
        graph_runner: QueryGraphRunner | None = None,
    ) -> None:
        self.snapshot_repository = snapshot_repository
        self.query_repository = query_repository
        self.semantic_resolver = semantic_resolver
        self.agent = agent
        self.connection_service = connection_service
        self.adapter_factory = adapter_factory
        self.graph_runner = graph_runner

    async def query(
        self,
        snapshot_id: str,
        request: NaturalLanguageQueryRequest,
        conversation_context: dict[str, object] | None = None,
    ) -> DatabaseQueryRun:
        snapshot = await run_in_threadpool(
            self.snapshot_repository.get,
            snapshot_id,
        )
        semantics = await self.semantic_resolver.resolve(snapshot)
        query_id = self._new_query_id()
        if self.graph_runner is not None:
            try:
                execution = await self.graph_runner.run(
                    query_id=query_id,
                    snapshot=snapshot,
                    question=request.question,
                    semantics=semantics,
                    conversation_context=conversation_context,
                )
            except Exception as exc:
                raise WorkflowResumeRequiredError(
                    query_id,
                    "query",
                    (
                        "数据库查询流程已保存断点，可以使用工作流恢复接口"
                        f"从失败节点继续：{str(exc)[:500]}"
                    ),
                ) from exc
            workflow_engine = "langgraph"
        else:
            execution_agent = None
            if self.connection_service is not None and self.adapter_factory is not None:
                config = await self.connection_service.resolve_snapshot(snapshot)
                execution_agent = SQLExecutionAgent(
                    self.adapter_factory.create(config),
                    max_rows=100,
                )
            execution = await self.agent.query(
                snapshot,
                request.question,
                semantics.payload,
                semantics.sources,
                semantics.field_sources,
                semantics.field_meanings,
                conversation_context,
                execution_agent,
            )
            workflow_engine = "legacy"
        return await self._persist_run(
            query_id=query_id,
            snapshot=snapshot,
            question=request.question,
            execution=execution,
            workflow_engine=workflow_engine,
        )

    async def workflow_status(self, query_id: str) -> WorkflowStatus:
        if self.graph_runner is None:
            raise WorkflowResumeRequiredError(
                query_id,
                "query",
                "当前查询流程没有启用LangGraph断点。",
            )
        return await self.graph_runner.status(query_id)

    async def resume(self, query_id: str) -> DatabaseQueryRun:
        try:
            return await self.get_run(query_id)
        except DatabaseQueryRunNotFoundError:
            pass
        if self.graph_runner is None:
            raise WorkflowResumeRequiredError(
                query_id,
                "query",
                "当前查询流程没有启用LangGraph断点。",
            )
        try:
            execution, snapshot, question = await self.graph_runner.resume(
                query_id
            )
        except Exception as exc:
            raise WorkflowResumeRequiredError(
                query_id,
                "query",
                f"数据库查询流程恢复失败，断点仍已保留：{str(exc)[:500]}",
            ) from exc
        return await self._persist_run(
            query_id=query_id,
            snapshot=snapshot,
            question=question,
            execution=execution,
            workflow_engine="langgraph",
        )

    async def _persist_run(
        self,
        *,
        query_id: str,
        snapshot: DatabaseSnapshot,
        question: str,
        execution,
        workflow_engine: str,
    ) -> DatabaseQueryRun:
        run = DatabaseQueryRun(
            query_id=query_id,
            snapshot_id=snapshot.snapshot_id,
            database_name=snapshot.database.name,
            question=question,
            created_at=datetime.now(UTC),
            status=(
                "completed"
                if execution.attempts[-1].result.status == "executed"
                else "execution_failed"
            ),
            workflow_engine=workflow_engine,
            workflow_thread_id=query_id if workflow_engine == "langgraph" else None,
            provider=execution.provider,
            model=execution.model,
            usage=execution.usage,
            semantic_sources=execution.semantic_sources,
            attempts=execution.attempts,
            explanation=execution.explanation,
        )
        await run_in_threadpool(self.query_repository.save, run)
        return run

    async def get_run(self, query_id: str) -> DatabaseQueryRun:
        return await run_in_threadpool(self.query_repository.get, query_id)

    @staticmethod
    def _new_query_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return f"query_{timestamp}_{uuid4().hex[:8]}"
