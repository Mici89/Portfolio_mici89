from datetime import datetime

from pydantic import Field

from app.models.database_snapshot import DatabaseType, DomainModel


class DatabaseConnectionProfile(DomainModel):
    connection_id: str
    label: str
    database_type: DatabaseType
    host: str
    port: int
    database: str
    schema_name: str | None = None
    username: str
    credential_ref: str
    write_username: str | None = None
    write_credential_ref: str | None = None
    options: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
