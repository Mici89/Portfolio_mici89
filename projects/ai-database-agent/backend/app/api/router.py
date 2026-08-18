from fastapi import APIRouter

from app.api.v1.router import router as v1_router
from app.core.config import get_settings

api_router = APIRouter()
settings = get_settings()
api_router.include_router(v1_router, prefix=settings.api_v1_prefix)


@api_router.get(
    "/health/live",
    tags=["health"],
    summary="检查 API 进程是否存活",
)
async def liveness() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }
