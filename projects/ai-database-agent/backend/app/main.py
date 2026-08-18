from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Database Agent 控制面 API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(ApplicationError)
async def application_exception_handler(
    _: Request,
    exc: ApplicationError,
) -> JSONResponse:
    content: dict[str, Any] = {
        "error": {
            "code": exc.code,
            "message": exc.message,
        }
    }
    workflow_id = getattr(exc, "workflow_id", None)
    workflow_kind = getattr(exc, "workflow_kind", None)
    if workflow_id is not None:
        content["error"]["workflow_id"] = workflow_id
    if workflow_kind is not None:
        content["error"]["workflow_kind"] = workflow_kind
    return JSONResponse(status_code=exc.http_status_code, content=content)


app.include_router(api_router)
