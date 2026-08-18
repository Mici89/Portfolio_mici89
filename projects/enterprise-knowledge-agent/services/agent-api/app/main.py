from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.knowledge_bases import router as knowledge_bases_router
from app.api.documents import router as documents_router
from app.api.search import router as search_router
from app.api.qa import router as qa_router
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

app = FastAPI(
    title="Enterprise Knowledge Agent API",
    version="0.1.0",
)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(knowledge_bases_router)
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(qa_router)
