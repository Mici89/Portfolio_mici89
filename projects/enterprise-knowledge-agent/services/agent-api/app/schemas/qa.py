import uuid
from typing import Any

from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


class AnswerSource(BaseModel):
    source_number: int
    document_id: uuid.UUID
    chunk_index: int
    content: str
    similarity: float
    metadata: dict[str, Any] | None = None


class AgentTrace(BaseModel):
    intent: str | None
    steps: int
    tools: list[str]


class QuestionResponse(BaseModel):
    answer: str
    sources: list[AnswerSource]
    agent_trace: AgentTrace
