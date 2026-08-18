import pytest

from app.adapters.database import DatabaseSelectResult
from app.agents.sql_execution import SQLExecutionAgent
from app.models import GeneratedSqlQuery


class RecordingAdapter:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute_select(self, sql: str, max_rows: int) -> DatabaseSelectResult:
        self.executed_sql.append(sql)
        return DatabaseSelectResult(
            columns=["value"],
            rows=[{"value": 1}],
            truncated=False,
        )


@pytest.mark.asyncio
async def test_select_is_executed() -> None:
    adapter = RecordingAdapter()
    agent = SQLExecutionAgent(adapter)  # type: ignore[arg-type]
    query = GeneratedSqlQuery(
        request_index=0,
        purpose="读取样本",
        sql="/* evidence */ SELECT `value` FROM `sample` LIMIT 10",
    )

    result = await agent.execute(query)

    assert result.status == "executed"
    assert result.statement_type == "SELECT"
    assert result.rows == [{"value": 1}]
    assert adapter.executed_sql == [query.sql]


@pytest.mark.asyncio
async def test_non_select_is_rejected_before_database_execution() -> None:
    adapter = RecordingAdapter()
    agent = SQLExecutionAgent(adapter)  # type: ignore[arg-type]
    query = GeneratedSqlQuery(
        request_index=0,
        purpose="错误写操作",
        sql="UPDATE `sample` SET `value` = 2",
    )

    result = await agent.execute(query)

    assert result.status == "rejected"
    assert result.statement_type == "UPDATE"
    assert adapter.executed_sql == []
