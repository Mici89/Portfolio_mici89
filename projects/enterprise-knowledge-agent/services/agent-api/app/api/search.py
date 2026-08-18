import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.document_chunk import search_hybrid_chunks
from app.repositories.knowledge_base import get_knowledge_base_by_id
from app.schemas.search import (
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)
from app.services.embedding_service import (
    EmbeddingError,
    generate_embedding,
)
from app.services.pii_redactor import redact_personal_information

router = APIRouter(
    prefix="/knowledge-bases/{knowledge_base_id}/search",
    tags=["Search"],
)


@router.post(
    "",
    response_model=list[KnowledgeSearchResult],
)
def search_knowledge_base(
    knowledge_base_id: uuid.UUID,
    data: KnowledgeSearchRequest,
    db: Annotated[Session, Depends(get_db)],
) -> list[KnowledgeSearchResult]:
    if get_knowledge_base_by_id(db, knowledge_base_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    try:
        query_embedding = generate_embedding(data.query)
    except EmbeddingError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service is unavailable",
        ) from error

    results = search_hybrid_chunks(
        db,
        knowledge_base_id=knowledge_base_id,
        query=data.query,
        query_embedding=query_embedding,
        limit=data.limit,
    )

    return [
        KnowledgeSearchResult(
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=redact_personal_information(chunk.content),
            similarity=distance,
            metadata=chunk.chunk_metadata,
        )
        for chunk, distance in results
    ]
