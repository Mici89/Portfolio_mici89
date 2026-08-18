from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationRoutingDecision(ConversationModel):
    kind: Literal["query", "action"]
    context_mode: Literal["standalone", "refine", "switch"]
    standalone_intent_complete: bool
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=500)
    omitted_references: list[str] = Field(default_factory=list, max_length=20)
    added_metrics: list[str] = Field(default_factory=list, max_length=20)
    added_dimensions: list[str] = Field(default_factory=list, max_length=20)
    added_filters: list[str] = Field(default_factory=list, max_length=30)
    detail_requests: list[str] = Field(default_factory=list, max_length=20)
    removed_metrics: list[str] = Field(default_factory=list, max_length=20)
    removed_dimensions: list[str] = Field(default_factory=list, max_length=20)
    removed_filters: list[str] = Field(default_factory=list, max_length=30)
    replace_metrics: bool = False
    replace_dimensions: bool = False
    replace_filters: bool = False


class ConversationContextResolution(ConversationModel):
    mode: Literal["standalone", "refine", "switch"]
    reason: str = Field(min_length=1, max_length=500)
    inherited_metrics: list[str] = Field(default_factory=list, max_length=20)
    inherited_dimensions: list[str] = Field(default_factory=list, max_length=20)
    inherited_filters: list[str] = Field(default_factory=list, max_length=30)
    inherited_tables: list[str] = Field(default_factory=list, max_length=20)
    added_metrics: list[str] = Field(default_factory=list, max_length=20)
    added_dimensions: list[str] = Field(default_factory=list, max_length=20)
    added_filters: list[str] = Field(default_factory=list, max_length=30)
    detail_requests: list[str] = Field(default_factory=list, max_length=20)
    required_metrics: list[str] = Field(default_factory=list, max_length=20)
    required_dimensions: list[str] = Field(default_factory=list, max_length=20)
    required_filters: list[str] = Field(default_factory=list, max_length=30)
    required_tables: list[str] = Field(default_factory=list, max_length=20)

