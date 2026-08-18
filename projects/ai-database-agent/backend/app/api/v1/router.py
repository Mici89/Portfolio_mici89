from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.database_actions import router as database_actions_router
from app.api.v1.endpoints.database_connections import router as database_connections_router
from app.api.v1.endpoints.database_query import router as database_query_router
from app.api.v1.endpoints.database_snapshots import router as database_snapshots_router
from app.api.v1.endpoints.database_understanding import (
    router as database_understanding_router,
)
from app.api.v1.endpoints.semantic_catalog import router as semantic_catalog_router

router = APIRouter()
router.include_router(
    auth_router,
    prefix="/auth",
    tags=["auth"],
)
router.include_router(
    database_connections_router,
    prefix="/database-connections",
    tags=["database-connections"],
)
router.include_router(
    database_actions_router,
    prefix="/database-actions",
    tags=["database-actions"],
)
router.include_router(
    database_snapshots_router,
    prefix="/database-snapshots",
    tags=["database-snapshots"],
)
router.include_router(
    database_understanding_router,
    prefix="/database-understanding",
    tags=["database-understanding"],
)
router.include_router(
    database_query_router,
    prefix="/database-query",
    tags=["database-query"],
)
router.include_router(
    semantic_catalog_router,
    prefix="/semantic-catalog",
    tags=["semantic-catalog"],
)
