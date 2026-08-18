import asyncio
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from app.adapters.llm import BaseLLMClient
from app.agents.database_understanding.context_builder import UnderstandingContextBuilder
from app.agents.database_understanding.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from app.agents.sql_execution import SQLExecutionAgent
from app.agents.sql_generation import SQLGenerationAgent
from app.core.exceptions import LLMResponseValidationError
from app.models import (
    ColumnUnderstanding,
    DatabaseSnapshot,
    EvidenceRequest,
    EvidenceStep,
    LLMTokenUsage,
    TableUnderstandingPayload,
    UnderstandingCompletionStatus,
    UnderstandingTerminationReason,
)


@dataclass(frozen=True, slots=True)
class TableUnderstandingExecution:
    analysis: TableUnderstandingPayload
    provider: str
    model: str
    usage: LLMTokenUsage
    evidence_scope: Literal["schema_only", "schema_and_query_evidence"]
    evidence_steps: list[EvidenceStep]
    completion_status: UnderstandingCompletionStatus
    termination_reason: UnderstandingTerminationReason
    evidence_round_count: int
    max_evidence_rounds: int
    deferred_evidence_requests: list[EvidenceRequest]


class DatabaseUnderstandingAgent:
    def __init__(
        self,
        llm_client: BaseLLMClient,
        context_builder: UnderstandingContextBuilder | None = None,
        sql_generation_agent: SQLGenerationAgent | None = None,
        sql_execution_agent: SQLExecutionAgent | None = None,
        max_evidence_rounds: int = 3,
    ) -> None:
        self.llm_client = llm_client
        self.context_builder = context_builder or UnderstandingContextBuilder()
        self.sql_generation_agent = sql_generation_agent
        self.sql_execution_agent = sql_execution_agent
        self.max_evidence_rounds = max_evidence_rounds

    async def understand_table(
        self,
        snapshot: DatabaseSnapshot,
        table_name: str,
        sql_execution_agent: SQLExecutionAgent | None = None,
    ) -> TableUnderstandingExecution:
        evidence_steps: list[EvidenceStep] = []
        context = self.context_builder.build(
            snapshot,
            table_name,
            evidence_steps,
            self.max_evidence_rounds,
        )
        analysis, provider, model, usage = await self.analyze_once(
            snapshot,
            table_name,
            context,
        )

        completion_status: UnderstandingCompletionStatus = "completed"
        termination_reason: UnderstandingTerminationReason = "schema_sufficient"
        evidence_round_count = 0
        deferred_requests: list[EvidenceRequest] = []
        execution_agent = sql_execution_agent or self.sql_execution_agent
        evidence_loop_available = (
            self.sql_generation_agent is not None and execution_agent is not None
        )

        if evidence_loop_available:
            for round_number in range(1, self.max_evidence_rounds + 1):
                requests = analysis.evidence_requests
                if not requests:
                    termination_reason = (
                        "evidence_resolved" if evidence_steps else "schema_sufficient"
                    )
                    break
                assert self.sql_generation_agent is not None
                generation = await self.sql_generation_agent.generate(
                    snapshot,
                    table_name,
                    requests,
                )
                usage = self.add_usage(usage, generation.usage)
                if not generation.plan.queries:
                    termination_reason = "sql_generation_stalled"
                    break
                assert execution_agent is not None
                results = await asyncio.gather(
                    *[execution_agent.execute(query) for query in generation.plan.queries]
                )
                round_steps = [
                    EvidenceStep(
                        round_number=round_number,
                        request=requests[query.request_index],
                        query=query,
                        result=result,
                    )
                    for query, result in zip(
                        generation.plan.queries,
                        results,
                        strict=True,
                    )
                ]
                evidence_steps.extend(round_steps)
                evidence_round_count = round_number
                context = self.context_builder.build(
                    snapshot,
                    table_name,
                    evidence_steps,
                    self.max_evidence_rounds,
                )
                analysis, provider, model, round_usage = await self.analyze_once(
                    snapshot,
                    table_name,
                    context,
                )
                usage = self.add_usage(usage, round_usage)
            else:
                termination_reason = (
                    "round_limit_reached" if analysis.evidence_requests else "evidence_resolved"
                )
        elif analysis.evidence_requests:
            termination_reason = "evidence_loop_unavailable"

        if analysis.evidence_requests:
            deferred_requests = list(analysis.evidence_requests)
            completion_status = "best_effort"
            limitation = self.termination_limitation(termination_reason)
            analysis = analysis.model_copy(
                update={
                    "evidence_requests": [],
                    "limitations": [*analysis.limitations, limitation][:8],
                }
            )

        return TableUnderstandingExecution(
            analysis=analysis,
            provider=provider,
            model=model,
            usage=usage,
            evidence_scope=("schema_and_query_evidence" if evidence_steps else "schema_only"),
            evidence_steps=evidence_steps,
            completion_status=completion_status,
            termination_reason=termination_reason,
            evidence_round_count=evidence_round_count,
            max_evidence_rounds=self.max_evidence_rounds,
            deferred_evidence_requests=deferred_requests,
        )

    async def analyze_once(
        self,
        snapshot: DatabaseSnapshot,
        table_name: str,
        context: dict[str, object],
    ) -> tuple[TableUnderstandingPayload, str, str, LLMTokenUsage]:
        llm_result = await self.llm_client.generate_json(
            system_prompt=SYSTEM_PROMPT,
            user_payload=context,
        )
        try:
            analysis = TableUnderstandingPayload.model_validate(llm_result.content)
        except ValidationError as exc:
            first_error = exc.errors(include_url=False)[0]
            location = ".".join(str(part) for part in first_error["loc"])
            raise LLMResponseValidationError(f"大模型返回结果字段无效：{location}") from None

        table = next(table for table in snapshot.tables if table.name == table_name)
        expected_columns = {column.name for column in table.columns}
        returned_columns = {column.column_name for column in analysis.columns}
        unexpected_columns = returned_columns - expected_columns
        if unexpected_columns:
            names = ", ".join(sorted(unexpected_columns))
            raise LLMResponseValidationError(f"大模型返回了不存在的字段：{names}")

        columns_by_name = {column.column_name: column for column in analysis.columns}
        normalized_columns = []
        for column in table.columns:
            normalized_columns.append(
                columns_by_name.get(column.name)
                or ColumnUnderstanding(
                    column_name=column.name,
                    status="unknown",
                    role_candidates=[],
                    meaning_candidates=[],
                    sensitivity_candidates=[],
                )
            )
        analysis = analysis.model_copy(update={"columns": normalized_columns})
        return (
            analysis,
            llm_result.provider,
            llm_result.model,
            llm_result.usage,
        )

    @staticmethod
    def add_usage(left: LLMTokenUsage, right: LLMTokenUsage) -> LLMTokenUsage:
        return LLMTokenUsage(
            prompt_tokens=left.prompt_tokens + right.prompt_tokens,
            completion_tokens=left.completion_tokens + right.completion_tokens,
            total_tokens=left.total_tokens + right.total_tokens,
        )

    @staticmethod
    def termination_limitation(
        reason: UnderstandingTerminationReason,
    ) -> str:
        messages = {
            "round_limit_reached": "已完成三轮自动取证；仍不唯一的语义按最佳候选保留。",
            "sql_generation_stalled": "SQL生成Agent未能生成新的有效查询，结果按现有证据收敛。",
            "evidence_loop_unavailable": "自动取证组件不可用，结果仅按现有证据收敛。",
            "schema_sufficient": "当前Schema证据已足够。",
            "evidence_resolved": "自动取证已解决关键证据需求。",
        }
        return messages[reason]


__all__ = [
    "DatabaseUnderstandingAgent",
    "PROMPT_VERSION",
    "TableUnderstandingExecution",
]
