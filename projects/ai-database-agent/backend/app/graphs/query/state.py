from typing import Any, Literal, TypedDict


class QueryGraphState(TypedDict, total=False):
    query_id: str
    snapshot: dict[str, Any]
    question: str
    conversation_context: dict[str, object] | None
    semantic_payload: dict[str, object]
    semantic_sources: list[dict[str, Any]]
    field_sources: list[dict[str, str]]
    field_meanings: list[dict[str, str]]
    attempts: list[dict[str, Any]]
    attempt_number: int
    max_attempts: int
    repair_context: dict[str, object] | None
    plan: dict[str, Any]
    result: dict[str, Any]
    assessment: dict[str, Any]
    explanation: dict[str, Any]
    provider: str
    model: str
    usage: dict[str, int]
    used_semantic_sources: list[dict[str, Any]]
    next_step: Literal["retry", "assess", "explain", "finish"]
