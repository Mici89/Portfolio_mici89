from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CatalogBuildModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogBuildItem(CatalogBuildModel):
    table_name: str
    status: Literal["pending", "running", "completed", "skipped", "failed"]
    run_id: str | None = None
    catalog_entry_id: str | None = None
    catalog_version: int | None = Field(default=None, ge=1)
    error: str | None = Field(default=None, max_length=1000)


class CatalogBuildJob(CatalogBuildModel):
    job_id: str
    snapshot_id: str
    database_name: str
    status: Literal["queued", "running", "completed", "partial_failed"]
    created_at: datetime
    updated_at: datetime
    current_table: str | None = None
    total_tables: int = Field(ge=0)
    processed_tables: int = Field(ge=0)
    completed_tables: int = Field(ge=0)
    skipped_tables: int = Field(ge=0)
    failed_tables: int = Field(ge=0)
    items: list[CatalogBuildItem] = Field(default_factory=list)
