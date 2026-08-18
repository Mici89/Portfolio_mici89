from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.graphs.conversation import ConversationGraphRunner
from app.models import ConversationRoutingDecision, QuerySession, UserPrincipal
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository
from app.repositories.query_session import FileQuerySessionRepository
from app.services.conversation import ConversationService
from app.services.conversation_context import ConversationContextMerger
from app.services.query_session import QuerySessionService
from tests.unit.test_query_session import FakeDatabaseQueryService
from tests.unit.test_semantic_review import make_snapshot


class QueryRouter:
    async def route(self, message, active_query_intent):
        return ConversationRoutingDecision(
            kind="query",
            context_mode="standalone",
            standalone_intent_complete=True,
            confidence=0.99,
            reason="完整的独立查询",
        )


class UnusedActionService:
    async def plan(self, *args, **kwargs):
        raise AssertionError("查询路由不应进入写操作子图")


@pytest.mark.asyncio
async def test_conversation_parent_graph_routes_and_invokes_query_subgraph(
    tmp_path: Path,
) -> None:
    snapshot = make_snapshot()
    snapshots = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    snapshots.save(snapshot)
    sessions = FileQuerySessionRepository(tmp_path / "sessions")
    session = QuerySession(
        session_id="session_conversation_graph",
        snapshot_id=snapshot.snapshot_id,
        database_name=snapshot.database.name,
        title="新分析对话",
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        updated_at=datetime(2026, 7, 30, tzinfo=UTC),
    )
    sessions.save(session)
    query_session_service = QuerySessionService(
        sessions,
        snapshots,
        FakeDatabaseQueryService(),  # type: ignore[arg-type]
    )
    router = QueryRouter()
    merger = ConversationContextMerger()
    checkpoint_path = tmp_path / "conversation_graph.sqlite"
    graph_runner = ConversationGraphRunner(
        router,  # type: ignore[arg-type]
        merger,
        query_session_service,
        UnusedActionService(),  # type: ignore[arg-type]
        checkpoint_path,
    )
    service = ConversationService(
        router,  # type: ignore[arg-type]
        merger,
        query_session_service,
        UnusedActionService(),  # type: ignore[arg-type]
        graph_runner,
    )
    principal = UserPrincipal(
        username="viewer",
        role="viewer",
        authenticated=False,
    )

    response = await service.send(
        session.session_id,
        "统计6月份各部门工资",
        principal,
    )

    assert response.kind == "query"
    assert response.workflow_engine == "langgraph"
    assert response.workflow_thread_id is not None
    assert response.query is not None
    assert response.query.turn.answer == "财务部工资总额为1000元。"
    async with AsyncSqliteSaver.from_conn_string(
        str(checkpoint_path)
    ) as checkpointer:
        checkpoints = [
            checkpoint
            async for checkpoint in checkpointer.alist(
                {
                    "configurable": {
                        "thread_id": response.workflow_thread_id
                    }
                }
            )
        ]
    assert len(checkpoints) >= 6
