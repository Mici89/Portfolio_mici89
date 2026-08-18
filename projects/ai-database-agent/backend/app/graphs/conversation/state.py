from typing import Any, TypedDict


class ConversationGraphState(TypedDict, total=False):
    workflow_id: str
    session_id: str
    message: str
    principal: dict[str, Any]
    session: dict[str, Any]
    routing: dict[str, Any]
    context_resolution: dict[str, Any]
    response: dict[str, Any]
