from fastapi import APIRouter, status

from app.api.dependencies import (
    SemanticCatalogServiceDependency,
    SemanticReviewServiceDependency,
)
from app.models import (
    CatalogEvidenceBundle,
    CatalogReviewCreate,
    CatalogReviewRevision,
    SemanticCatalogEntry,
)

router = APIRouter()


@router.get(
    "/databases/{database_name}/tables",
    response_model=list[SemanticCatalogEntry],
    summary="列出数据库当前语义目录",
)
async def list_catalog_tables(
    database_name: str,
    service: SemanticCatalogServiceDependency,
    connection_id: str | None = None,
) -> list[SemanticCatalogEntry]:
    return await service.list_tables(database_name, connection_id)


@router.get(
    "/databases/{database_name}/tables/{table_name}",
    response_model=SemanticCatalogEntry,
    summary="读取表的当前语义目录条目",
)
async def get_catalog_table(
    database_name: str,
    table_name: str,
    service: SemanticCatalogServiceDependency,
    connection_id: str | None = None,
) -> SemanticCatalogEntry:
    return await service.get_table(database_name, table_name, connection_id)


@router.get(
    "/databases/{database_name}/reviews",
    response_model=list[CatalogReviewRevision],
    summary="列出数据库各表的最新人工审核版本",
)
async def list_latest_reviews(
    database_name: str,
    service: SemanticReviewServiceDependency,
    connection_id: str | None = None,
) -> list[CatalogReviewRevision]:
    return await service.list_latest_reviews(database_name, connection_id)


@router.get(
    "/databases/{database_name}/tables/{table_name}/evidence",
    response_model=CatalogEvidenceBundle,
    summary="读取当前语义版本的完整取证证据",
)
async def get_catalog_evidence(
    database_name: str,
    table_name: str,
    service: SemanticReviewServiceDependency,
    connection_id: str | None = None,
) -> CatalogEvidenceBundle:
    return await service.get_evidence(database_name, table_name, connection_id)


@router.get(
    "/databases/{database_name}/tables/{table_name}/reviews",
    response_model=list[CatalogReviewRevision],
    summary="列出一张表的人工审核历史",
)
async def list_table_reviews(
    database_name: str,
    table_name: str,
    service: SemanticReviewServiceDependency,
    connection_id: str | None = None,
) -> list[CatalogReviewRevision]:
    return await service.list_reviews(database_name, table_name, connection_id)


@router.post(
    "/databases/{database_name}/tables/{table_name}/reviews",
    response_model=CatalogReviewRevision,
    status_code=status.HTTP_201_CREATED,
    summary="提交整表或多字段人工审核并生成不可变审核版本",
)
async def create_table_review(
    database_name: str,
    table_name: str,
    payload: CatalogReviewCreate,
    service: SemanticReviewServiceDependency,
    connection_id: str | None = None,
) -> CatalogReviewRevision:
    return await service.create_review(
        database_name,
        table_name,
        payload,
        connection_id,
    )


@router.post(
    "/runs/{run_id}/publish",
    response_model=SemanticCatalogEntry,
    status_code=status.HTTP_201_CREATED,
    summary="将已有理解运行发布到语义目录",
)
async def publish_understanding_run(
    run_id: str,
    service: SemanticCatalogServiceDependency,
) -> SemanticCatalogEntry:
    return await service.publish_run(run_id)
