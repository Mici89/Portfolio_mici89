from datetime import UTC, datetime
from typing import Any

import pytest

from app.adapters.database import DatabaseSelectResult
from app.adapters.llm import BaseLLMClient, LLMJsonResult
from app.agents.database_understanding import DatabaseUnderstandingAgent
from app.agents.sql_execution import SQLExecutionAgent
from app.agents.sql_generation import SQLGenerationAgent
from app.models import (
    ColumnSchema,
    DatabaseMetadata,
    DatabaseSnapshot,
    DatabaseSource,
    LLMTokenUsage,
    ScanStatistics,
    TableSchema,
)


class FakeLLMClient(BaseLLMClient):
    def __init__(self) -> None:
        self.last_payload: dict[str, Any] | None = None

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> LLMJsonResult:
        assert "不得虚构" in system_prompt
        self.last_payload = user_payload
        return LLMJsonResult(
            content={
                "summary": "结构不足，只能形成初步候选。",
                "status": "ambiguous",
                "table_candidates": [
                    {
                        "meaning": "员工月度薪资快照",
                        "description": "可能记录员工每月工资组成。",
                        "confidence": 0.58,
                        "supporting_evidence": ["包含多个金额型字段"],
                        "counter_evidence": ["没有字段注释和数据画像"],
                    }
                ],
                "table_role_candidates": [],
                "grain_candidates": [],
                "columns": [
                    {
                        "column_name": "k1",
                        "status": "inferred",
                        "role_candidates": [],
                        "meaning_candidates": [
                            {
                                "meaning": "记录主键",
                                "description": "",
                                "confidence": 0.99,
                                "supporting_evidence": ["数据库声明为主键"],
                                "counter_evidence": [],
                            }
                        ],
                        "sensitivity_candidates": [],
                    }
                ],
                "evidence_requests": [
                    {
                        "request_type": "value_distribution",
                        "target_columns": ["c01"],
                        "reason": "需要判断字段编码模式。",
                        "priority": "high",
                    }
                ],
                "limitations": ["当前只有Schema证据"],
            },
            provider="deepseek",
            model="deepseek-chat",
            usage=LLMTokenUsage(prompt_tokens=100, completion_tokens=80, total_tokens=180),
        )


def make_snapshot() -> DatabaseSnapshot:
    return DatabaseSnapshot(
        snapshot_id="snap_test_agent",
        captured_at=datetime(2026, 7, 27, tzinfo=UTC),
        source=DatabaseSource(
            database_type="mysql",
            host="127.0.0.1",
            port=3307,
            database="legacy_enterprise",
        ),
        database=DatabaseMetadata(
            name="legacy_enterprise",
            server_version="8.4.10",
            current_user="ai_reader@%",
            character_set="utf8mb4",
            collation="utf8mb4_0900_ai_ci",
        ),
        tables=[
            TableSchema(
                name="t_a01",
                table_type="BASE TABLE",
                primary_key=["k1"],
                columns=[
                    ColumnSchema(
                        name="k1",
                        ordinal_position=1,
                        data_type="bigint",
                        column_type="bigint unsigned",
                        nullable=False,
                        is_primary_key=True,
                    ),
                    ColumnSchema(
                        name="c01",
                        ordinal_position=2,
                        data_type="varchar",
                        column_type="varchar(20)",
                        nullable=False,
                    ),
                ],
            )
        ],
        declared_relationships=[],
        scan_statistics=ScanStatistics(
            table_count=1,
            view_count=0,
            column_count=2,
            foreign_key_count=0,
            index_count=1,
        ),
    )


@pytest.mark.asyncio
async def test_agent_keeps_multiple_candidates_and_fills_missing_columns() -> None:
    llm = FakeLLMClient()
    agent = DatabaseUnderstandingAgent(llm)

    execution = await agent.understand_table(make_snapshot(), "t_a01")

    assert execution.analysis.status == "ambiguous"
    assert execution.analysis.table_candidates[0].meaning == "员工月度薪资快照"
    assert [column.column_name for column in execution.analysis.columns] == ["k1", "c01"]
    assert execution.analysis.columns[1].status == "unknown"
    assert llm.last_payload is not None
    assert llm.last_payload["evidence_scope"] == "schema_only"
    assert "host" not in llm.last_payload["database"]


