from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.adapters.database.base import DatabaseConnectionConfig


class DatabaseConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    database_type: Literal["mysql", "postgresql", "sqlserver", "oracle"] = "mysql"
    label: str = Field(default="", max_length=128)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=3306, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr
    schema_name: str | None = Field(default=None, max_length=128)
    options: dict[str, str] = Field(default_factory=dict)
    write_username: str | None = Field(default=None, min_length=1, max_length=128)
    write_password: SecretStr | None = None
    connect_timeout_seconds: int = Field(default=5, ge=1, le=30)

    @field_validator("host", "database", "username")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise ValueError("must not contain control characters")
        return value

    @model_validator(mode="after")
    def validate_write_credentials(self) -> "DatabaseConnectionRequest":
        if (self.write_username is None) != (self.write_password is None):
            raise ValueError("write_username和write_password必须同时提供")
        return self

    def to_config(self) -> DatabaseConnectionConfig:
        return DatabaseConnectionConfig(
            database_type=self.database_type,
            host=self.host,
            port=self.port,
            database=self.database,
            username=self.username,
            password=self.password.get_secret_value(),
            schema_name=self.schema_name,
            options=self.options,
            connect_timeout_seconds=self.connect_timeout_seconds,
        )


class DatabaseConnectionResponse(BaseModel):
    status: Literal["connected"] = "connected"
    connection_id: str | None = None
    database_type: Literal["mysql", "postgresql", "sqlserver", "oracle"]
    host: str
    port: int
    database: str
    server_version: str
    current_user: str
    latency_ms: float


class DatabaseConnectionProfileResponse(BaseModel):
    connection_id: str
    label: str
    database_type: Literal["mysql", "postgresql", "sqlserver", "oracle"]
    host: str
    port: int
    database: str
    schema_name: str | None
    username: str
    has_separate_write_credential: bool
