from datetime import UTC, datetime

import pytest

from app.core.exceptions import DatabaseSnapshotNotFoundError
from app.models import (
    DatabaseMetadata,
    DatabaseSnapshot,
    DatabaseSource,
    ScanStatistics,
)
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository


def make_snapshot() -> DatabaseSnapshot:
    return DatabaseSnapshot(
        snapshot_id="snap_test_001",
        captured_at=datetime(2026, 7, 27, tzinfo=UTC),
        source=DatabaseSource(
            database_type="mysql",
            host="127.0.0.1",
            port=3307,
            database="legacy_enterprise",
        ),
        database=DatabaseMetadata(
            name="legacy_enterprise",
            server_version="8.4.10",
            current_user="ai_reader@%",
            character_set="utf8mb4",
            collation="utf8mb4_0900_ai_ci",
        ),
        tables=[],
        declared_relationships=[],
        scan_statistics=ScanStatistics(
            table_count=0,
            view_count=0,
            column_count=0,
            foreign_key_count=0,
            index_count=0,
        ),
    )


def test_repository_round_trip(tmp_path) -> None:
    repository = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    snapshot = make_snapshot()

    repository.save(snapshot)

    assert repository.get(snapshot.snapshot_id) == snapshot


def test_repository_rejects_invalid_snapshot_id(tmp_path) -> None:
    repository = FileDatabaseSnapshotRepository(tmp_path / "snapshots")

    with pytest.raises(DatabaseSnapshotNotFoundError):
        repository.get("../../etc/passwd")
