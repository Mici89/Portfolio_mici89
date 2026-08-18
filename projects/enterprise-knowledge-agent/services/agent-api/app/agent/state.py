import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvidence:
    source_number: int
    document_id: uuid.UUID
    chunk_index: int
    content: str
    similarity: float
    metadata: dict[str, Any] | None


@dataclass
class AgentState:
    question: str
    knowledge_base_id: uuid.UUID
    top_k: int
    phase: str = "planning"
    intent: str | None = None
    plan: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[AgentEvidence] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    step_count: int = 0

    def add_evidence(
        self,
        *,
        document_id: uuid.UUID,
        chunk_index: int,
        content: str,
        similarity: float,
        metadata: dict[str, Any] | None,
    ) -> AgentEvidence:
        for item in self.evidence:
            if item.document_id == document_id and item.chunk_index == chunk_index:
                return item

        item = AgentEvidence(
            source_number=len(self.evidence) + 1,
            document_id=document_id,
            chunk_index=chunk_index,
            content=content,
            similarity=similarity,
            metadata=metadata,
        )
        self.evidence.append(item)
        return item
