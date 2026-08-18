import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.state import AgentState
from app.core.config import get_settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk import search_hybrid_chunks
from app.services.embedding_service import generate_embedding
from app.services.pii_redactor import redact_personal_information


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "在当前知识库执行混合检索。适合事实查询、规则查询和重新表述问题后的补充检索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "用于检索的具体查询语句"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ready_documents",
            "description": "列出当前知识库中已完成索引的文档。适合需要定位年份、部门或具体制度文件时使用。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_chunk",
            "description": "读取当前知识库某个文档的指定切片，用于补足上下文或核对已经检索到的资料。",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "检索结果返回的文档 ID"},
                    "chunk_index": {"type": "integer", "minimum": 0},
                },
                "required": ["document_id", "chunk_index"],
                "additionalProperties": False,
            },
        },
    },
]


def _source_payload(item: Any) -> dict[str, Any]:
    return {
        "source_number": item.source_number,
        "document_id": str(item.document_id),
        "chunk_index": item.chunk_index,
        "content": item.content,
        "similarity": round(item.similarity, 4),
        "metadata": item.metadata,
    }


def _add_chunk_to_state(
    state: AgentState,
    *,
    chunk: DocumentChunk,
    similarity: float,
) -> dict[str, Any]:
    evidence = state.add_evidence(
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        content=redact_personal_information(chunk.content),
        similarity=similarity,
        metadata=chunk.chunk_metadata,
    )
    return _source_payload(evidence)


def _search_knowledge_base(
    db: Session,
    state: AgentState,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {"error": "query must not be empty"}

    top_k = min(max(int(arguments.get("top_k", state.top_k)), 1), 10)
    embedding = generate_embedding(query)
    results = search_hybrid_chunks(
        db,
        knowledge_base_id=state.knowledge_base_id,
        query=query,
        query_embedding=embedding,
        limit=top_k,
    )
    sources = [
        _add_chunk_to_state(state, chunk=chunk, similarity=score)
        for chunk, score in results
        if score >= get_settings().retrieval_min_similarity
    ]
    return {
        "query": query,
        "sources": sources,
        "sufficient_evidence": bool(sources),
    }


def _list_ready_documents(db: Session, state: AgentState) -> dict[str, Any]:
    documents = db.scalars(
        select(Document)
        .where(
            Document.knowledge_base_id == state.knowledge_base_id,
            Document.status == "ready",
        )
        .order_by(Document.created_at.desc())
    ).all()
    return {
        "documents": [
            {"document_id": str(document.id), "file_name": document.file_name}
            for document in documents
        ]
    }


def _get_document_chunk(
    db: Session,
    state: AgentState,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    try:
        document_id = uuid.UUID(str(arguments.get("document_id", "")))
        chunk_index = int(arguments.get("chunk_index"))
    except (TypeError, ValueError):
        return {"error": "document_id and chunk_index are required"}

    chunk = db.scalar(
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.id == document_id,
            Document.knowledge_base_id == state.knowledge_base_id,
            DocumentChunk.chunk_index == chunk_index,
        )
    )
    if chunk is None:
        return {"error": "chunk not found in the current knowledge base"}

    return {"source": _add_chunk_to_state(state, chunk=chunk, similarity=0.0)}


def execute_tool(
    *,
    db: Session,
    state: AgentState,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if tool_name == "search_knowledge_base":
        result = _search_knowledge_base(db, state, arguments)
    elif tool_name == "list_ready_documents":
        result = _list_ready_documents(db, state)
    elif tool_name == "get_document_chunk":
        result = _get_document_chunk(db, state, arguments)
    else:
        result = {"error": f"unknown tool: {tool_name}"}

    state.tool_calls.append({"name": tool_name, "arguments": arguments, "result": result})
    return result


def tool_result_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False)
