from datetime import UTC, datetime

import pytest

from app.core.exceptions import SemanticReviewValidationError
from app.models import (
    CatalogReviewCreate,
    ColumnSchema,
    ColumnUnderstanding,
    DatabaseMetadata,
    DatabaseSnapshot,
    DatabaseSource,
    FieldReviewInput,
    LLMTokenUsage,
    ScanStatistics,
    SemanticCandidate,
    TableReviewInput,
    TableSchema,
    TableUnderstandingPayload,
    TableUnderstandingRun,
)
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository
from app.repositories.semantic_catalog import FileSemanticCatalogRepository
from app.repositories.semantic_review import FileSemanticReviewRepository
from app.repositories.understanding_run import FileUnderstandingRunRepository
from app.services.semantic_catalog import SemanticCatalogService
from app.services.semantic_review import SemanticReviewService


def make_snapshot() -> DatabaseSnapshot:
    return DatabaseSnapshot(
        snapshot_id="snap_review",
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
                    ),
                    ColumnSchema(
                        name="gz",
                        ordinal_position=2,
                        data_type="decimal",
                        column_type="decimal(12,2)",
                        nullable=False,
                    ),
                ],
            )
        ],
        declared_relationships=[],
        scan_statistics=ScanStatistics(
            table_count=1,
            view_count=0,
            column_count=2,
            foreign_key_count=0,
            index_count=0,
        ),
    )


def make_run() -> TableUnderstandingRun:
    return TableUnderstandingRun(
        run_id="understand_review",
        snapshot_id="snap_review",
        table_name="rs_gzff",
        created_at=datetime(2026, 7, 28, tzinfo=UTC),
        provider="deepseek",
        model="deepseek-chat",
        prompt_version="database-understanding-v3-evidence-loop",
        evidence_scope="schema_and_query_evidence",
        usage=LLMTokenUsage(total_tokens=100),
        analysis=TableUnderstandingPayload(
            summary="记录历史系统工资发放数据",
            status="inferred",
            table_candidates=[
                SemanticCandidate(
                    meaning="工资发放记录",
                    confidence=0.9,
                )
            ],
            columns=[
                ColumnUnderstanding(
                    column_name="ygbh",
                    status="inferred",
                    meaning_candidates=[
                        SemanticCandidate(
                            meaning="人员编号",
                            description="人员的业务编码",
                            confidence=0.8,
                        )
                    ],
                ),
                ColumnUnderstanding(
                    column_name="gz",
                    status="inferred",
                    meaning_candidates=[
                        SemanticCandidate(
                            meaning="工资金额",
                            description="本次发放的工资",
                            confidence=0.92,
                        )
                    ],
                ),
            ],
        ),
        completion_status="completed",
        termination_reason="evidence_resolved",
        evidence_round_count=1,
        max_evidence_rounds=3,
    )


async def make_service(tmp_path) -> tuple[SemanticReviewService, SemanticCatalogService]:
    snapshot_repository = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    run_repository = FileUnderstandingRunRepository(tmp_path / "runs")
    catalog_repository = FileSemanticCatalogRepository(tmp_path / "catalog")
    review_repository = FileSemanticReviewRepository(tmp_path / "reviews")
    catalog_service = SemanticCatalogService(
        catalog_repository,
        snapshot_repository,
        run_repository,
    )
    snapshot_repository.save(make_snapshot())
    run_repository.save(make_run())
    await catalog_service.publish_run("understand_review")
    return (
        SemanticReviewService(
            review_repository,
            catalog_service,
            run_repository,
        ),
        catalog_service,
    )


@pytest.mark.asyncio
async def test_partial_review_can_edit_field_and_keeps_ai_version(tmp_path) -> None:
    service, catalog_service = await make_service(tmp_path)

    review = await service.create_review(
        "legacy_enterprise",
        "rs_gzff",
        CatalogReviewCreate(
            source_catalog_version=1,
            scope="fields",
            reviewer="财务用户A",
            field_decisions=[
                FieldReviewInput(
                    column_name="ygbh",
                    reviewed_meaning="员工编号",
                    reviewed_description="对应员工主数据中的员工编号",
                )
            ],
        ),
    )

    assert review.display_version == "v1-r1"
    assert review.status == "partially_reviewed"
    assert review.field_decisions[0].decision == "edited"
    assert review.reviewed_analysis.columns[0].meaning_candidates[0].meaning == "员工编号"
    ai_entry = await catalog_service.get_table("legacy_enterprise", "rs_gzff")
    assert ai_entry.analysis.columns[0].meaning_candidates[0].meaning == "人员编号"


@pytest.mark.asyncio
async def test_later_review_inherits_previous_field_decisions(tmp_path) -> None:
    service, _ = await make_service(tmp_path)
    await service.create_review(
        "legacy_enterprise",
        "rs_gzff",
        CatalogReviewCreate(
            source_catalog_version=1,
            scope="fields",
            reviewer="人事用户",
            field_decisions=[
                FieldReviewInput(
                    column_name="ygbh",
                    reviewed_meaning="员工编号",
                    reviewed_description="员工主数据编码",
                )
            ],
        ),
    )

    review = await service.create_review(
        "legacy_enterprise",
        "rs_gzff",
        CatalogReviewCreate(
            source_catalog_version=1,
            scope="table",
            reviewer="财务负责人",
            table_decision=TableReviewInput(
                reviewed_meaning="历史工资发放记录",
                reviewed_summary="按员工和发放月份记录历史工资金额。",
            ),
            field_decisions=[
                FieldReviewInput(
                    column_name="ygbh",
                    reviewed_meaning="员工编号",
                    reviewed_description="员工主数据编码",
                ),
                FieldReviewInput(
                    column_name="gz",
                    reviewed_meaning="实发工资",
                    reviewed_description="本次实际发放金额",
                ),
            ],
        ),
    )

    assert review.display_version == "v1-r2"
    assert review.status == "fully_reviewed"
    assert review.reviewed_field_count == 2
    assert review.table_decision is not None
    assert review.reviewed_analysis.table_candidates[0].meaning == "历史工资发放记录"


@pytest.mark.asyncio
async def test_review_rejects_stale_catalog_version(tmp_path) -> None:
    service, _ = await make_service(tmp_path)

    with pytest.raises(SemanticReviewValidationError) as raised:
        await service.create_review(
            "legacy_enterprise",
            "rs_gzff",
            CatalogReviewCreate(
                source_catalog_version=2,
                scope="fields",
                reviewer="审核人",
                field_decisions=[
                    FieldReviewInput(
                        column_name="ygbh",
                        reviewed_meaning="员工编号",
                    )
                ],
            ),
        )

    assert raised.value.http_status_code == 409
