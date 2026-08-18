from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.database_snapshot import DeclaredRelationship
from app.models.database_understanding import (
    EvidenceStep,
    TableUnderstandingPayload,
)

ReviewScope = Literal["table", "fields"]
ReviewStatus = Literal["partially_reviewed", "fully_reviewed"]
ReviewDecisionType = Literal["confirmed", "edited"]


class SemanticReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TableReviewInput(SemanticReviewModel):
    reviewed_meaning: str = Field(min_length=1, max_length=120)
    reviewed_summary: str = Field(min_length=1, max_length=1000)
    source_candidate_index: int | None = Field(default=0, ge=0, le=2)
    note: str = Field(default="", max_length=500)


class FieldReviewInput(SemanticReviewModel):
    column_name: str = Field(min_length=1, max_length=128)
    reviewed_meaning: str = Field(min_length=1, max_length=120)
    reviewed_description: str = Field(default="", max_length=500)
    source_candidate_index: int | None = Field(default=0, ge=0, le=2)
    note: str = Field(default="", max_length=500)


class CatalogReviewCreate(SemanticReviewModel):
    source_catalog_version: int = Field(ge=1)
    scope: ReviewScope
    reviewer: str = Field(min_length=1, max_length=120)
    table_decision: TableReviewInput | None = None
    field_decisions: list[FieldReviewInput] = Field(
        default_factory=list,
        max_length=500,
    )
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_decisions(self) -> "CatalogReviewCreate":
        if self.scope == "fields" and not self.field_decisions:
            raise ValueError("字段审核至少需要选择一个字段")
        names = [decision.column_name for decision in self.field_decisions]
        if len(names) != len(set(names)):
            raise ValueError("一次审核中不能重复提交同一字段")
        return self


class TableReviewDecision(SemanticReviewModel):
    decision: ReviewDecisionType
    original_meaning: str
    original_summary: str
    reviewed_meaning: str
    reviewed_summary: str
    source_candidate_index: int | None = None
    note: str = ""


class FieldReviewDecision(SemanticReviewModel):
    column_name: str
    decision: ReviewDecisionType
    original_meaning: str
    original_description: str
    reviewed_meaning: str
    reviewed_description: str
    source_candidate_index: int | None = None
    note: str = ""


class CatalogReviewRevision(SemanticReviewModel):
    review_id: str
    catalog_entry_id: str
    database_name: str
    table_name: str
    source_catalog_version: int = Field(ge=1)
    revision: int = Field(ge=1)
    display_version: str
    schema_fingerprint: str
    created_at: datetime
    reviewer: str
    scope: ReviewScope
    status: ReviewStatus
    reviewed_field_count: int = Field(ge=0)
    total_field_count: int = Field(ge=0)
    submitted_field_names: list[str] = Field(default_factory=list)
    table_decision: TableReviewDecision | None = None
    field_decisions: list[FieldReviewDecision] = Field(default_factory=list)
    note: str = ""
    reviewed_analysis: TableUnderstandingPayload


class CatalogEvidenceBundle(SemanticReviewModel):
    catalog_entry_id: str
    catalog_version: int = Field(ge=1)
    table_name: str
    source_run_id: str
    generated_at: datetime
    declared_relationships: list[DeclaredRelationship] = Field(default_factory=list)
    evidence_steps: list[EvidenceStep] = Field(default_factory=list)
