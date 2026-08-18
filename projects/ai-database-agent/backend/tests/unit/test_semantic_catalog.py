from datetime import UTC, datetime

import pytest

from app.agents.database_understanding import TableUnderstandingExecution
from app.models import (
    ColumnSchema,
    ColumnUnderstanding,
    DatabaseMetadata,
    DatabaseSnapshot,
    DatabaseSource,
    LLMTokenUsage,
    ScanStatistics,
    TableSchema,
    TableUnderstandingPayload,
    TableUnderstandingRun,
)
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository
from app.repositories.semantic_catalog import FileSemanticCatalogRepository
from app.repositories.understanding_run import FileUnderstandingRunRepository
from app.services.database_understanding import DatabaseUnderstandingService
from app.services.semantic_catalog import SemanticCatalogService


def make_catalog_snapshot() -> DatabaseSnapshot:
    return DatabaseSnapshot(
        snapshot_id="snap_catalog",
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
        tables=[
            TableSchema(
                name="rs_gzff",
                table_type="BASE TABLE",
                columns=[
                    ColumnSchema(
                        name="ygbh",
                        ordinal_position=1,
                        data_type="varchar",
                        column_type="varchar(20)",
                        nullable=False,
                    )
                ],
            )
        ],
        declared_relationships=[],
        scan_statistics=ScanStatistics(
            table_count=1,
            view_count=0,
            column_count=1,
            foreign_key_count=0,
            index_count=0,
        ),
    )


def make_catalog_run(run_id: str) -> TableUnderstandingRun:
    return TableUnderstandingRun(
        run_id=run_id,
        snapshot_id="snap_catalog",
        table_name="rs_gzff",
        created_at=datetime(2026, 7, 28, tzinfo=UTC),
        provider="deepseek",
        model="deepseek-chat",
        prompt_version="database-understanding-v3-evidence-loop",
        evidence_scope="schema_and_query_evidence",
        usage=LLMTokenUsage(total_tokens=100),
        analysis=TableUnderstandingPayload(
            summary="员工工资发放记录",
            status="inferred",
            columns=[
                ColumnUnderstanding(
                    column_name="ygbh",
                    status="inferred",
                )
            ],
        ),
        completion_status="completed",
        termination_reason="evidence_resolved",
        evidence_round_count=1,
        max_evidence_rounds=3,
    )


@pytest.mark.asyncio
async def test_catalog_publish_is_idempotent_and_versions_new_runs(tmp_path) -> None:
    snapshot_repository = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    run_repository = FileUnderstandingRunRepository(tmp_path / "runs")
    catalog_repository = FileSemanticCatalogRepository(tmp_path / "catalog")
    service = SemanticCatalogService(
        catalog_repository,
        snapshot_repository,
        run_repository,
    )
    snapshot_repository.save(make_catalog_snapshot())
    first_run = make_catalog_run("understand_catalog_v1")
    run_repository.save(first_run)

    first = await service.publish_run(first_run.run_id)
    repeated = await service.publish_run(first_run.run_id)

    assert first.version == 1
    assert repeated == first
    assert first.analysis.summary == "员工工资发放记录"

    second_run = make_catalog_run("understand_catalog_v2")
    run_repository.save(second_run)
    second = await service.publish_run(second_run.run_id)

    assert second.catalog_entry_id == first.catalog_entry_id
    assert second.version == 2
    assert second.source_run_id == second_run.run_id
    assert len(await service.list_tables("legacy_enterprise")) == 1
    assert len(list((tmp_path / "catalog" / "history").glob("*.json"))) == 2


class FakeCatalogUnderstandingAgent:
    async def understand_table(
        self,
        _snapshot: DatabaseSnapshot,
        _table_name: str,
    ) -> TableUnderstandingExecution:
        run = make_catalog_run("unused")
        return TableUnderstandingExecution(
            analysis=run.analysis,
            provider=run.provider,
            model=run.model,
            usage=run.usage,
            evidence_scope="schema_and_query_evidence",
            evidence_steps=[],
            completion_status="completed",
            termination_reason="evidence_resolved",
            evidence_round_count=1,
            max_evidence_rounds=3,
            deferred_evidence_requests=[],
        )


@pytest.mark.asyncio
async def test_understanding_service_automatically_publishes_catalog(tmp_path) -> None:
    snapshot_repository = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    run_repository = FileUnderstandingRunRepository(tmp_path / "runs")
    catalog_repository = FileSemanticCatalogRepository(tmp_path / "catalog")
    catalog_service = SemanticCatalogService(
        catalog_repository,
        snapshot_repository,
        run_repository,
    )
    snapshot_repository.save(make_catalog_snapshot())
    service = DatabaseUnderstandingService(
        snapshot_repository,
        run_repository,
        FakeCatalogUnderstandingAgent(),  # type: ignore[arg-type]
        catalog_service,
    )

    run = await service.understand_table("snap_catalog", "rs_gzff")

    assert run.catalog_entry_id is not None
    assert run.catalog_version == 1
    catalog_entry = await catalog_service.get_table(
        "legacy_enterprise",
        "rs_gzff",
    )
    assert catalog_entry.source_run_id == run.run_id
