from datetime import UTC, datetime
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.adapters.database import DatabaseAdapterFactory
from app.agents.database_understanding import DatabaseUnderstandingAgent
from app.agents.database_understanding.prompts import PROMPT_VERSION
from app.agents.sql_execution import SQLExecutionAgent
from app.core.exceptions import (
    UnderstandingRunNotFoundError,
    WorkflowResumeRequiredError,
)
from app.graphs.understanding import UnderstandingGraphRunner
from app.models import (
    DatabaseSnapshot,
    TableUnderstandingRun,
    WorkflowStatus,
)
from app.repositories.database_snapshot import DatabaseSnapshotRepository
from app.repositories.understanding_run import UnderstandingRunRepository
from app.services.database_connection import DatabaseConnectionService
from app.services.semantic_catalog import SemanticCatalogService


class DatabaseUnderstandingService:
    def __init__(
        self,
        snapshot_repository: DatabaseSnapshotRepository,
        run_repository: UnderstandingRunRepository,
        agent: DatabaseUnderstandingAgent,
        catalog_service: SemanticCatalogService | None = None,
        connection_service: DatabaseConnectionService | None = None,
        adapter_factory: DatabaseAdapterFactory | None = None,
        graph_runner: UnderstandingGraphRunner | None = None,
    ) -> None:
        self.snapshot_repository = snapshot_repository
        self.run_repository = run_repository
        self.agent = agent
        self.catalog_service = catalog_service
        self.connection_service = connection_service
        self.adapter_factory = adapter_factory
        self.graph_runner = graph_runner

    async def understand_table(
        self,
        snapshot_id: str,
        table_name: str,
    ) -> TableUnderstandingRun:
        snapshot = await run_in_threadpool(self.snapshot_repository.get, snapshot_id)
        run_id = self._new_run_id()
        execution_agent = None
        if self.connection_service is not None and self.adapter_factory is not None:
            config = await self.connection_service.resolve_snapshot(snapshot)
            execution_agent = SQLExecutionAgent(
                self.adapter_factory.create(config),
                max_rows=50,
            )
        if self.graph_runner is not None:
            try:
                execution = await self.graph_runner.run(
                    run_id=run_id,
                    snapshot=snapshot,
                    table_name=table_name,
                    sql_execution_agent=execution_agent,
                )
            except Exception as exc:
                raise WorkflowResumeRequiredError(
                    run_id,
                    "understanding",
                    (
                        "数据库理解流程已保存断点，可以使用工作流恢复接口"
                        f"从失败节点继续：{str(exc)[:500]}"
                    ),
                ) from exc
            workflow_engine = "langgraph"
        elif execution_agent is None:
            execution = await self.agent.understand_table(snapshot, table_name)
            workflow_engine = "legacy"
        else:
            execution = await self.agent.understand_table(
                snapshot,
                table_name,
                execution_agent,
            )
            workflow_engine = "legacy"
        return await self._persist_run(
            run_id=run_id,
            snapshot=snapshot,
            table_name=table_name,
            execution=execution,
            workflow_engine=workflow_engine,
        )

    async def workflow_status(self, run_id: str) -> WorkflowStatus:
        if self.graph_runner is None:
            raise WorkflowResumeRequiredError(
                run_id,
                "understanding",
                "当前数据库理解流程没有启用LangGraph断点。",
            )
        return await self.graph_runner.status(run_id)

    async def resume(self, run_id: str) -> TableUnderstandingRun:
        try:
            return await self.get_run(run_id)
        except UnderstandingRunNotFoundError:
            pass
        if self.graph_runner is None:
            raise WorkflowResumeRequiredError(
                run_id,
                "understanding",
                "当前数据库理解流程没有启用LangGraph断点。",
            )
        try:
            execution, snapshot, table_name = await self.graph_runner.resume(
                run_id
            )
        except Exception as exc:
            raise WorkflowResumeRequiredError(
                run_id,
                "understanding",
                f"数据库理解流程恢复失败，断点仍已保留：{str(exc)[:500]}",
            ) from exc
        return await self._persist_run(
            run_id=run_id,
            snapshot=snapshot,
            table_name=table_name,
            execution=execution,
            workflow_engine="langgraph",
        )

    async def _persist_run(
        self,
        *,
        run_id: str,
        snapshot: DatabaseSnapshot,
        table_name: str,
        execution,
        workflow_engine: str,
    ) -> TableUnderstandingRun:
        run = TableUnderstandingRun(
            run_id=run_id,
            snapshot_id=snapshot.snapshot_id,
            table_name=table_name,
            created_at=datetime.now(UTC),
            provider=execution.provider,
            model=execution.model,
            prompt_version=PROMPT_VERSION,
            workflow_engine=workflow_engine,
            workflow_thread_id=(
                run_id if workflow_engine == "langgraph" else None
            ),
            evidence_scope=execution.evidence_scope,
            usage=execution.usage,
            analysis=execution.analysis,
            evidence_steps=execution.evidence_steps,
            completion_status=execution.completion_status,
            termination_reason=execution.termination_reason,
            evidence_round_count=execution.evidence_round_count,
            max_evidence_rounds=execution.max_evidence_rounds,
            deferred_evidence_requests=execution.deferred_evidence_requests,
        )
        if self.catalog_service is not None:
            await run_in_threadpool(self.run_repository.save, run)
            catalog_entry = await self.catalog_service.publish(run, snapshot)
            run = run.model_copy(
                update={
                    "catalog_entry_id": catalog_entry.catalog_entry_id,
                    "catalog_version": catalog_entry.version,
                }
            )
        await run_in_threadpool(self.run_repository.save, run)
        return run

    async def get_run(self, run_id: str) -> TableUnderstandingRun:
        return await run_in_threadpool(self.run_repository.get, run_id)

    @staticmethod
    def _new_run_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return f"understand_{timestamp}_{uuid4().hex[:8]}"
