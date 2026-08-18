from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models import (
    ColumnSchema,
    DatabaseMetadata,
    DatabaseSnapshot,
    DatabaseSource,
    ScanStatistics,
    TableSchema,
)
from app.repositories.catalog_build_job import FileCatalogBuildJobRepository
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository
from app.services.catalog_build import CatalogBuildService


def make_build_snapshot() -> DatabaseSnapshot:
    tables = [
        TableSchema(
            name=name,
            table_type="BASE TABLE",
            columns=[
                ColumnSchema(
                    name="id",
                    ordinal_position=1,
                    data_type="bigint",
                    column_type="bigint",
                    nullable=False,
                )
            ],
        )
        for name in ("already_understood", "needs_understanding")
    ]
    return DatabaseSnapshot(
        snapshot_id="snap_build",
        captured_at=datetime(2026, 7, 28, tzinfo=UTC),
        source=DatabaseSource(
            database_type="mysql",
            host="127.0.0.1",
            port=3307,
            database="legacy_enterprise",
        ),
        database=DatabaseMetadata(
            name="legacy_enterprise",
            server_version="8.4",
            current_user="ai_reader@%",
            character_set="utf8mb4",
            collation="utf8mb4_0900_ai_ci",
        ),
        tables=tables,
        declared_relationships=[],
        scan_statistics=ScanStatistics(
            table_count=2,
            view_count=0,
            column_count=2,
            foreign_key_count=0,
            index_count=0,
        ),
    )


class FakeBuildUnderstandingService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def understand_table(self, _snapshot_id: str, table_name: str):
        self.calls.append(table_name)
        return SimpleNamespace(
            run_id=f"run_{table_name}",
            catalog_entry_id=f"catalog_{table_name}",
            catalog_version=1,
        )


class FakeBuildCatalogService:
    async def find_table(self, _database_name: str, table_name: str):
        if table_name == "already_understood":
            return SimpleNamespace(
                schema_fingerprint="already_understood",
                catalog_entry_id="catalog_existing",
                version=2,
            )
        return None

    @staticmethod
    def schema_fingerprint(table_payload: dict[str, object]) -> str:
        return str(table_payload["name"])


@pytest.mark.asyncio
async def test_catalog_build_skips_unchanged_and_understands_missing_tables(
    tmp_path,
) -> None:
    snapshot_repository = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    job_repository = FileCatalogBuildJobRepository(tmp_path / "jobs")
    understanding_service = FakeBuildUnderstandingService()
    snapshot_repository.save(make_build_snapshot())
    service = CatalogBuildService(
        job_repository,
        snapshot_repository,
        understanding_service,  # type: ignore[arg-type]
        FakeBuildCatalogService(),  # type: ignore[arg-type]
    )

    created = await service.create_job("snap_build")
    await service.run_job(created.job_id)
    completed = await service.get_job(created.job_id)

    assert completed.status == "completed"
    assert completed.processed_tables == 2
    assert completed.skipped_tables == 1
    assert completed.completed_tables == 1
    assert completed.failed_tables == 0
    assert understanding_service.calls == ["needs_understanding"]
    assert [item.status for item in completed.items] == ["skipped", "completed"]
