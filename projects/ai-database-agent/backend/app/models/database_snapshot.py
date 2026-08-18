from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DatabaseType = Literal["mysql", "postgresql", "sqlserver", "oracle"]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatabaseSource(DomainModel):
    connection_id: str | None = None
    database_type: DatabaseType
    host: str
    port: int
    database: str
    schema_name: str | None = None


class DatabaseMetadata(DomainModel):
    name: str
    server_version: str
    current_user: str
    character_set: str
    collation: str


class ColumnSchema(DomainModel):
    name: str
    ordinal_position: int
    data_type: str
    column_type: str
    nullable: bool
    default: Any = None
    comment: str = ""
    extra: str = ""
    character_maximum_length: int | None = None
    numeric_precision: int | None = None
    numeric_scale: int | None = None
    datetime_precision: int | None = None
    is_primary_key: bool = False
    is_unique: bool = False


class IndexSchema(DomainModel):
    name: str
    columns: list[str]
    unique: bool
    primary: bool
    index_type: str


class TableSchema(DomainModel):
    name: str
    table_type: Literal["BASE TABLE", "VIEW", "SYSTEM VIEW"]
    comment: str = ""
    engine: str | None = None
    estimated_row_count: int | None = Field(default=None, ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    primary_key: list[str] = Field(default_factory=list)
    columns: list[ColumnSchema] = Field(default_factory=list)
    indexes: list[IndexSchema] = Field(default_factory=list)


class DeclaredRelationship(DomainModel):
    constraint_name: str
    source_table: str
    source_columns: list[str]
    target_table: str
    target_columns: list[str]
    on_update: str
    on_delete: str
    relationship_source: Literal["declared_foreign_key"] = "declared_foreign_key"
    confidence: Literal[1.0] = 1.0


class DatabaseSchemaInspection(DomainModel):
    source: DatabaseSource
    database: DatabaseMetadata
    tables: list[TableSchema]
    declared_relationships: list[DeclaredRelationship]


class ScanStatistics(DomainModel):
    table_count: int = Field(ge=0)
    view_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    foreign_key_count: int = Field(ge=0)
    index_count: int = Field(ge=0)


class DatabaseSnapshot(DomainModel):
    snapshot_id: str
    captured_at: datetime
    source: DatabaseSource
    database: DatabaseMetadata
    tables: list[TableSchema]
    declared_relationships: list[DeclaredRelationship]
    scan_statistics: ScanStatistics
