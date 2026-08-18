from dataclasses import dataclass

from pydantic import ValidationError

from app.adapters.llm import BaseLLMClient
from app.agents.sql_generation.prompts import build_system_prompt
from app.core.exceptions import DatabaseTableNotFoundError, LLMResponseValidationError
from app.models import (
    DatabaseSnapshot,
    EvidenceRequest,
    LLMTokenUsage,
    SqlGenerationPayload,
)


@dataclass(frozen=True, slots=True)
class SQLGenerationExecution:
    plan: SqlGenerationPayload
    provider: str
    model: str
    usage: LLMTokenUsage


class SQLGenerationAgent:
    def __init__(self, llm_client: BaseLLMClient) -> None:
        self.llm_client = llm_client

    async def generate(
        self,
        snapshot: DatabaseSnapshot,
        table_name: str,
        requests: list[EvidenceRequest],
    ) -> SQLGenerationExecution:
        tables_by_name = {table.name: table for table in snapshot.tables}
        if table_name not in tables_by_name:
            raise DatabaseTableNotFoundError(table_name)

        payload = {
            "task": "generate_evidence_select_queries",
            "database": {
                "type": snapshot.source.database_type,
                "name": snapshot.database.name,
                "server_version": snapshot.database.server_version,
            },
            "target_table": table_name,
            "evidence_requests": [
                {"request_index": index, **request.model_dump(mode="json")}
                for index, request in enumerate(requests)
            ],
            "available_schema": [
                {
                    "name": table.name,
                    "comment": table.comment,
                    "primary_key": table.primary_key,
                    "estimated_row_count": table.estimated_row_count,
                    "columns": [
                        {
                            "name": column.name,
                            "column_type": column.column_type,
                            "nullable": column.nullable,
                            "comment": column.comment,
                            "is_primary_key": column.is_primary_key,
                            "is_unique": column.is_unique,
                        }
                        for column in table.columns
                    ],
                }
                for table in snapshot.tables
            ],
            "declared_relationships": [
                relationship.model_dump(mode="json")
                for relationship in snapshot.declared_relationships
            ],
            "output_json_schema": SqlGenerationPayload.model_json_schema(),
        }
        llm_result = await self.llm_client.generate_json(
            system_prompt=build_system_prompt(snapshot.source.database_type),
            user_payload=payload,
        )
        try:
            plan = SqlGenerationPayload.model_validate(llm_result.content)
        except ValidationError as exc:
            first_error = exc.errors(include_url=False)[0]
            location = ".".join(str(part) for part in first_error["loc"])
            raise LLMResponseValidationError(f"SQL生成Agent返回结果字段无效：{location}") from None

        invalid_indexes = {
            query.request_index for query in plan.queries if query.request_index >= len(requests)
        }
        if invalid_indexes:
            indexes = ", ".join(str(index) for index in sorted(invalid_indexes))
            raise LLMResponseValidationError(f"SQL生成Agent引用了不存在的证据请求：{indexes}")
        return SQLGenerationExecution(
            plan=plan,
            provider=llm_result.provider,
            model=llm_result.model,
            usage=llm_result.usage,
        )
