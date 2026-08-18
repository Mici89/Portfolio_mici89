from typing import Any

import pytest

from app.adapters.llm.base import LLMJsonResult
from app.agents.database_query import DatabaseQueryAgent
from app.models import (
    LLMTokenUsage,
    QuerySemanticSource,
    SqlExecutionResult,
)
from tests.unit.test_semantic_review import make_snapshot


class QueryLLM:
    def __init__(self) -> None:
        self.planning_calls = 0

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> LLMJsonResult:
        del system_prompt
        if user_payload["task"] == "explain_database_query_result":
            content = {
                "answer": "工资总额为1000元。",
                "observations": ["共返回1行聚合结果。"],
                "data_scope": "当前数据库全部记录。",
                "limitations": [],
            }
        elif user_payload["task"] == "assess_database_query_result":
            content = {
                "verdict": "sufficient",
                "confidence": 0.98,
                "reason": "结果列和聚合粒度能够直接回答问题。",
                "issues": [],
                "next_action": "",
            }
        else:
            self.planning_calls += 1
            content = {
                "intent": {
                    "summary": "统计工资总额",
                    "metrics": ["工资总额"],
                    "dimensions": [],
                    "filters": [],
                    "tables": ["rs_gzff"],
                    "field_mappings": [
                        {
                            "user_term": "实发工资",
                            "table_name": "rs_gzff",
                            "column_name": "gz",
                            "semantic_meaning": "错误的模型输出",
                            "source": "schema_only",
                            "reason": "字段语义匹配",
                        }
                    ],
                    "assumptions": [],
                },
                "sql": "SELECT SUM(`gz`) AS total_gz FROM `rs_gzff`",
                "sql_purpose": "统计工资总额",
                "expected_columns": ["total_gz"],
            }
        return LLMJsonResult(
            content=content,
            provider="fake",
            model="fake-query-model",
            usage=LLMTokenUsage(total_tokens=10),
        )


class AliasedTableLLM(QueryLLM):
    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> LLMJsonResult:
        result = await super().generate_json(
            system_prompt=system_prompt,
            user_payload=user_payload,
        )
        if user_payload["task"] == "plan_and_generate_read_only_query":
            result.content["intent"]["tables"] = ["rs_gzff AS payroll"]
            result.content["intent"]["field_mappings"][0]["table_name"] = "rs_gzff payroll"
            result.content["sql"] = "SELECT SUM(payroll.`gz`) AS total_gz FROM `rs_gzff` AS payroll"
        return result


class SuccessfulExecutor:
    async def execute(self, _query) -> SqlExecutionResult:
        return SqlExecutionResult(
            status="executed",
            statement_type="SELECT",
            columns=["total_gz"],
            rows=[{"total_gz": "1000.00"}],
            returned_row_count=1,
        )


class RepairingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, _query) -> SqlExecutionResult:
        self.calls += 1
        if self.calls == 1:
            return SqlExecutionResult(
                status="failed",
                statement_type="SELECT",
                error="Unknown column",
            )
        return SqlExecutionResult(
            status="executed",
            statement_type="SELECT",
            columns=["total_gz"],
            rows=[{"total_gz": "1000.00"}],
            returned_row_count=1,
        )


class EmptyThenResolvedExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, _query) -> SqlExecutionResult:
        self.calls += 1
        if self.calls == 1:
            return SqlExecutionResult(
                status="executed",
                statement_type="SELECT",
                columns=["total_gz"],
                rows=[],
                returned_row_count=0,
            )
        return SqlExecutionResult(
            status="executed",
            statement_type="SELECT",
            columns=["total_gz"],
            rows=[{"total_gz": "1000.00"}],
            returned_row_count=1,
        )


class ResultAwareQueryLLM(QueryLLM):
    def __init__(self) -> None:
        super().__init__()
        self.repair_contexts: list[dict[str, object] | None] = []

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> LLMJsonResult:
        if user_payload["task"] == "plan_and_generate_read_only_query":
            self.repair_contexts.append(user_payload["repair_context"])
        if user_payload["task"] == "assess_database_query_result":
            rows = user_payload["query_result"]["rows"]
            return LLMJsonResult(
                content={
                    "verdict": "sufficient" if rows else "replan",
                    "confidence": 0.95,
                    "reason": (
                        "结果可以回答问题" if rows else "空结果与业务取值假设冲突，需要重新规划"
                    ),
                    "issues": [] if rows else ["空结果"],
                    "next_action": ("" if rows else "查询真实类别取值后重新生成最终查询"),
                },
                provider="fake",
                model="fake-query-model",
                usage=LLMTokenUsage(total_tokens=10),
            )
        return await super().generate_json(
            system_prompt=system_prompt,
            user_payload=user_payload,
        )


