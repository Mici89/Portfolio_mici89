from datetime import UTC, datetime

import pytest

from app.core.exceptions import WorkflowResumeRequiredError
from app.models import (
    DatabaseQueryRun,
    LLMTokenUsage,
    QueryAttempt,
    QueryExplanation,
    QueryIntent,
    QueryPlan,
    QuerySemanticSource,
    SqlExecutionResult,
)
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository
from app.repositories.query_session import FileQuerySessionRepository
from app.services.query_session import QuerySessionService
from tests.unit.test_semantic_review import make_snapshot


class FakeDatabaseQueryService:
    def __init__(self) -> None:
        self.contexts: list[dict[str, object] | None] = []

    async def query(self, snapshot_id, request, conversation_context=None):
        self.contexts.append(conversation_context)
        second_turn = conversation_context is not None
        filters = ["2026年6月"]
        if second_turn:
            filters.append("地区=上海")
        intent = QueryIntent(
            summary="按部门统计工资",
            metrics=["工资总额"],
            dimensions=["部门"],
            filters=filters,
            tables=["rs_gzff"],
        )
        result = SqlExecutionResult(
            status="executed",
            statement_type="SELECT",
            columns=["部门", "工资总额"],
            rows=[{"部门": "财务部", "工资总额": "1000.00"}],
            returned_row_count=1,
        )
        return DatabaseQueryRun(
            query_id=f"query_{len(self.contexts)}",
            snapshot_id=snapshot_id,
            database_name="legacy_enterprise",
            question=request.question,
            created_at=datetime(2026, 7, 29, tzinfo=UTC),
            status="completed",
            provider="fake",
            model="fake",
            usage=LLMTokenUsage(),
            semantic_sources=[
                QuerySemanticSource(
                    table_name="rs_gzff",
                    catalog_version=1,
                    source="ai_catalog",
                )
            ],
            attempts=[
                QueryAttempt(
                    attempt_number=1,
                    plan=QueryPlan(
                        intent=intent,
                        sql="SELECT '财务部' AS `部门`, 1000 AS `工资总额`",
                        sql_purpose="按部门统计工资",
                    ),
                    result=result,
                )
            ],
            explanation=QueryExplanation(
                answer="财务部工资总额为1000元。",
                data_scope="2026年6月",
            ),
        )


class RecoverableDatabaseQueryService:
    def __init__(self) -> None:
        self.snapshot_id = ""
        self.request = None
        self.delegate = FakeDatabaseQueryService()

    async def query(self, snapshot_id, request, conversation_context=None):
        del conversation_context
        self.snapshot_id = snapshot_id
        self.request = request
        raise WorkflowResumeRequiredError(
            "query_pending_turn",
            "query",
            "查询已保存断点",
        )

    async def resume(self, query_id):
        assert query_id == "query_pending_turn"
        assert self.request is not None
        return await self.delegate.query(
            self.snapshot_id,
            self.request,
        )


@pytest.mark.asyncio
async def test_query_session_supplies_structured_context_to_follow_up(tmp_path) -> None:
    snapshot_repository = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    snapshot = make_snapshot()
    snapshot_repository.save(snapshot)
    session_repository = FileQuerySessionRepository(tmp_path / "sessions")
    query_service = FakeDatabaseQueryService()
    service = QuerySessionService(
        session_repository,
        snapshot_repository,
        query_service,  # type: ignore[arg-type]
    )
    session = await service.create(snapshot.snapshot_id)

    first = await service.add_turn(session.session_id, "统计6月份各部门工资")
    second = await service.add_turn(session.session_id, "只看上海地区")

    assert query_service.contexts[0] is None
    context = query_service.contexts[1]
    assert context is not None
    assert context["active_intent"]["filters"] == ["2026年6月"]  # type: ignore[index]
    assert len(context["recent_turns"]) == 1  # type: ignore[arg-type]
    assert second.turn.parent_turn_id == first.turn.turn_id
    assert second.session.current_intent is not None
    assert second.session.current_intent.filters == ["2026年6月", "地区=上海"]
    assert second.turn.result_digest.sample_rows == [{"部门": "财务部", "工资总额": "1000.00"}]
    assert second.turn.result_rows == [{"部门": "财务部", "工资总额": "1000.00"}]
    sessions = await service.list("legacy_enterprise")
    assert [item.session_id for item in sessions] == [session.session_id]


@pytest.mark.asyncio
async def test_query_session_persists_and_resumes_pending_query(
    tmp_path,
) -> None:
    snapshot_repository = FileDatabaseSnapshotRepository(
        tmp_path / "snapshots"
    )
    snapshot = make_snapshot()
    snapshot_repository.save(snapshot)
    session_repository = FileQuerySessionRepository(tmp_path / "sessions")
    service = QuerySessionService(
        session_repository,
        snapshot_repository,
        RecoverableDatabaseQueryService(),  # type: ignore[arg-type]
    )
    session = await service.create(snapshot.snapshot_id)

    with pytest.raises(WorkflowResumeRequiredError):
        await service.add_turn(session.session_id, "统计工资总额")

    pending = await service.get(session.session_id)
    assert pending.pending_query is not None
    assert pending.pending_query.query_id == "query_pending_turn"

    resumed = await service.resume_turn(
        session.session_id,
        "query_pending_turn",
    )

    assert resumed.session.pending_query is None
    assert resumed.turn.user_message == "统计工资总额"
    assert resumed.turn.status == "completed"
