from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.models.database_snapshot import DatabaseSchemaInspection, DatabaseType


@dataclass(frozen=True, slots=True)
class DatabaseConnectionConfig:
    database_type: DatabaseType
    host: str
    port: int
    database: str
    username: str
    password: str
    connection_id: str | None = None
    schema_name: str | None = None
    options: Mapping[str, str] | None = None
    connect_timeout_seconds: int = 5


@dataclass(frozen=True, slots=True)
class DatabaseConnectionInfo:
    database_type: DatabaseType
    host: str
    port: int
    database: str
    server_version: str
    current_user: str
    latency_ms: float


@dataclass(frozen=True, slots=True)
class DatabaseSelectResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


@dataclass(frozen=True, slots=True)
class DatabaseWriteRequest:
    action_type: str
    table_name: str
    sql: str
    parameters: Mapping[str, Any]
    lock_sql: str
    lock_parameters: Mapping[str, Any]
    expected_target_count: int
    max_affected_rows: int
    primary_key_columns: tuple[str, ...]
    expected_before_rows: tuple[Mapping[str, Any], ...] = ()
    expected_values: tuple[tuple[str, Any], ...] = ()
    insert_lookup_sql: str | None = None
    insert_lookup_parameters: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DatabaseWriteResult:
    affected_row_count: int
    before_rows: list[dict[str, Any]]
    after_rows: list[dict[str, Any]]
    verification_passed: bool


class DatabaseQueryError(Exception):
    """A query failed after a database connection was established."""


class BaseDatabaseAdapter(ABC):
    def __init__(self, config: DatabaseConnectionConfig) -> None:
        self.config = config

    @abstractmethod
    def test_connection(self) -> DatabaseConnectionInfo:
        """Open a short-lived connection, run a metadata query, and close it."""

    @abstractmethod
    def inspect_schema(self) -> DatabaseSchemaInspection:
        """Inspect database metadata without reading business-table rows."""

    @abstractmethod
    def execute_select(
        self,
        sql: str,
        max_rows: int,
        parameters: Mapping[str, Any] | None = None,
    ) -> DatabaseSelectResult:
        """Execute one SELECT statement and return a bounded result."""

    @abstractmethod
    def execute_write_transaction(
        self,
        request: DatabaseWriteRequest,
    ) -> DatabaseWriteResult:
        """Execute one bounded write in a transaction and verify its effect."""
