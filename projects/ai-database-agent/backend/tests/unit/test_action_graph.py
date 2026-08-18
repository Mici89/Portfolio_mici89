from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.models import QuerySession, UserPrincipal
from app.repositories.database_action import FileDatabaseActionRepository
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository
from app.repositories.query_session import FileQuerySessionRepository
from app.services.database_action import DatabaseActionService
from tests.unit.test_database_action import (
    FakeWriteAdapter,
    LookupPlanningAgent,
    LookupReadAdapter,
    LookupSemanticResolver,
    make_employee_position_snapshot,
)


@pytest.mark.asyncio
async def test_action_graph_resolves_lookup_previews_executes_and_verifies(
    tmp_path: Path,
) -> None:
    snapshot = make_employee_position_snapshot()
    snapshots = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    snapshots.save(snapshot)
    sessions = FileQuerySessionRepository(tmp_path / "sessions")
    sessions.save(
        QuerySession(
            session_id="session_action_graph",
            snapshot_id=snapshot.snapshot_id,
            database_name=snapshot.database.name,
            title="岗位修改",
            created_at=datetime(2026, 7, 30, tzinfo=UTC),
            updated_at=datetime(2026, 7, 30, tzinfo=UTC),
        )
    )
    writer = FakeWriteAdapter()
    checkpoint_path = tmp_path / "action_graph.sqlite"
    service = DatabaseActionService(
        FileDatabaseActionRepository(tmp_path / "actions"),
        sessions,
        snapshots,
        LookupSemanticResolver(),  # type: ignore[arg-type]
        LookupPlanningAgent(),  # type: ignore[arg-type]
        LookupReadAdapter(),  # type: ignore[arg-type]
        writer,  # type: ignore[arg-type]
        graph_checkpoint_path=checkpoint_path,
    )
    principal = UserPrincipal(
        username="operator",
        role="database_operator",
        authenticated=True,
        permissions=["database_action:execute"],
    )

    planned = await service.plan(
        "session_action_graph",
        "吴凯降职为研发工程师",
        principal,
    )
    waiting = await service.workflow_status(planned.action_id)
    executed = await service.confirm(planned.action_id, principal)
    completed = await service.workflow_status(planned.action_id)

    assert planned.workflow_engine == "langgraph"
    assert planned.workflow_thread_id == planned.action_id
    assert planned.draft.assignments[0].value == 7
    assert planned.status == "pending_confirmation"
    assert waiting.status == "interrupted"
    assert waiting.awaiting_input is True
    assert waiting.current_node == "await_user_confirmation"
    assert executed.status == "executed"
    assert executed.execution is not None
    assert executed.execution.verification_passed is True
    assert len(writer.requests) == 1
    async with AsyncSqliteSaver.from_conn_string(
        str(checkpoint_path)
    ) as checkpointer:
        planning_checkpoints = [
            checkpoint
            async for checkpoint in checkpointer.alist(
                {"configurable": {"thread_id": planned.action_id}}
            )
        ]
        legacy_execution_checkpoints = [
            checkpoint
            async for checkpoint in checkpointer.alist(
                {
                    "configurable": {
                        "thread_id": f"{planned.action_id}:execute"
                    }
                }
            )
        ]
    assert len(planning_checkpoints) >= 6
    assert legacy_execution_checkpoints == []
    assert completed.status == "completed"
    assert "execute_transaction_and_verify" in completed.completed_nodes


@pytest.mark.asyncio
async def test_action_graph_cancels_the_same_interrupted_thread(
    tmp_path: Path,
) -> None:
    snapshot = make_employee_position_snapshot()
    snapshots = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    snapshots.save(snapshot)
    sessions = FileQuerySessionRepository(tmp_path / "sessions")
    sessions.save(
        QuerySession(
            session_id="session_action_cancel",
            snapshot_id=snapshot.snapshot_id,
            database_name=snapshot.database.name,
            title="取消岗位修改",
            created_at=datetime(2026, 7, 30, tzinfo=UTC),
            updated_at=datetime(2026, 7, 30, tzinfo=UTC),
        )
    )
    writer = FakeWriteAdapter()
    service = DatabaseActionService(
        FileDatabaseActionRepository(tmp_path / "actions"),
        sessions,
        snapshots,
        LookupSemanticResolver(),  # type: ignore[arg-type]
        LookupPlanningAgent(),  # type: ignore[arg-type]
        LookupReadAdapter(),  # type: ignore[arg-type]
        writer,  # type: ignore[arg-type]
        graph_checkpoint_path=tmp_path / "action_graph.sqlite",
    )
    principal = UserPrincipal(
        username="operator",
        role="database_operator",
        authenticated=True,
        permissions=["database_action:execute"],
    )

    planned = await service.plan(
        "session_action_cancel",
        "吴凯降职为研发工程师",
        principal,
    )
    cancelled = await service.cancel(planned.action_id, principal)
    completed = await service.workflow_status(planned.action_id)

    assert cancelled.status == "cancelled"
    assert cancelled.cancelled_by == "operator"
    assert writer.requests == []
    assert completed.status == "completed"
