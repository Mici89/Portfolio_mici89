from datetime import date

from pydantic import ValidationError

from app.adapters.llm import BaseLLMClient
from app.agents.database_action.prompts import (
    CONVERSATION_ROUTER_SYSTEM_PROMPT,
    DATABASE_ACTION_PLANNER_SYSTEM_PROMPT,
)
from app.core.exceptions import LLMResponseValidationError
from app.models import (
    ConversationRoutingDecision,
    DatabaseActionDraft,
    DatabaseSnapshot,
    LLMTokenUsage,
)


class ConversationIntentRouter:
    def __init__(self, llm_client: BaseLLMClient) -> None:
        self.llm_client = llm_client

    async def route(
        self,
        message: str,
        conversation_context: dict[str, object] | None,
    ) -> ConversationRoutingDecision:
        result = await self.llm_client.generate_json(
            system_prompt=CONVERSATION_ROUTER_SYSTEM_PROMPT,
            user_payload={
                "message": message,
                "conversation_context": conversation_context,
                "output_json_schema": ConversationRoutingDecision.model_json_schema(),
            },
        )
        try:
            return ConversationRoutingDecision.model_validate(result.content)
        except ValidationError as exc:
            raise self._validation_error("意图路由Agent", exc) from None

    @staticmethod
    def _validation_error(prefix: str, exc: ValidationError) -> LLMResponseValidationError:
        first_error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in first_error["loc"])
        return LLMResponseValidationError(f"{prefix}返回结果字段无效：{location}")


class DatabaseActionPlanningAgent:
    def __init__(self, llm_client: BaseLLMClient) -> None:
        self.llm_client = llm_client

    async def plan(
        self,
        snapshot: DatabaseSnapshot,
        message: str,
        semantic_payload: dict[str, object],
        conversation_context: dict[str, object] | None = None,
        planning_context: dict[str, object] | None = None,
    ) -> tuple[DatabaseActionDraft, str, str, LLMTokenUsage]:
        result = await self.llm_client.generate_json(
            system_prompt=DATABASE_ACTION_PLANNER_SYSTEM_PROMPT,
            user_payload={
                "task": "plan_single_table_database_action",
                "message": message,
                "current_date": date.today().isoformat(),
                "conversation_context": conversation_context,
                "planning_context": planning_context,
                "database": {
                    "name": snapshot.database.name,
                    "type": snapshot.source.database_type,
                },
                "database_schema": {
                    "tables": [
                        {
                            "name": table.name,
                            "type": table.table_type,
                            "primary_key": table.primary_key,
                            "columns": [
                                {
                                    "name": column.name,
                                    "data_type": column.data_type,
                                    "column_type": column.column_type,
                                    "nullable": column.nullable,
                                    "default": column.default,
                                    "extra": column.extra,
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
                },
                "effective_semantics": semantic_payload,
                "output_json_schema": DatabaseActionDraft.model_json_schema(),
            },
        )
        try:
            draft = DatabaseActionDraft.model_validate(result.content)
        except ValidationError as exc:
            raise ConversationIntentRouter._validation_error(
                "数据库操作规划Agent",
                exc,
            ) from None
        return draft, result.provider, result.model, result.usage
