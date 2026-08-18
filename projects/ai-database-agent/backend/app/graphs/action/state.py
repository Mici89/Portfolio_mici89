from typing import Any, Literal, TypedDict


class ActionGraphState(TypedDict, total=False):
    action_id: str
    session_id: str
    message: str
    principal: dict[str, Any]
    conversation_context: dict[str, object] | None
    snapshot: dict[str, Any]
    semantic_payload: dict[str, object]
    semantic_sources: list[dict[str, Any]]
    field_sources: list[dict[str, str]]
    field_meanings: list[dict[str, str]]
    planning_round: int
    max_planning_rounds: int
    planning_context: dict[str, object] | None
    planning_steps: list[dict[str, Any]]
    draft: dict[str, Any]
    lookup_resolutions: list[dict[str, Any]]
    provider: str
    model: str
    usage: dict[str, int]
    validation_error: str | None
    record: dict[str, Any]
    confirmation: dict[str, Any]
    confirmation_decision: Literal["confirm", "cancel"]
    next_step: Literal[
        "retry",
        "resolve",
        "preview",
        "blocked",
        "wait",
        "execute",
        "finish",
    ]
