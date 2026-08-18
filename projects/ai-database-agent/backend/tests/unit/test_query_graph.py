from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agents.database_query import DatabaseQueryAgent
from app.core.exceptions import WorkflowResumeRequiredError
from app.graphs.query import QueryGraphRunner
from app.models import NaturalLanguageQueryRequest, QuerySemanticSource
from app.repositories.database_query import FileDatabaseQueryRunRepository
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository
from app.services.database_query import DatabaseQueryService
from app.services.effective_semantics import EffectiveSemanticContext
from tests.unit.test_database_query_agent import (
    EmptyThenResolvedExecutor,
    QueryLLM,
    RepairingExecutor,
    ResultAwareQueryLLM,
    SuccessfulExecutor,
)
from tests.unit.test_semantic_review import make_snapshot


def semantics() -> EffectiveSemanticContext:
    return EffectiveSemanticContext(
        payload={"tables": []},
        sources=[
            QuerySemanticSource(
                table_name="rs_gzff",
                catalog_version=1,
                source="ai_catalog",
            )
        ],
        field_sources={
            ("rs_gzff", "ygbh"): "ai_catalog",
            ("rs_gzff", "gz"): "ai_catalog",
        },
        field_meanings={
            ("rs_gzff", "ygbh"): "员工编号",
            ("rs_gzff", "gz"): "工资金额",
        },
    )


@pytest.mark.asyncio
async def test_query_graph_executes_and_persists_checkpoints(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "query_graph.sqlite"
    query_id = "query_graph_success"
    runner = QueryGraphRunner(
        DatabaseQueryAgent(
            QueryLLM(),  # type: ignore[arg-type]
            SuccessfulExecutor(),  # type: ignore[arg-type]
        ),
        checkpoint_path,
    )

    execution = await runner.run(
        query_id=query_id,
        snapshot=make_snapshot(),
        question="工资总额是多少",
        semantics=semantics(),
        conversation_context=None,
    )

    assert execution.explanation.answer == "工资总额为1000元。"
    assert len(execution.attempts) == 1
    assert checkpoint_path.is_file()
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        checkpoints = [
            checkpoint
            async for checkpoint in checkpointer.alist(
                {"configurable": {"thread_id": query_id}}
            )
        ]
    assert len(checkpoints) >= 6
    assert checkpoints[0].config["configurable"]["thread_id"] == query_id


@pytest.mark.asyncio
async def test_query_graph_replans_after_execution_failure(tmp_path: Path) -> None:
    executor = RepairingExecutor()
    llm = QueryLLM()
    runner = QueryGraphRunner(
        DatabaseQueryAgent(
            llm,  # type: ignore[arg-type]
            executor,  # type: ignore[arg-type]
            max_attempts=2,
        ),
        tmp_path / "query_graph.sqlite",
    )

    execution = await runner.run(
        query_id="query_graph_execution_repair",
        snapshot=make_snapshot(),
        question="工资总额是多少",
        semantics=semantics(),
        conversation_context=None,
    )

    assert [attempt.result.status for attempt in execution.attempts] == [
        "failed",
        "executed",
    ]
    assert executor.calls == 2
    assert llm.planning_calls == 2


@pytest.mark.asyncio
async def test_query_graph_replans_insufficient_result(tmp_path: Path) -> None:
    llm = ResultAwareQueryLLM()
    executor = EmptyThenResolvedExecutor()
    runner = QueryGraphRunner(
        DatabaseQueryAgent(
            llm,  # type: ignore[arg-type]
            executor,  # type: ignore[arg-type]
            max_attempts=3,
        ),
        tmp_path / "query_graph.sqlite",
    )

    execution = await runner.run(
        query_id="query_graph_result_repair",
        snapshot=make_snapshot(),
        question="工资总额是多少",
        semantics=semantics(),
        conversation_context=None,
    )

    assert len(execution.attempts) == 2
    assert execution.attempts[0].assessment is not None
    assert execution.attempts[0].assessment.verdict == "replan"
    assert execution.attempts[1].assessment is not None
    assert execution.attempts[1].assessment.verdict == "sufficient"
    assert llm.repair_contexts[1] is not None
    assert llm.repair_contexts[1]["query_result"]["rows"] == []  # type: ignore[index]


class FailOnceQueryLLM(QueryLLM):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    async def generate_json(self, *, system_prompt, user_payload):
        if (
            user_payload["task"] == "plan_and_generate_read_only_query"
            and not self.failed
        ):
            self.failed = True
            raise RuntimeError("temporary query planning failure")
        return await super().generate_json(
            system_prompt=system_prompt,
            user_payload=user_payload,
        )


@pytest.mark.asyncio
async def test_query_graph_resumes_from_failed_node_without_new_thread(
    tmp_path: Path,
) -> None:
    query_id = "query_graph_resume"
    llm = FailOnceQueryLLM()
    runner = QueryGraphRunner(
        DatabaseQueryAgent(
            llm,  # type: ignore[arg-type]
            SuccessfulExecutor(),  # type: ignore[arg-type]
        ),
        tmp_path / "query_graph.sqlite",
    )

    with pytest.raises(RuntimeError, match="temporary query planning"):
        await runner.run(
            query_id=query_id,
            snapshot=make_snapshot(),
            question="工资总额是多少",
            semantics=semantics(),
            conversation_context=None,
        )

    failed = await runner.status(query_id)
    execution, _, _ = await runner.resume(query_id)
    completed = await runner.status(query_id)

    assert failed.status == "failed"
    assert failed.current_node == "plan_query"
    assert failed.can_resume is True
    assert execution.explanation.answer == "工资总额为1000元。"
    assert completed.status == "completed"


class FixedSemanticResolver:
    async def resolve(self, _snapshot):
        return semantics()


@pytest.mark.asyncio
async def test_query_service_returns_recoverable_id_and_persists_resume(
    tmp_path: Path,
) -> None:
    snapshot = make_snapshot()
    snapshots = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    snapshots.save(snapshot)
    llm = FailOnceQueryLLM()
    agent = DatabaseQueryAgent(
        llm,  # type: ignore[arg-type]
        SuccessfulExecutor(),  # type: ignore[arg-type]
    )
    runner = QueryGraphRunner(
        agent,
        tmp_path / "query_graph.sqlite",
    )
    service = DatabaseQueryService(
        snapshots,
        FileDatabaseQueryRunRepository(tmp_path / "runs"),
        FixedSemanticResolver(),  # type: ignore[arg-type]
        agent,
        graph_runner=runner,
    )

    with pytest.raises(WorkflowResumeRequiredError) as caught:
        await service.query(
            snapshot.snapshot_id,
            NaturalLanguageQueryRequest(question="工资总额是多少"),
        )

    resumed = await service.resume(caught.value.workflow_id)

    assert resumed.workflow_thread_id == caught.value.workflow_id
    assert resumed.status == "completed"
    assert (await service.get_run(resumed.query_id)).query_id == resumed.query_id
