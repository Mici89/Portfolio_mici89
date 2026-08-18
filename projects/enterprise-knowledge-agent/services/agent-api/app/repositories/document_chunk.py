import re
import uuid
from collections.abc import Sequence

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.text_splitter import StructuredChunk


def replace_document_chunks(
    db: Session,
    *,
    document: Document,
    chunks: list[StructuredChunk] | list[str],
    embeddings: list[list[float]],
) -> Sequence[DocumentChunk]:
    if len(chunks) != len(embeddings):
        raise ValueError("Chunk count does not match embedding count")

    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    chunk_models = []
    for index, item in enumerate(chunks):
        if isinstance(item, str):
            content = item
            metadata = None
        else:
            content = item.content
            metadata = item.metadata
        chunk_models.append(
            DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                content=content,
                character_count=len(content),
                chunk_metadata=metadata,
                embedding=embeddings[index],
            )
        )

    db.add_all(chunk_models)
    document.status = "ready"
    document.error_message = None
    db.commit()
    for chunk in chunk_models:
        db.refresh(chunk)
    return chunk_models


def _query_terms(query: str) -> list[str]:
    terms = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]+", query.lower())
    if not terms:
        return [query.strip().lower()]
    return list(dict.fromkeys(terms))[:8]


def _lexical_score(query: str, content: str) -> float:
    query = query.lower().strip()
    content = content.lower()
    if not query or not content:
        return 0.0
    score = 1.0 if query in content else 0.0
    terms = _query_terms(query)
    matched = sum(term in content for term in terms)
    return min(1.0, score * 0.6 + matched / max(1, len(terms)) * 0.4)


def search_hybrid_chunks(
    db: Session,
    *,
    knowledge_base_id: uuid.UUID,
    query: str,
    query_embedding: list[float],
    limit: int = 5,
    candidate_limit: int = 20,
) -> Sequence[tuple[DocumentChunk, float]]:
    distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
    base_filter = (
        Document.knowledge_base_id == knowledge_base_id,
        DocumentChunk.embedding.is_not(None),
    )

    vector_rows = db.execute(
        select(DocumentChunk, distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(*base_filter)
        .order_by(distance)
        .limit(candidate_limit)
    ).all()

    terms = _query_terms(query)
    lexical_conditions = [DocumentChunk.content.ilike(f"%{term}%") for term in terms]
    lexical_rows = db.scalars(
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(*base_filter, or_(*lexical_conditions))
        .limit(candidate_limit)
    ).all()

    candidates: dict[uuid.UUID, tuple[DocumentChunk, float, int | None, float]] = {}
    for rank, row in enumerate(vector_rows, start=1):
        candidates[row.DocumentChunk.id] = (
            row.DocumentChunk,
            float(row.distance),
            rank,
            0.0,
        )
    for chunk in lexical_rows:
        previous = candidates.get(chunk.id)
        candidates[chunk.id] = (
            chunk,
            previous[1] if previous else 1.0,
            previous[2] if previous else None,
            _lexical_score(query, chunk.content),
        )

    reranked: list[tuple[DocumentChunk, float]] = []
    for chunk, distance_value, vector_rank, lexical_score in candidates.values():
        vector_similarity = max(0.0, 1.0 - distance_value)
        rrf = 1 / (60 + vector_rank) if vector_rank else 0.0
        # Lightweight reranker: semantic score + lexical match + reciprocal rank fusion.
        final_score = 0.70 * vector_similarity + 0.20 * lexical_score + 0.10 * min(1.0, rrf * 60)
        reranked.append((chunk, final_score))

    reranked.sort(key=lambda item: item[1], reverse=True)
    return reranked[:limit]


def search_similar_chunks(
    db: Session,
    *,
    knowledge_base_id: uuid.UUID,
    query_embedding: list[float],
    limit: int = 5,
) -> Sequence[tuple[DocumentChunk, float]]:
    """Compatibility wrapper for callers that do not provide raw query text."""
    distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
    statement = (
        select(DocumentChunk, distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.knowledge_base_id == knowledge_base_id,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(limit)
    )
    rows = db.execute(statement).all()
    return [(row.DocumentChunk, float(row.distance)) for row in rows]