class EvidenceLoopLLMClient(BaseLLMClient):
    def __init__(self, *, resolve_after_evidence: bool = True) -> None:
        self.understanding_payloads: list[dict[str, Any]] = []
        self.resolve_after_evidence = resolve_after_evidence

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> LLMJsonResult:
        if system_prompt.startswith("你是数据库取证流程中的SQL生成Agent"):
            content = {
                "queries": [
                    {
                        "request_index": 0,
                        "purpose": "查看c01代表值",
                        "sql": "SELECT `c01` FROM `t_a01` LIMIT 10",
                    }
                ]
            }
        else:
            self.understanding_payloads.append(user_payload)
            has_evidence = bool(user_payload.get("query_evidence")) and self.resolve_after_evidence
            content = {
                "summary": "已读取实际字段值。" if has_evidence else "需要查询字段值。",
                "status": "inferred" if has_evidence else "ambiguous",
                "table_candidates": [],
                "table_role_candidates": [],
                "grain_candidates": [],
                "columns": [],
                "evidence_requests": (
                    []
                    if has_evidence
                    else [
                        {
                            "request_type": "representative_rows",
                            "target_columns": ["c01"],
                            "reason": "需要读取实际编码值。",
                            "priority": "high",
                        }
                    ]
                ),
                "limitations": [],
            }
        return LLMJsonResult(
            content=content,
            provider="deepseek",
            model="deepseek-chat",
            usage=LLMTokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )


class FakeSelectAdapter:
    def execute_select(self, sql: str, max_rows: int) -> DatabaseSelectResult:
        assert sql == "SELECT `c01` FROM `t_a01` LIMIT 10"
        assert max_rows == 50
        return DatabaseSelectResult(
            columns=["c01"],
            rows=[{"c01": "E00001"}, {"c01": "E00002"}],
            truncated=False,
        )


@pytest.mark.asyncio
async def test_agent_automatically_generates_and_executes_evidence_sql() -> None:
    llm = EvidenceLoopLLMClient()
    sql_generation_agent = SQLGenerationAgent(llm)
    sql_execution_agent = SQLExecutionAgent(FakeSelectAdapter())  # type: ignore[arg-type]
    agent = DatabaseUnderstandingAgent(
        llm,
        sql_generation_agent=sql_generation_agent,
        sql_execution_agent=sql_execution_agent,
    )

    execution = await agent.understand_table(make_snapshot(), "t_a01")

    assert execution.analysis.status == "inferred"
    assert execution.evidence_scope == "schema_and_query_evidence"
    assert len(execution.evidence_steps) == 1
    assert execution.evidence_steps[0].result.status == "executed"
    assert execution.evidence_steps[0].result.rows[0]["c01"] == "E00001"
    assert len(llm.understanding_payloads) == 2
    assert llm.understanding_payloads[1]["query_evidence"][0]["result"]["rows"]
    assert execution.usage.total_tokens == 45


@pytest.mark.asyncio
async def test_agent_runs_three_rounds_then_returns_best_effort_without_user_todo() -> None:
    llm = EvidenceLoopLLMClient(resolve_after_evidence=False)
    agent = DatabaseUnderstandingAgent(
        llm,
        sql_generation_agent=SQLGenerationAgent(llm),
        sql_execution_agent=SQLExecutionAgent(FakeSelectAdapter()),  # type: ignore[arg-type]
        max_evidence_rounds=3,
    )

    execution = await agent.understand_table(make_snapshot(), "t_a01")

    assert execution.completion_status == "best_effort"
    assert execution.termination_reason == "round_limit_reached"
    assert execution.evidence_round_count == 3
    assert execution.max_evidence_rounds == 3
    assert len(execution.evidence_steps) == 3
    assert execution.analysis.evidence_requests == []
    assert len(execution.deferred_evidence_requests) == 1
    assert len(llm.understanding_payloads) == 4
    assert execution.usage.total_tokens == 105
