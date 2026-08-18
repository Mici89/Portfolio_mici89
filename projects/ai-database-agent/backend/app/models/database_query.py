from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.conversation import ConversationContextResolution
from app.models.database_understanding import LLMTokenUsage, SqlExecutionResult


class DatabaseQueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NaturalLanguageQueryRequest(DatabaseQueryModel):
    question: str = Field(min_length=2, max_length=2000)


class QuerySessionCreate(DatabaseQueryModel):
    snapshot_id: str = Field(min_length=1, max_length=100)


class QueryTurnCreate(DatabaseQueryModel):
    message: str = Field(min_length=1, max_length=2000)


class QuerySemanticSource(DatabaseQueryModel):
    table_name: str
    catalog_version: int | None = Field(default=None, ge=1)
    review_version: str | None = None
    source: Literal["reviewed", "ai_catalog", "schema_only"]


class QueryFieldMapping(DatabaseQueryModel):
    user_term: str = Field(min_length=1, max_length=120)
    table_name: str
    column_name: str
    semantic_meaning: str = Field(min_length=1, max_length=200)
    source: Literal["reviewed", "ai_catalog", "schema_only"]
    reason: str = Field(default="", max_length=1200)


class QueryFieldReference(DatabaseQueryModel):
    table_name: str = Field(min_length=1, max_length=120)
    column_name: str = Field(min_length=1, max_length=120)


class QueryPredicateBinding(DatabaseQueryModel):
    source_text: str = Field(min_length=1, max_length=200)
    field: QueryFieldReference
    predicate_type: Literal[
        "equals",
        "contains",
        "range",
        "in",
        "comparison",
        "is_null",
    ]


class QuerySemanticFrame(DatabaseQueryModel):
    fact_table: str | None = Field(default=None, max_length=120)
    metric_entity: str = Field(default="", max_length=120)
    aggregation: Literal[
        "detail",
        "count",
        "count_distinct",
        "sum",
        "avg",
        "min",
        "max",
    ] = "detail"
    distinct_key: QueryFieldReference | None = None
    time_scope_kind: Literal["none", "business_event", "entity_lifecycle"] = "none"
    time_field: QueryFieldReference | None = None
    predicate_bindings: list[QueryPredicateBinding] = Field(
        default_factory=list,
        max_length=30,
    )


class QueryIntent(DatabaseQueryModel):
    summary: str = Field(min_length=1, max_length=500)
    metrics: list[str] = Field(default_factory=list, max_length=20)
    dimensions: list[str] = Field(default_factory=list, max_length=20)
    filters: list[str] = Field(default_factory=list, max_length=30)
    detail_requests: list[str] = Field(default_factory=list, max_length=20)
    tables: list[str] = Field(min_length=1, max_length=20)
    field_mappings: list[QueryFieldMapping] = Field(default_factory=list, max_length=60)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    semantic_frame: QuerySemanticFrame = Field(default_factory=QuerySemanticFrame)


class QueryPlan(DatabaseQueryModel):
    intent: QueryIntent
    plan_type: Literal["answer", "evidence"] = "answer"
    sql: str = Field(min_length=1, max_length=20000)
    sql_purpose: str = Field(min_length=1, max_length=500)
    expected_columns: list[str] = Field(default_factory=list, max_length=100)


class QueryResultAssessment(DatabaseQueryModel):
    verdict: Literal["sufficient", "replan"]
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=500)
    issues: list[str] = Field(default_factory=list, max_length=10)
    next_action: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def keep_verdict_consistent(self) -> "QueryResultAssessment":
        if self.verdict == "sufficient" and (self.issues or self.next_action):
            self.verdict = "replan"
            if not self.next_action:
                self.next_action = self.reason
        elif self.verdict == "replan" and not self.next_action:
            self.next_action = self.reason
        return self


class QueryExplanation(DatabaseQueryModel):
    answer: str = Field(min_length=1, max_length=2000)
    observations: list[str] = Field(default_factory=list, max_length=20)
    data_scope: str = Field(default="", max_length=500)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class QueryAttempt(DatabaseQueryModel):
    attempt_number: int = Field(ge=1, le=5)
    plan: QueryPlan
    result: SqlExecutionResult
    assessment: QueryResultAssessment | None = None


class DatabaseQueryRun(DatabaseQueryModel):
    query_id: str
    snapshot_id: str
    database_name: str
    question: str
    created_at: datetime
    status: Literal["completed", "execution_failed"]
    workflow_engine: Literal["legacy", "langgraph"] = "legacy"
    workflow_thread_id: str | None = None
    provider: str
    model: str
    usage: LLMTokenUsage
    semantic_sources: list[QuerySemanticSource] = Field(default_factory=list)
    attempts: list[QueryAttempt] = Field(min_length=1, max_length=5)
    explanation: QueryExplanation


class QueryResultDigest(DatabaseQueryModel):
    columns: list[str] = Field(default_factory=list, max_length=100)
    row_count: int = Field(ge=0)
    sample_rows: list[dict[str, object]] = Field(default_factory=list, max_length=5)
    truncated: bool = False


class QuerySessionTurn(DatabaseQueryModel):
    turn_id: str
    parent_turn_id: str | None = None
    query_id: str
    created_at: datetime
    user_message: str
    context_resolution: ConversationContextResolution | None = None
    status: Literal["completed", "execution_failed"]
    intent: QueryIntent
    sql: str
    result_digest: QueryResultDigest
    result_rows: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    answer: str
    observations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    semantic_sources: list[QuerySemanticSource] = Field(default_factory=list)
    attempts: list[QueryAttempt] = Field(default_factory=list, max_length=5)


class PendingQueryTurn(DatabaseQueryModel):
    query_id: str
    message: str = Field(min_length=1, max_length=2000)
    created_at: datetime
    context_resolution: ConversationContextResolution | None = None


class QuerySession(DatabaseQueryModel):
    session_id: str
    snapshot_id: str
    database_name: str
    connection_id: str | None = None
    title: str
    created_at: datetime
    updated_at: datetime
    active_turn_id: str | None = None
    current_intent: QueryIntent | None = None
    pending_query: PendingQueryTurn | None = None
    turns: list[QuerySessionTurn] = Field(default_factory=list, max_length=200)


class QuerySessionSummary(DatabaseQueryModel):
    session_id: str
    snapshot_id: str
    database_name: str
    connection_id: str | None = None
    title: str
    created_at: datetime
    updated_at: datetime
    turn_count: int = Field(ge=0)


class QueryTurnResponse(DatabaseQueryModel):
    session: QuerySession
    turn: QuerySessionTurn
    run: DatabaseQueryRun
