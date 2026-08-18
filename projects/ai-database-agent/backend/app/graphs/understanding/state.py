from typing import Any, Literal, TypedDict


class UnderstandingGraphState(TypedDict, total=False):
    run_id: str
    snapshot: dict[str, Any]
    table_name: str
    evidence_steps: list[dict[str, Any]]
    evidence_round_count: int
    max_evidence_rounds: int
    analysis: dict[str, Any]
    pending_requests: list[dict[str, Any]]
    generated_queries: list[dict[str, Any]]
    provider: str
    model: str
    usage: dict[str, int]
    completion_status: Literal["completed", "best_effort"]
    termination_reason: str
    deferred_evidence_requests: list[dict[str, Any]]
    evidence_scope: Literal["schema_only", "schema_and_query_evidence"]
    next_step: Literal["generate", "execute", "analyze", "finalize"]
