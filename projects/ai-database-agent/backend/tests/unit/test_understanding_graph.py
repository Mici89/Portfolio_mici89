from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agents.database_understanding import DatabaseUnderstandingAgent
from app.agents.sql_execution import SQLExecutionAgent
from app.agents.sql_generation import SQLGenerationAgent
from app.core.exceptions import WorkflowResumeRequiredError
from app.graphs.understanding import UnderstandingGraphRunner
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository
from app.repositories.understanding_run import FileUnderstandingRunRepository
from app.services.database_understanding import DatabaseUnderstandingService
from tests.unit.test_database_understanding_agent import (
    EvidenceLoopLLMClient,
    FakeSelectAdapter,
    make_snapshot,
)


class FailOnceUnderstandingLLM(EvidenceLoopLLMClient):
    def __init__(self) -> None:
        super().__init__(resolve_after_evidence=True)
        self.failed = False

    async def generate_json(self, *, system_prompt, user_payload):
        if (
            not system_prompt.startswith(
                "你是数据库取证流程中的SQL生成Agent"
            )
            and not self.failed
        ):
            self.failed = True
            raise RuntimeError("temporary understanding failure")
        return await super().generate_json(
            system_prompt=system_prompt,
            user_payload=user_payload,
        )


@pytest.mark.asyncio
async def test_understanding_graph_runs_three_evidence_rounds(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "understanding_graph.sqlite"
    llm = EvidenceLoopLLMClient(resolve_after_evidence=False)
    agent = DatabaseUnderstandingAgent(
        llm,
        sql_generation_agent=SQLGenerationAgent(llm),
        sql_execution_agent=SQLExecutionAgent(FakeSelectAdapter()),  # type: ignore[arg-type]
        max_evidence_rounds=3,
    )
    runner = UnderstandingGraphRunner(agent, checkpoint_path)

    execution = await runner.run(
        run_id="understanding_graph_three_rounds",
        snapshot=make_snapshot(),
        table_name="t_a01",
    )

    assert execution.completion_status == "best_effort"
    assert execution.termination_reason == "round_limit_reached"
    assert execution.evidence_round_count == 3
    assert len(execution.evidence_steps) == 3
    assert len(execution.deferred_evidence_requests) == 1
    assert execution.analysis.evidence_requests == []
    async with AsyncSqliteSaver.from_conn_string(
        str(checkpoint_path)
    ) as checkpointer:
        checkpoints = [
            checkpoint
            async for checkpoint in checkpointer.alist(
                {
                    "configurable": {
                        "thread_id": "understanding_graph_three_rounds"
                    }
                }
            )
        ]
    assert len(checkpoints) >= 12


@pytest.mark.asyncio
async def test_understanding_graph_resumes_failed_analysis_node(
    tmp_path: Path,
) -> None:
    run_id = "understanding_graph_resume"
    llm = FailOnceUnderstandingLLM()
    agent = DatabaseUnderstandingAgent(
        llm,
        sql_generation_agent=SQLGenerationAgent(llm),
        sql_execution_agent=SQLExecutionAgent(FakeSelectAdapter()),  # type: ignore[arg-type]
        max_evidence_rounds=3,
    )
    runner = UnderstandingGraphRunner(
        agent,
        tmp_path / "understanding_graph.sqlite",
    )

    with pytest.raises(RuntimeError, match="temporary understanding"):
        await runner.run(
            run_id=run_id,
            snapshot=make_snapshot(),
            table_name="t_a01",
        )

    failed = await runner.status(run_id)
    execution, _, _ = await runner.resume(run_id)
    completed = await runner.status(run_id)

    assert failed.status == "failed"
    assert failed.current_node == "analyze_schema_and_evidence"
    assert failed.can_resume is True
    assert execution.completion_status == "completed"
    assert completed.status == "completed"


@pytest.mark.asyncio
async def test_understanding_service_returns_recoverable_id_and_persists_resume(
    tmp_path: Path,
) -> None:
    snapshot = make_snapshot()
    snapshots = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    snapshots.save(snapshot)
    llm = FailOnceUnderstandingLLM()
    agent = DatabaseUnderstandingAgent(
        llm,
        sql_generation_agent=SQLGenerationAgent(llm),
        sql_execution_agent=SQLExecutionAgent(FakeSelectAdapter()),  # type: ignore[arg-type]
    )
    runner = UnderstandingGraphRunner(
        agent,
        tmp_path / "understanding_graph.sqlite",
    )
    service = DatabaseUnderstandingService(
        snapshots,
        FileUnderstandingRunRepository(tmp_path / "runs"),
        agent,
        graph_runner=runner,
    )

    with pytest.raises(WorkflowResumeRequiredError) as caught:
        await service.understand_table(snapshot.snapshot_id, "t_a01")

    resumed = await service.resume(caught.value.workflow_id)

    assert resumed.workflow_thread_id == caught.value.workflow_id
    assert resumed.completion_status == "completed"
    assert (await service.get_run(resumed.run_id)).run_id == resumed.run_id
