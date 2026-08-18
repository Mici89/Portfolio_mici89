from collections.abc import Mapping
from contextlib import suppress
from datetime import date, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, Connection, Engine
from sqlalchemy.exc import DBAPIError, NoSuchTableError, SQLAlchemyError

from app.adapters.database.base import (
    BaseDatabaseAdapter,
    DatabaseConnectionInfo,
    DatabaseQueryError,
    DatabaseSelectResult,
    DatabaseWriteRequest,
    DatabaseWriteResult,
)
from app.adapters.database.dialect import SqlDialect, get_dialect
from app.core.exceptions import DatabaseConnectionError
from app.models import (
    ColumnSchema,
    DatabaseMetadata,
    DatabaseSchemaInspection,
    DatabaseSource,
    DeclaredRelationship,
    IndexSchema,
    TableSchema,
)


class SQLAlchemyDatabaseAdapter(BaseDatabaseAdapter):
    driver_name: str

    @property
    def dialect(self) -> SqlDialect:
        return get_dialect(self.config.database_type)

    def build_url(self) -> URL:
        return URL.create(
            self.driver_name,
            username=self.config.username,
            password=self.config.password,
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            query=dict(self.config.options or {}),
        )

    def connect_args(self) -> dict[str, Any]:
        return {}

    def _engine(self) -> Engine:
        return create_engine(
            self.build_url(),
            connect_args=self.connect_args(),
            pool_pre_ping=True,
            pool_recycle=900,
        )

    def test_connection(self) -> DatabaseConnectionInfo:
        started_at = perf_counter()
        engine = self._engine()
        try:
            with engine.connect() as connection:
                metadata = self.get_database_info(connection)
            return DatabaseConnectionInfo(
                database_type=self.config.database_type,
                host=self.config.host,
                port=self.config.port,
                database=metadata.name,
                server_version=metadata.server_version,
                current_user=metadata.current_user,
                latency_ms=round((perf_counter() - started_at) * 1000, 2),
            )
        except (SQLAlchemyError, OSError) as exc:
            raise self._translate_connection_error(exc) from None
        finally:
            engine.dispose()

    def inspect_schema(self) -> DatabaseSchemaInspection:
        engine = self._engine()
        try:
            with engine.connect() as connection:
                metadata = self.get_database_info(connection)
                inspector = inspect(connection)
                schema_name = self._effective_schema(inspector)
                tables = self._inspect_tables(inspector, schema_name)
                relationships = self._inspect_relationships(
                    inspector,
                    schema_name,
                    [table.name for table in tables if table.table_type == "BASE TABLE"],
                )
            return DatabaseSchemaInspection(
                source=DatabaseSource(
                    connection_id=self.config.connection_id,
                    database_type=self.config.database_type,
                    host=self.config.host,
                    port=self.config.port,
                    database=self.config.database,
                    schema_name=schema_name,
                ),
                database=metadata,
                tables=tables,
                declared_relationships=relationships,
            )
        except (SQLAlchemyError, OSError) as exc:
            raise self._translate_connection_error(exc) from None
        finally:
            engine.dispose()

    def execute_select(
        self,
        sql: str,
        max_rows: int,
        parameters: Mapping[str, Any] | None = None,
    ) -> DatabaseSelectResult:
        engine = self._engine()
        try:
            with engine.connect() as connection:
                result = connection.execute(text(sql), dict(parameters or {}))
                fetched_rows = list(result.mappings().fetchmany(max_rows + 1))
                columns = [str(column) for column in result]
            return DatabaseSelectResult(
                columns=columns,
                rows=[self._json_safe_row(row) for row in fetched_rows[:max_rows]],
                truncated=len(fetched_rows) > max_rows,
            )
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseQueryError(str(exc)[:1000]) from None
        finally:
            engine.dispose()

    def execute_write_transaction(
        self,
        request: DatabaseWriteRequest,
    ) -> DatabaseWriteResult:
        engine = self._engine()
        try:
            with engine.begin() as connection:
                locked = connection.execute(
                    text(request.lock_sql),
                    dict(request.lock_parameters),
                )
                locked_rows = list(locked.mappings().fetchmany(request.max_affected_rows + 1))
                if len(locked_rows) > request.max_affected_rows:
                    raise DatabaseQueryError(
                        f"实际影响范围超过安全上限 {request.max_affected_rows} 行"
                    )
                if len(locked_rows) != request.expected_target_count:
                    raise DatabaseQueryError("数据在确认前已发生变化，请重新生成操作计划")
                if (
                    request.action_type != "INSERT"
                    and not self._same_target_rows(
                        locked_rows,
                        request.expected_before_rows,
                        request.primary_key_columns,
                    )
                ):
                    raise DatabaseQueryError(
                        "目标行内容在确认前已发生变化，请重新生成操作计划"
                    )

                write_result = connection.execute(text(request.sql), dict(request.parameters))
                affected_row_count = max(int(write_result.rowcount or 0), 0)
                after_rows = self._verification_rows(connection, request, locked_rows)
                if not self._verify_effect(
                    request.action_type,
                    locked_rows,
                    after_rows,
                    request.expected_values,
                ):
                    raise DatabaseQueryError("修改后的数据回查验证失败，事务已回滚")
            return DatabaseWriteResult(
                affected_row_count=affected_row_count,
                before_rows=[self._json_safe_row(row) for row in locked_rows],
                after_rows=[self._json_safe_row(row) for row in after_rows],
                verification_passed=True,
            )
        except DatabaseQueryError:
            raise
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseQueryError(str(exc)[:1000]) from None
        finally:
            engine.dispose()

    def get_database_info(self, connection: Connection) -> DatabaseMetadata:
        current_user = str(connection.execute(text(self.current_user_sql())).scalar_one())
        version = self.server_version(connection)
        return DatabaseMetadata(
            name=self.config.database,
            server_version=version,
            current_user=current_user,
            character_set=self.character_set(connection),
            collation=self.collation(connection),
        )

    def current_user_sql(self) -> str:
        return "SELECT CURRENT_USER"

    def server_version(self, connection: Connection) -> str:
        version_info = connection.dialect.server_version_info
        return ".".join(str(part) for part in version_info) if version_info else "unknown"

    def character_set(self, connection: Connection) -> str:
        return ""

    def collation(self, connection: Connection) -> str:
        return ""

    def _effective_schema(self, inspector: Any) -> str | None:
        if self.config.schema_name:
            return self.config.schema_name
        if self.config.database_type == "oracle":
            return self.config.username.upper()
        return inspector.default_schema_name or self.dialect.default_schema

    def _inspect_tables(self, inspector: Any, schema_name: str | None) -> list[TableSchema]:
        table_names = inspector.get_table_names(schema=schema_name)
        view_names = inspector.get_view_names(schema=schema_name)
        tables = [
            self._inspect_table(inspector, schema_name, table_name, "BASE TABLE")
            for table_name in table_names
        ]
        tables.extend(
            self._inspect_table(inspector, schema_name, view_name, "VIEW")
            for view_name in view_names
        )
        return sorted(tables, key=lambda item: item.name)

    def _inspect_table(
        self,
        inspector: Any,
        schema_name: str | None,
        table_name: str,
        table_type: str,
    ) -> TableSchema:
        column_rows = inspector.get_columns(table_name, schema=schema_name)
        pk = inspector.get_pk_constraint(table_name, schema=schema_name) or {}
        primary_key = [str(name) for name in (pk.get("constrained_columns") or [])]
        index_rows = inspector.get_indexes(table_name, schema=schema_name)
        unique_constraints = inspector.get_unique_constraints(table_name, schema=schema_name)
        unique_columns = {
            str(columns[0])
            for constraint in unique_constraints
            if len(columns := (constraint.get("column_names") or [])) == 1
        }
        indexes: list[IndexSchema] = []
        for index in index_rows:
            columns = [str(name) for name in (index.get("column_names") or []) if name]
            unique = bool(index.get("unique"))
            if unique and len(columns) == 1:
                unique_columns.add(columns[0])
            indexes.append(
                IndexSchema(
                    name=str(index.get("name") or "_unnamed_index"),
                    columns=columns,
                    unique=unique,
                    primary=False,
                    index_type=str(index.get("dialect_options") or "INDEX"),
                )
            )
        if primary_key:
            indexes.append(
                IndexSchema(
                    name=str(pk.get("name") or "PRIMARY"),
                    columns=primary_key,
                    unique=True,
                    primary=True,
                    index_type="PRIMARY KEY",
                )
            )
        comment = ""
        with suppress(NotImplementedError, NoSuchTableError):
            comment = str((inspector.get_table_comment(table_name, schema=schema_name) or {}).get(
                "text"
            ) or "")
        columns = [
            ColumnSchema(
                name=str(column["name"]),
                ordinal_position=index,
                data_type=str(column["type"]),
                column_type=str(column["type"]),
                nullable=bool(column.get("nullable", True)),
                default=self._json_safe_value(column.get("default")),
                comment=str(column.get("comment") or ""),
                extra=self._column_extra(column),
                character_maximum_length=getattr(column["type"], "length", None),
                numeric_precision=getattr(column["type"], "precision", None),
                numeric_scale=getattr(column["type"], "scale", None),
                datetime_precision=None,
                is_primary_key=str(column["name"]) in primary_key,
                is_unique=str(column["name"]) in unique_columns,
            )
            for index, column in enumerate(column_rows, start=1)
        ]
        return TableSchema(
            name=table_name,
            table_type=table_type,
            comment=comment,
            engine=self.config.database_type,
            estimated_row_count=None,
            primary_key=primary_key,
            columns=columns,
            indexes=sorted(indexes, key=lambda item: item.name),
        )

    def _inspect_relationships(
        self,
        inspector: Any,
        schema_name: str | None,
        table_names: list[str],
    ) -> list[DeclaredRelationship]:
        relationships: list[DeclaredRelationship] = []
        for table_name in table_names:
            for foreign_key in inspector.get_foreign_keys(table_name, schema=schema_name):
                options = foreign_key.get("options") or {}
                relationships.append(
                    DeclaredRelationship(
                        constraint_name=str(foreign_key.get("name") or "_unnamed_fk"),
                        source_table=table_name,
                        source_columns=[
                            str(column)
                            for column in (foreign_key.get("constrained_columns") or [])
                        ],
                        target_table=str(foreign_key.get("referred_table") or ""),
                        target_columns=[
                            str(column)
                            for column in (foreign_key.get("referred_columns") or [])
                        ],
                        on_update=str(options.get("onupdate") or "NO ACTION"),
                        on_delete=str(options.get("ondelete") or "NO ACTION"),
                    )
                )
        return sorted(
            relationships,
            key=lambda item: (item.source_table, item.constraint_name),
        )

    def _verification_rows(
        self,
        connection: Connection,
        request: DatabaseWriteRequest,
        before_rows: list[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        if request.action_type == "INSERT":
            if not request.insert_lookup_sql:
                return []
            result = connection.execute(
                text(request.insert_lookup_sql),
                dict(request.insert_lookup_parameters or {}),
            )
            return list(result.mappings())
        if not before_rows or not request.primary_key_columns:
            return []
        predicates: list[str] = []
        parameters: dict[str, Any] = {}
        for row_index, row in enumerate(before_rows):
            parts = []
            for column_index, column in enumerate(request.primary_key_columns):
                bind = f"pk_{row_index}_{column_index}"
                parts.append(f"{self.dialect.quote_identifier(column)} = :{bind}")
                parameters[bind] = row[column]
            predicates.append(f"({' AND '.join(parts)})")
        table = self.dialect.quote_identifier(request.table_name)
        result = connection.execute(
            text(f"SELECT * FROM {table} WHERE {' OR '.join(predicates)}"),
            parameters,
        )
        return list(result.mappings())

    @staticmethod
    def _same_target_rows(
        actual_rows: list[Mapping[str, Any]],
        expected_rows: tuple[Mapping[str, Any], ...],
        primary_key_columns: tuple[str, ...],
    ) -> bool:
        if len(actual_rows) != len(expected_rows):
            return False
        if not primary_key_columns:
            return False

        def identity(row: Mapping[str, Any]) -> tuple[str, ...]:
            return tuple(str(row.get(column)) for column in primary_key_columns)

        actual = {
            identity(row): SQLAlchemyDatabaseAdapter._json_safe_row(row)
            for row in actual_rows
        }
        expected = {
            identity(row): SQLAlchemyDatabaseAdapter._json_safe_row(row)
            for row in expected_rows
        }
        return actual == expected

    @staticmethod
    def _verify_effect(
        action_type: str,
        before_rows: list[Mapping[str, Any]],
        after_rows: list[Mapping[str, Any]],
        expected_values: tuple[tuple[str, Any], ...],
    ) -> bool:
        if action_type == "DELETE":
            return not after_rows
        expected_count = len(before_rows) if action_type == "UPDATE" else 1
        return len(after_rows) == expected_count and all(
            all(
                SQLAlchemyDatabaseAdapter._values_equal(row.get(column), value)
                for column, value in expected_values
            )
            for row in after_rows
        )

    @staticmethod
    def _values_equal(actual: Any, expected: Any) -> bool:
        if actual is None or expected is None:
            return actual is expected
        if isinstance(actual, (date, datetime)):
            return str(actual) == str(expected)
        if isinstance(actual, Decimal):
            return actual == Decimal(str(expected))
        return actual == expected or str(actual) == str(expected)

    @staticmethod
    def _column_extra(column: Mapping[str, Any]) -> str:
        parts = []
        if column.get("autoincrement"):
            parts.append("auto_increment")
        if column.get("identity"):
            parts.append("identity")
        if column.get("computed"):
            parts.append("computed")
        return " ".join(parts)

    @staticmethod
    def _json_safe_value(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    @classmethod
    def _json_safe_row(cls, row: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key): cls._json_safe_value(value) for key, value in row.items()}

    @staticmethod
    def _translate_connection_error(exc: Exception) -> DatabaseConnectionError:
        message = str(exc).lower()
        if any(token in message for token in ("password", "authentication", "login failed")):
            return DatabaseConnectionError(
                "authentication_failed",
                "数据库身份验证失败，请检查用户名和密码",
                http_status_code=401,
            )
        if any(token in message for token in ("unknown database", "does not exist", "ora-12514")):
            return DatabaseConnectionError(
                "database_not_found",
                "指定的数据库或服务不存在",
                http_status_code=404,
            )
        if isinstance(exc, DBAPIError) and exc.connection_invalidated:
            return DatabaseConnectionError(
                "database_unreachable",
                "无法连接到数据库，请检查主机、端口、驱动和网络状态",
                http_status_code=502,
            )
        return DatabaseConnectionError(
            "database_connection_failed",
            f"数据库连接检查失败：{str(exc)[:300]}",
            http_status_code=502,
        )
