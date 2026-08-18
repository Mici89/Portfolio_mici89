from dataclasses import dataclass

from app.models.database_snapshot import DatabaseType


@dataclass(frozen=True, slots=True)
class SqlDialect:
    database_type: DatabaseType
    display_name: str
    identifier_open: str
    identifier_close: str
    default_port: int
    default_schema: str | None
    pagination_instruction: str
    lock_style: str

    def quote_identifier(self, identifier: str) -> str:
        escaped = identifier.replace(self.identifier_close, self.identifier_close * 2)
        return f"{self.identifier_open}{escaped}{self.identifier_close}"

    def limit_select(self, select_sql: str, row_count: int) -> str:
        if self.database_type == "sqlserver":
            if not select_sql.lstrip().upper().startswith("SELECT "):
                raise ValueError("SQL Server pagination requires a SELECT statement")
            prefix_length = len(select_sql) - len(select_sql.lstrip()) + len("SELECT")
            return f"{select_sql[:prefix_length]} TOP ({row_count}){select_sql[prefix_length:]}"
        if self.database_type == "oracle":
            return f"{select_sql} FETCH FIRST {row_count} ROWS ONLY"
        return f"{select_sql} LIMIT {row_count}"

    def lock_select(self, select_sql: str, row_count: int) -> str:
        if self.database_type == "oracle":
            conjunction = " AND " if " WHERE " in select_sql.upper() else " WHERE "
            return f"{select_sql}{conjunction}ROWNUM <= {row_count} FOR UPDATE"
        limited = self.limit_select(select_sql, row_count)
        if self.lock_style == "for_update":
            return f"{limited} FOR UPDATE"
        if self.lock_style == "sqlserver_hint":
            marker = " FROM "
            position = limited.upper().find(marker)
            if position < 0:
                raise ValueError("Unable to add SQL Server lock hint")
            table_start = position + len(marker)
            table_end = limited.find(" ", table_start)
            if table_end < 0:
                table_end = len(limited)
            return (
                f"{limited[:table_end]} WITH (UPDLOCK, ROWLOCK)"
                f"{limited[table_end:]}"
            )
        return limited

    @property
    def prompt_rules(self) -> str:
        quote_example = self.quote_identifier("column_name")
        return (
            f"目标数据库是 {self.display_name}。标识符使用 {quote_example} 形式引用；"
            f"{self.pagination_instruction}"
        )


DIALECTS: dict[DatabaseType, SqlDialect] = {
    "mysql": SqlDialect(
        database_type="mysql",
        display_name="MySQL",
        identifier_open="`",
        identifier_close="`",
        default_port=3306,
        default_schema=None,
        pagination_instruction="限制明细行数时使用 LIMIT",
        lock_style="for_update",
    ),
    "postgresql": SqlDialect(
        database_type="postgresql",
        display_name="PostgreSQL",
        identifier_open='"',
        identifier_close='"',
        default_port=5432,
        default_schema="public",
        pagination_instruction="限制明细行数时使用 LIMIT",
        lock_style="for_update",
    ),
    "sqlserver": SqlDialect(
        database_type="sqlserver",
        display_name="Microsoft SQL Server",
        identifier_open="[",
        identifier_close="]",
        default_port=1433,
        default_schema="dbo",
        pagination_instruction="限制明细行数时使用 SELECT TOP (n)，不要使用 LIMIT",
        lock_style="sqlserver_hint",
    ),
    "oracle": SqlDialect(
        database_type="oracle",
        display_name="Oracle Database",
        identifier_open='"',
        identifier_close='"',
        default_port=1521,
        default_schema=None,
        pagination_instruction="限制明细行数时使用 FETCH FIRST n ROWS ONLY，不要使用 LIMIT",
        lock_style="for_update",
    ),
}


def get_dialect(database_type: DatabaseType) -> SqlDialect:
    return DIALECTS[database_type]
