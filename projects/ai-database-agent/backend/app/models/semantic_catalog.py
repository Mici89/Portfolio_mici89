from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.database_snapshot import DeclaredRelationship
from app.models.database_understanding import (
    EvidenceRequest,
    TableUnderstandingPayload,
    UnderstandingCompletionStatus,
    UnderstandingTerminationReason,
)


class SemanticCatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogEvidenceSummary(SemanticCatalogModel):
    database_query_rounds: int = Field(ge=0, le=10)
    generated_query_count: int = Field(ge=0)
    executed_query_count: int = Field(ge=0)
    rejected_query_count: int = Field(ge=0)
    failed_query_count: int = Field(ge=0)


class SemanticCatalogEntry(SemanticCatalogModel):
    catalog_entry_id: str
    version: int = Field(ge=1)
    status: Literal["active"] = "active"
    database_name: str
    connection_id: str | None = None
    table_name: str
    schema_fingerprint: str
    snapshot_id: str
    source_run_id: str
    first_published_at: datetime
    published_at: datetime
    completion_status: UnderstandingCompletionStatus
    termination_reason: UnderstandingTerminationReason
    prompt_version: str
    provider: str
    model: str
    evidence_summary: CatalogEvidenceSummary
    deferred_evidence_requests: list[EvidenceRequest] = Field(default_factory=list)
    declared_relationships: list[DeclaredRelationship] = Field(default_factory=list)
    analysis: TableUnderstandingPayload
