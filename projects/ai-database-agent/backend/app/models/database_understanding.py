from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

UnderstandingCompletionStatus = Literal["completed", "best_effort"]
UnderstandingTerminationReason = Literal[
    "schema_sufficient",
    "evidence_resolved",
    "round_limit_reached",
    "sql_generation_stalled",
    "evidence_loop_unavailable",
]


class UnderstandingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SemanticCandidate(UnderstandingModel):
    meaning: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: list[str] = Field(default_factory=list, max_length=8)
    counter_evidence: list[str] = Field(default_factory=list, max_length=5)


class ColumnUnderstanding(UnderstandingModel):
    column_name: str
    status: Literal["inferred", "ambiguous", "unknown"]
    role_candidates: list[SemanticCandidate] = Field(default_factory=list, max_length=3)
    meaning_candidates: list[SemanticCandidate] = Field(default_factory=list, max_length=3)
    sensitivity_candidates: list[SemanticCandidate] = Field(default_factory=list, max_length=3)


class EvidenceRequest(UnderstandingModel):
    request_type: Literal[
        "value_distribution",
        "representative_rows",
        "relationship_match",
        "formula_check",
        "numeric_statistics",
        "date_range",
        "string_pattern",
    ]
    target_columns: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=500)
    priority: Literal["high", "medium", "low"] = "medium"


class TableUnderstandingPayload(UnderstandingModel):
    summary: str = Field(max_length=1000)
    status: Literal["inferred", "ambiguous", "unknown"]
    table_candidates: list[SemanticCandidate] = Field(default_factory=list, max_length=3)
    table_role_candidates: list[SemanticCandidate] = Field(default_factory=list, max_length=3)
    grain_candidates: list[SemanticCandidate] = Field(default_factory=list, max_length=3)
    columns: list[ColumnUnderstanding]
    evidence_requests: list[EvidenceRequest] = Field(default_factory=list, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=8)


class LLMTokenUsage(UnderstandingModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class GeneratedSqlQuery(UnderstandingModel):
    request_index: int = Field(ge=0)
    purpose: str = Field(min_length=1, max_length=500)
    sql: str = Field(min_length=1, max_length=10000)


class SqlGenerationPayload(UnderstandingModel):
    queries: list[GeneratedSqlQuery] = Field(default_factory=list, max_length=12)


class SqlExecutionResult(UnderstandingModel):
    status: Literal["executed", "rejected", "failed"]
    statement_type: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    returned_row_count: int = Field(default=0, ge=0)
    truncated: bool = False
    error: str | None = Field(default=None, max_length=1000)


class EvidenceStep(UnderstandingModel):
    round_number: int = Field(ge=1)
    request: EvidenceRequest
    query: GeneratedSqlQuery
    result: SqlExecutionResult


class TableUnderstandingRun(UnderstandingModel):
    run_id: str
    snapshot_id: str
    table_name: str
    created_at: datetime
    provider: str
    model: str
    prompt_version: str
    workflow_engine: Literal["legacy", "langgraph"] = "legacy"
    workflow_thread_id: str | None = None
    evidence_scope: Literal[
        "schema_only",
        "schema_and_profile",
        "schema_and_query_evidence",
    ]
    usage: LLMTokenUsage
    analysis: TableUnderstandingPayload
    evidence_steps: list[EvidenceStep] = Field(default_factory=list)
    completion_status: UnderstandingCompletionStatus = "completed"
    termination_reason: UnderstandingTerminationReason = "schema_sufficient"
    evidence_round_count: int = Field(default=0, ge=0, le=10)
    max_evidence_rounds: int = Field(default=3, ge=1, le=10)
    deferred_evidence_requests: list[EvidenceRequest] = Field(
        default_factory=list,
        max_length=12,
    )
    catalog_entry_id: str | None = None
    catalog_version: int | None = Field(default=None, ge=1)
