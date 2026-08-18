from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.conversation import ConversationRoutingDecision
from app.models.database_query import (
    QueryFieldMapping,
    QuerySemanticSource,
    QueryTurnResponse,
)
from app.models.database_understanding import LLMTokenUsage

ActionPrimitiveValue = str | int | float | bool | None
ActionType = Literal["INSERT", "UPDATE", "DELETE"]
ActionStatus = Literal[
    "pending_confirmation",
    "executing",
    "blocked",
    "executed",
    "failed",
    "recovery_required",
    "cancelled",
]


class DatabaseActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationMessageCreate(DatabaseActionModel):
    message: str = Field(min_length=1, max_length=2000)


class ActionLookupReference(DatabaseActionModel):
    lookup_id: str = Field(min_length=1, max_length=100)


ActionValue = ActionPrimitiveValue | ActionLookupReference


class ActionAssignment(DatabaseActionModel):
    column_name: str = Field(min_length=1, max_length=128)
    value: ActionValue
    reason: str = Field(default="", max_length=300)


class ActionCondition(DatabaseActionModel):
    column_name: str = Field(min_length=1, max_length=128)
    operator: Literal[
        "=",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "LIKE",
        "IN",
        "IS NULL",
        "IS NOT NULL",
    ]
    value: ActionValue | list[ActionPrimitiveValue] = None
    reason: str = Field(default="", max_length=300)


class ActionLookupCondition(DatabaseActionModel):
    column_name: str = Field(min_length=1, max_length=128)
    operator: Literal[
        "=",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "LIKE",
        "IN",
        "IS NULL",
        "IS NOT NULL",
    ]
    value: ActionPrimitiveValue | list[ActionPrimitiveValue] = None
    reason: str = Field(default="", max_length=300)


class ActionValueLookup(DatabaseActionModel):
    lookup_id: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=500)
    target_kind: Literal["assignment", "condition"]
    target_column_name: str = Field(min_length=1, max_length=128)
    source_table: str = Field(min_length=1, max_length=128)
    source_value_column: str = Field(min_length=1, max_length=128)
    conditions: list[ActionLookupCondition] = Field(min_length=1, max_length=10)


class DatabaseActionDraft(DatabaseActionModel):
    summary: str = Field(min_length=1, max_length=500)
    action_type: ActionType
    table_name: str = Field(min_length=1, max_length=128)
    assignments: list[ActionAssignment] = Field(default_factory=list, max_length=100)
    conditions: list[ActionCondition] = Field(default_factory=list, max_length=30)
    value_lookups: list[ActionValueLookup] = Field(default_factory=list, max_length=20)
    field_mappings: list[QueryFieldMapping] = Field(default_factory=list, max_length=100)
    expected_effect: str = Field(min_length=1, max_length=500)
    assumptions: list[str] = Field(default_factory=list, max_length=20)


class ActionPreview(DatabaseActionModel):
    matched_row_count: int = Field(ge=0)
    columns: list[str] = Field(default_factory=list, max_length=200)
    sample_rows: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    proposed_rows: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    truncated: bool = False


class ActionSafetyCheck(DatabaseActionModel):
    code: str = Field(min_length=1, max_length=100)
    passed: bool
    message: str = Field(min_length=1, max_length=500)


class ActionLookupResolution(DatabaseActionModel):
    lookup_id: str
    purpose: str
    target_kind: Literal["assignment", "condition"]
    target_column_name: str
    source_table: str
    source_value_column: str
    display_sql: str = Field(min_length=1, max_length=20000)
    status: Literal["resolved", "not_found", "ambiguous", "failed"]
    matched_row_count: int = Field(ge=0)
    truncated: bool = False
    rows: list[dict[str, object]] = Field(default_factory=list, max_length=10)
    resolved_value: ActionPrimitiveValue = None
    message: str = Field(min_length=1, max_length=500)


class ActionPlanningStep(DatabaseActionModel):
    round_number: int = Field(ge=1, le=10)
    summary: str = Field(min_length=1, max_length=500)
    outcome: Literal["resolved", "retrying", "blocked"]
    lookup_resolutions: list[ActionLookupResolution] = Field(default_factory=list)
    message: str = Field(min_length=1, max_length=500)


class ActionExecution(DatabaseActionModel):
    executed_at: datetime
    affected_row_count: int = Field(ge=0)
    verification_passed: bool
    before_rows: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    after_rows: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    message: str = Field(min_length=1, max_length=500)


class DatabaseActionRecord(DatabaseActionModel):
    action_id: str
    session_id: str
    snapshot_id: str
    database_name: str
    user_message: str
    requested_by: str = "unknown"
    requested_by_role: str = "unknown"
    confirmed_by: str | None = None
    cancelled_by: str | None = None
    created_at: datetime
    updated_at: datetime
    status: ActionStatus
    workflow_engine: Literal["legacy", "langgraph"] = "legacy"
    workflow_thread_id: str | None = None
    provider: str
    model: str
    usage: LLMTokenUsage
    draft: DatabaseActionDraft
    parameterized_sql: str = Field(min_length=1, max_length=20000)
    sql_parameters: list[ActionValue] = Field(default_factory=list, max_length=300)
    sql_parameter_values: dict[str, ActionPrimitiveValue] = Field(
        default_factory=dict,
        max_length=300,
    )
    display_sql: str = Field(min_length=1, max_length=20000)
    preview: ActionPreview
    preview_signature: str = Field(default="", max_length=64)
    safety_checks: list[ActionSafetyCheck] = Field(default_factory=list, max_length=20)
    semantic_sources: list[QuerySemanticSource] = Field(default_factory=list)
    planning_steps: list[ActionPlanningStep] = Field(default_factory=list, max_length=10)
    lookup_resolutions: list[ActionLookupResolution] = Field(default_factory=list)
    execution: ActionExecution | None = None
    error: str | None = Field(default=None, max_length=1000)


class ConversationMessageResponse(DatabaseActionModel):
    kind: Literal["query", "action"]
    routing: ConversationRoutingDecision
    workflow_engine: Literal["legacy", "langgraph"] = "legacy"
    workflow_thread_id: str | None = None
    query: QueryTurnResponse | None = None
    action: DatabaseActionRecord | None = None
