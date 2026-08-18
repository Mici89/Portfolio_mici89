import re

from starlette.concurrency import run_in_threadpool

from app.adapters.database.base import (
    BaseDatabaseAdapter,
    DatabaseQueryError,
)
from app.models import GeneratedSqlQuery, SqlExecutionResult

SQL_KEYWORD_PATTERN = re.compile(r"[A-Za-z]+")


class SQLExecutionAgent:
    def __init__(
        self,
        database_adapter: BaseDatabaseAdapter,
        *,
        max_rows: int = 50,
    ) -> None:
        self.database_adapter = database_adapter
        self.max_rows = max_rows

    async def execute(self, query: GeneratedSqlQuery) -> SqlExecutionResult:
        statement_type = self.statement_type(query.sql)
        if statement_type != "SELECT":
            return SqlExecutionResult(
                status="rejected",
                statement_type=statement_type,
                error=f"当前只允许执行SELECT，收到：{statement_type or 'UNKNOWN'}",
            )
        try:
            result = await run_in_threadpool(
                self.database_adapter.execute_select,
                query.sql,
                self.max_rows,
            )
        except DatabaseQueryError as exc:
            return SqlExecutionResult(
                status="failed",
                statement_type=statement_type,
                error=str(exc),
            )
        return SqlExecutionResult(
            status="executed",
            statement_type=statement_type,
            columns=result.columns,
            rows=result.rows,
            returned_row_count=len(result.rows),
            truncated=result.truncated,
        )

    @classmethod
    def statement_type(cls, sql: str) -> str:
        remaining = sql.lstrip()
        while remaining:
            if remaining.startswith("--") or remaining.startswith("#"):
                line_end = remaining.find("\n")
                if line_end < 0:
                    return ""
                remaining = remaining[line_end + 1 :].lstrip()
                continue
            if remaining.startswith("/*"):
                comment_end = remaining.find("*/", 2)
                if comment_end < 0:
                    return ""
                remaining = remaining[comment_end + 2 :].lstrip()
                continue
            break
        match = SQL_KEYWORD_PATTERN.match(remaining)
        return match.group(0).upper() if match else ""