@pytest.mark.asyncio
async def test_query_agent_executes_and_normalizes_semantic_source() -> None:
    llm = QueryLLM()
    agent = DatabaseQueryAgent(
        llm,  # type: ignore[arg-type]
        SuccessfulExecutor(),  # type: ignore[arg-type]
    )

    execution = await agent.query(
        make_snapshot(),
        "工资总额是多少",
        {"tables": []},
        [
            QuerySemanticSource(
                table_name="rs_gzff",
                catalog_version=1,
                review_version="v1-r1",
                source="reviewed",
            )
        ],
        {("rs_gzff", "ygbh"): "ai_catalog", ("rs_gzff", "gz"): "reviewed"},
        {("rs_gzff", "ygbh"): "员工编号", ("rs_gzff", "gz"): "实发工资"},
    )

    mapping = execution.attempts[0].plan.intent.field_mappings[0]
    assert mapping.source == "reviewed"
    assert mapping.semantic_meaning == "实发工资"
    assert execution.explanation.answer == "工资总额为1000元。"
    assert execution.usage.total_tokens == 30


@pytest.mark.asyncio
async def test_query_agent_repairs_failed_sql_once() -> None:
    llm = QueryLLM()
    executor = RepairingExecutor()
    agent = DatabaseQueryAgent(
        llm,  # type: ignore[arg-type]
        executor,  # type: ignore[arg-type]
        max_attempts=2,
    )

    execution = await agent.query(
        make_snapshot(),
        "工资总额是多少",
        {"tables": []},
        [
            QuerySemanticSource(
                table_name="rs_gzff",
                catalog_version=1,
                source="ai_catalog",
            )
        ],
        {("rs_gzff", "ygbh"): "ai_catalog", ("rs_gzff", "gz"): "ai_catalog"},
        {("rs_gzff", "ygbh"): "员工编号", ("rs_gzff", "gz"): "工资金额"},
    )

    assert len(execution.attempts) == 2
    assert execution.attempts[0].result.status == "failed"
    assert execution.attempts[1].result.status == "executed"
    assert llm.planning_calls == 2


@pytest.mark.asyncio
async def test_query_agent_replans_successful_but_insufficient_result() -> None:
    llm = ResultAwareQueryLLM()
    executor = EmptyThenResolvedExecutor()
    agent = DatabaseQueryAgent(
        llm,  # type: ignore[arg-type]
        executor,  # type: ignore[arg-type]
        max_attempts=3,
    )

    execution = await agent.query(
        make_snapshot(),
        "工资总额是多少",
        {"tables": []},
        [QuerySemanticSource(table_name="rs_gzff", source="ai_catalog")],
        {("rs_gzff", "ygbh"): "ai_catalog", ("rs_gzff", "gz"): "ai_catalog"},
        {("rs_gzff", "ygbh"): "员工编号", ("rs_gzff", "gz"): "工资金额"},
    )

    assert len(execution.attempts) == 2
    assert execution.attempts[0].assessment is not None
    assert execution.attempts[0].assessment.verdict == "replan"
    assert execution.attempts[1].assessment is not None
    assert execution.attempts[1].assessment.verdict == "sufficient"
    assert llm.repair_contexts[1] is not None
    assert llm.repair_contexts[1]["query_result"]["rows"] == []  # type: ignore[index]


@pytest.mark.asyncio
async def test_query_agent_normalizes_valid_self_join_style_aliases() -> None:
    llm = AliasedTableLLM()
    agent = DatabaseQueryAgent(
        llm,  # type: ignore[arg-type]
        SuccessfulExecutor(),  # type: ignore[arg-type]
    )

    execution = await agent.query(
        make_snapshot(),
        "统计工资",
        {"tables": []},
        [
            QuerySemanticSource(
                table_name="rs_gzff",
                source="ai_catalog",
            )
        ],
        {("rs_gzff", "ygbh"): "ai_catalog", ("rs_gzff", "gz"): "ai_catalog"},
        {("rs_gzff", "ygbh"): "员工编号", ("rs_gzff", "gz"): "工资金额"},
    )

    intent = execution.attempts[0].plan.intent
    assert intent.tables == ["rs_gzff"]
    assert intent.field_mappings[0].table_name == "rs_gzff"
