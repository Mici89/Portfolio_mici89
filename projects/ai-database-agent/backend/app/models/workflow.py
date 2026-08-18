from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WorkflowKind = Literal["understanding", "query", "action", "conversation"]
WorkflowRuntimeStatus = Literal[
    "running",
    "interrupted",
    "failed",
    "completed",
]


class WorkflowStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    workflow_kind: WorkflowKind
    status: WorkflowRuntimeStatus
    current_node: str | None = None
    completed_nodes: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0)
    can_resume: bool = False
    awaiting_input: bool = False
    interrupt_payload: object | None = None
    error: str | None = Field(default=None, max_length=2000)
