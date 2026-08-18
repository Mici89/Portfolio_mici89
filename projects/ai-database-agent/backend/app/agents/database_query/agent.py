import re
from dataclasses import dataclass
from datetime import date

from pydantic import ValidationError

from app.adapters.llm import BaseLLMClient
from app.agents.database_query.prompts import (
    QUERY_EXPLAINER_SYSTEM_PROMPT,
    QUERY_RESULT_ASSESSOR_SYSTEM_PROMPT,
    build_query_planner_system_prompt,
)
from app.agents.sql_execution import SQLExecutionAgent
from app.core.exceptions import LLMResponseValidationError
from app.models import (
    DatabaseSnapshot,
    GeneratedSqlQuery,
    LLMTokenUsage,
    QueryAttempt,
    QueryExplanation,
    QueryFieldReference,
    QueryPlan,
    QueryResultAssessment,
    QuerySemanticSource,
)


@dataclass(frozen=True, slots=True)
class DatabaseQueryExecution:
    attempts: list[QueryAttempt]
    explanation: QueryExplanation
    semantic_sources: list[QuerySemanticSource]
    provider: str
    model: str
    usage: LLMTokenUsage


class DatabaseQueryAgent:
    def __init__(
        self,
        llm_client: BaseLLMClient,
        sql_execution_agent: SQLExecutionAgent | None = None,
        *,
        max_attempts: int = 3,
        max_planning_attempts: int = 3,
    ) -> None:
        self.llm_client = llm_client
        self.sql_execution_agent = sql_execution_agent
        self.max_attempts = max_attempts
        self.max_planning_attempts = max_planning_attempts

    async def plan_once(
        self,
        snapshot: DatabaseSnapshot,
        question: str,
        semantic_payload: dict[str, object],
        field_sources: dict[tuple[str, str], str],
        field_meanings: dict[tuple[str, str], str],
        repair_context: dict[str, object] | None,
        conversation_context: dict[str, object] | None,
    ) -> tuple[QueryPlan, str, str, LLMTokenUsage]:
        """Run one validated planning step for an external workflow orchestrator."""
        return await self._plan_with_repair(
            snapshot,
            question,
            semantic_payload,
            field_sources,
            field_meanings,
            repair_context,
            conversation_context,
        )

    async def assess_result(
        self,
        question: str,
        plan: QueryPlan,
        result: dict[str, object],
        previous_attempts: list[QueryAttempt],
        conversation_context: dict[str, object] | None,
    ) -> tuple[QueryResultAssessment, LLMTokenUsage]:
        """Assess one executed result without owning the outer retry loop."""
        return await self._assess(
            question,
            plan,
            result,
            previous_attempts,
            conversation_context,
        )

    async def explain_result(
        self,
        question: str,
        plan: QueryPlan,
        result: dict[str, object],
        semantic_sources: list[QuerySemanticSource],
        conversation_context: dict[str, object] | None,
    ) -> tuple[QueryExplanation, LLMTokenUsage]:
        """Explain the final result for an external workflow orchestrator."""
        return await self._explain(
            question,
            plan,
            result,
            semantic_sources,
            conversation_context,
        )

    @classmethod
    def result_repair_context(
        cls,
        attempts: list[QueryAttempt],
        assessment: QueryResultAssessment,
    ) -> dict[str, object]:
        return cls._result_repair_context(attempts, assessment)

    @staticmethod
    def attempt_history(attempts: list[QueryAttempt]) -> list[dict[str, object]]:
        return DatabaseQueryAgent._attempt_history(attempts)

    @staticmethod
    def add_usage(left: LLMTokenUsage, right: LLMTokenUsage) -> LLMTokenUsage:
        return DatabaseQueryAgent._add_usage(left, right)

    async def query(
        self,
        snapshot: DatabaseSnapshot,
        question: str,
        semantic_payload: dict[str, object],
        semantic_sources: list[QuerySemanticSource],
        field_sources: dict[tuple[str, str], str],
        field_meanings: dict[tuple[str, str], str],
        conversation_context: dict[str, object] | None = None,
        sql_execution_agent: SQLExecutionAgent | None = None,
    ) -> DatabaseQueryExecution:
        attempts: list[QueryAttempt] = []
        usage = LLMTokenUsage()
        provider = ""
        model = ""
        repair_context: dict[str, object] | None = None

        for attempt_number in range(1, self.max_attempts + 1):
            plan, provider, model, plan_usage = await self._plan_with_repair(
                snapshot,
                question,
                semantic_payload,
                field_sources,
                field_meanings,
                repair_context,
                conversation_context,
            )
            usage = self._add_usage(usage, plan_usage)
            execution_agent = sql_execution_agent or self.sql_execution_agent
            if execution_agent is None:
                raise RuntimeError("Database query execution adapter was not resolved")
            result = await execution_agent.execute(
                GeneratedSqlQuery(
                    request_index=0,
                    purpose=plan.sql_purpose,
                    sql=plan.sql,
                )
            )
            if result.status == "executed":
                assessment, assessment_usage = await self._assess(
                    question,
                    plan,
                    result.model_dump(mode="json"),
                    attempts,
                    conversation_context,
                )
                usage = self._add_usage(usage, assessment_usage)
                attempts.append(
                    QueryAttempt(
                        attempt_number=attempt_number,
                        plan=plan,
                        result=result,
                        assessment=assessment,
                    )
                )
                if assessment.verdict == "replan" and attempt_number < self.max_attempts:
                    repair_context = self._result_repair_context(
                        attempts,
                        assessment,
                    )
                    continue
                used_sources = [
                    source for source in semantic_sources if source.table_name in plan.intent.tables
                ]
                explanation, explanation_usage = await self._explain(
                    question,
                    plan,
                    result.model_dump(mode="json"),
                    used_sources,
                    conversation_context,
                )
                usage = self._add_usage(usage, explanation_usage)
                if assessment.verdict == "replan":
                    explanation = explanation.model_copy(
                        update={
                            "limitations": [
                                *explanation.limitations,
                                (f"查询闭环已达到{self.max_attempts}轮上限：{assessment.reason}"),
                            ]
                        }
                    )
                return DatabaseQueryExecution(
                    attempts=attempts,
                    explanation=explanation,
                    semantic_sources=used_sources,
                    provider=provider,
                    model=model,
                    usage=usage,
                )
            assessment = QueryResultAssessment(
                verdict="replan",
                confidence=1,
                reason=result.error or "SQL执行失败",
                issues=[result.error or "SQL执行失败"],
                next_action="根据数据库错误修正SQL并重新执行。",
            )
            attempts.append(
                QueryAttempt(
                    attempt_number=attempt_number,
                    plan=plan,
                    result=result,
                    assessment=assessment,
                )
            )
            repair_context = {
                "attempt_history": self._attempt_history(attempts),
                "previous_sql": plan.sql,
                "execution_status": result.status,
                "database_error": result.error,
                "instruction": assessment.next_action,
            }

        last_result = attempts[-1].result
        used_tables = set(attempts[-1].plan.intent.tables)
        return DatabaseQueryExecution(
            attempts=attempts,
            explanation=QueryExplanation(
                answer="查询未能成功执行。",
                observations=[],
                data_scope="没有返回可解释的查询结果。",
                limitations=[last_result.error or "SQL执行失败"],
            ),
            semantic_sources=[
                source for source in semantic_sources if source.table_name in used_tables
            ],
            provider=provider,
            model=model,
            usage=usage,
        )

    async def _assess(
        self,
        question: str,
        plan: QueryPlan,
        result: dict[str, object],
        previous_attempts: list[QueryAttempt],
        conversation_context: dict[str, object] | None,
    ) -> tuple[QueryResultAssessment, LLMTokenUsage]:
        llm_result = await self.llm_client.generate_json(
            system_prompt=QUERY_RESULT_ASSESSOR_SYSTEM_PROMPT,
            user_payload={
                "task": "assess_database_query_result",
                "question": question,
                "current_plan": plan.model_dump(mode="json"),
                "query_result": result,
                "previous_attempts": self._attempt_history(previous_attempts),
                "conversation_context": conversation_context,
                "output_json_schema": QueryResultAssessment.model_json_schema(),
            },
        )
        try:
            assessment = QueryResultAssessment.model_validate(llm_result.content)
        except ValidationError as exc:
            first_error = exc.errors(include_url=False)[0]
            location = ".".join(str(part) for part in first_error["loc"])
            raise LLMResponseValidationError(f"查询结果质检Agent返回字段无效：{location}") from None
        if plan.plan_type == "evidence" and assessment.verdict != "replan":
            assessment = assessment.model_copy(
                update={
                    "verdict": "replan",
                    "reason": "当前是取证查询，必须基于真实证据生成最终回答查询。",
                    "next_action": (
                        assessment.next_action or "使用本轮证据生成plan_type=answer的查询。"
                    ),
                }
            )
        return assessment, llm_result.usage

    async def _plan_with_repair(
        self,
        snapshot: DatabaseSnapshot,
        question: str,
        semantic_payload: dict[str, object],
        field_sources: dict[tuple[str, str], str],
        field_meanings: dict[tuple[str, str], str],
        repair_context: dict[str, object] | None,
        conversation_context: dict[str, object] | None,
    ) -> tuple[QueryPlan, str, str, LLMTokenUsage]:
        current_repair = repair_context
        for planning_attempt in range(1, self.max_planning_attempts + 1):
            try:
                return await self._plan(
                    snapshot,
                    question,
                    semantic_payload,
                    field_sources,
                    field_meanings,
                    current_repair,
                    conversation_context,
                )
            except LLMResponseValidationError as exc:
                if planning_attempt >= self.max_planning_attempts:
                    raise
                required_frame = self._required_frame_from_validation(exc.message)
                current_repair = {
                    **(repair_context or {}),
                    "planning_validation_error": exc.message,
                    "required_semantic_frame": required_frame,
                    "instruction": (
                        "上一计划无效，必须先消除planning_validation_error指出的语义冲突，"
                        "再重新生成完整semantic_frame和SQL；禁止重复上一计划。"
                    ),
                }
        raise AssertionError("unreachable")

    async def _plan(
        self,
        snapshot: DatabaseSnapshot,
        question: str,
        semantic_payload: dict[str, object],
        field_sources: dict[tuple[str, str], str],
        field_meanings: dict[tuple[str, str], str],
        repair_context: dict[str, object] | None,
        conversation_context: dict[str, object] | None,
    ) -> tuple[QueryPlan, str, str, LLMTokenUsage]:
        llm_result = await self.llm_client.generate_json(
            system_prompt=build_query_planner_system_prompt(
                snapshot.source.database_type
            ),
            user_payload={
                "task": "plan_and_generate_read_only_query",
                "planning_mode": (
                    "repair_invalid_plan"
                    if repair_context is not None
                    else "initial_plan"
                ),
                "question": question,
                "current_date": date.today().isoformat(),
                "repair_context": repair_context,
                "conversation_context": conversation_context,
                "database": {
                    "name": snapshot.database.name,
                    "type": snapshot.source.database_type,
                    "server_version": snapshot.database.server_version,
                },
                "effective_semantics": semantic_payload,
                "output_json_schema": QueryPlan.model_json_schema(),
            },
        )
        try:
            plan = QueryPlan.model_validate(llm_result.content)
        except ValidationError as exc:
            first_error = exc.errors(include_url=False)[0]
            location = ".".join(str(part) for part in first_error["loc"])
            raise LLMResponseValidationError(f"查询Agent返回结果字段无效：{location}") from None
        plan = self._validate_and_normalize_plan(
            snapshot,
            plan,
            field_sources,
            field_meanings,
        )
        self._validate_semantic_frame(
            snapshot,
            plan,
            question,
            field_meanings,
            conversation_context,
        )
        self._validate_goal_alignment(plan, conversation_context)
        return plan, llm_result.provider, llm_result.model, llm_result.usage

    async def _explain(
        self,
        question: str,
        plan: QueryPlan,
        result: dict[str, object],
        semantic_sources: list[QuerySemanticSource],
        conversation_context: dict[str, object] | None,
    ) -> tuple[QueryExplanation, LLMTokenUsage]:
        llm_result = await self.llm_client.generate_json(
            system_prompt=QUERY_EXPLAINER_SYSTEM_PROMPT,
            user_payload={
                "task": "explain_database_query_result",
                "question": question,
                "query_intent": plan.intent.model_dump(mode="json"),
                "executed_sql": plan.sql,
                "query_result": result,
                "semantic_sources": [source.model_dump(mode="json") for source in semantic_sources],
                "conversation_context": conversation_context,
                "output_json_schema": QueryExplanation.model_json_schema(),
            },
        )
        try:
            explanation = QueryExplanation.model_validate(llm_result.content)
        except ValidationError as exc:
            first_error = exc.errors(include_url=False)[0]
            location = ".".join(str(part) for part in first_error["loc"])
            raise LLMResponseValidationError(f"结果解释Agent返回字段无效：{location}") from None
        return explanation, llm_result.usage

    @classmethod
    def _validate_goal_alignment(
        cls,
        plan: QueryPlan,
        conversation_context: dict[str, object] | None,
    ) -> None:
        if plan.plan_type != "answer" or not conversation_context:
            return
        goal = conversation_context.get("resolved_goal")
        if not isinstance(goal, dict):
            return
        missing: list[str] = []
        required_tables = goal.get("tables")
        if isinstance(required_tables, list):
            actual_tables = set(plan.intent.tables)
            dropped_tables = [
                table
                for table in required_tables
                if isinstance(table, str) and table not in actual_tables
            ]
            if dropped_tables:
                missing.append(f"事实表：{', '.join(dropped_tables)}")

        active = conversation_context.get("active_intent")
        if isinstance(active, dict):
            active_frame = active.get("semantic_frame")
            if isinstance(active_frame, dict):
                cls._validate_inherited_frame(
                    plan,
                    active_frame,
                    goal,
                    missing,
                )
        if missing:
            raise LLMResponseValidationError(
                "查询计划偏离合并后的对话目标，缺少" + "；".join(missing)
            )

    @classmethod
    def _validate_inherited_frame(
        cls,
        plan: QueryPlan,
        active_frame: dict[str, object],
        goal: dict[str, object],
        missing: list[str],
    ) -> None:
        frame = plan.intent.semantic_frame
        if goal.get("metrics"):
            previous_aggregation = active_frame.get("aggregation")
            if (
                isinstance(previous_aggregation, str)
                and previous_aggregation != "detail"
                and frame.aggregation != previous_aggregation
            ):
                missing.append(f"聚合口径：{previous_aggregation}")
            previous_entity = active_frame.get("metric_entity")
            if (
                isinstance(previous_entity, str)
                and previous_entity
                and cls._semantic_key(frame.metric_entity)
                != cls._semantic_key(previous_entity)
            ):
                missing.append(f"统计实体：{previous_entity}")
        if goal.get("filters"):
            previous_time = cls._dict_field_reference(active_frame.get("time_field"))
            current_time = frame.time_field
            if previous_time is not None and (
                current_time is None
                or (current_time.table_name, current_time.column_name) != previous_time
            ):
                missing.append(
                    f"时间字段：{previous_time[0]}.{previous_time[1]}"
                )

    @staticmethod
    def _dict_field_reference(value: object) -> tuple[str, str] | None:
        if not isinstance(value, dict):
            return None
        table_name = value.get("table_name")
        column_name = value.get("column_name")
        if isinstance(table_name, str) and isinstance(column_name, str):
            return table_name, column_name
        return None

    @staticmethod
    def _semantic_key(value: str) -> str:
        return "".join(value.lower().split())

    @staticmethod
    def _validate_and_normalize_plan(
        snapshot: DatabaseSnapshot,
        plan: QueryPlan,
        field_sources: dict[tuple[str, str], str],
        field_meanings: dict[tuple[str, str], str],
    ) -> QueryPlan:
        tables = {
            table.name: {column.name for column in table.columns} for table in snapshot.tables
        }
        normalized_tables = []
        for table_reference in plan.intent.tables:
            physical_table = DatabaseQueryAgent._physical_table_name(
                table_reference,
                tables,
            )
            if physical_table not in normalized_tables:
                normalized_tables.append(physical_table)
        unknown_tables = sorted(set(normalized_tables) - tables.keys())
        if unknown_tables:
            raise LLMResponseValidationError(
                f"查询Agent引用了不存在的表：{', '.join(unknown_tables)}"
            )
        mappings = []
        for mapping in plan.intent.field_mappings:
            physical_table = DatabaseQueryAgent._physical_table_name(
                mapping.table_name,
                tables,
            )
            columns = tables.get(physical_table)
            if columns is None or mapping.column_name not in columns:
                raise LLMResponseValidationError(
                    f"查询Agent引用了不存在的字段：{physical_table}.{mapping.column_name}"
                )
            key = (physical_table, mapping.column_name)
            mappings.append(
                mapping.model_copy(
                    update={
                        "table_name": physical_table,
                        "source": field_sources[key],
                        "semantic_meaning": field_meanings[key],
                    }
                )
            )
        frame = plan.intent.semantic_frame
        fact_table = (
            DatabaseQueryAgent._physical_table_name(frame.fact_table, tables)
            if frame.fact_table
            else None
        )
        if fact_table is not None and fact_table not in tables:
            raise LLMResponseValidationError(
                f"查询Agent的事实表不存在：{fact_table}"
            )
        distinct_key = DatabaseQueryAgent._normalize_frame_reference(
            frame.distinct_key,
            tables,
        )
        time_field = DatabaseQueryAgent._normalize_frame_reference(
            frame.time_field,
            tables,
        )
        predicate_bindings = [
            binding.model_copy(
                update={
                    "field": DatabaseQueryAgent._normalize_frame_reference(
                        binding.field,
                        tables,
                    )
                }
            )
            for binding in frame.predicate_bindings
        ]
        normalized_frame = frame.model_copy(
            update={
                "fact_table": fact_table,
                "distinct_key": distinct_key,
                "time_field": time_field,
                "predicate_bindings": predicate_bindings,
            }
        )
        referenced_tables = {
            reference.table_name
            for reference in [
                distinct_key,
                time_field,
                *(binding.field for binding in predicate_bindings),
            ]
            if reference is not None
        }
        if fact_table is not None:
            referenced_tables.add(fact_table)
        missing_frame_tables = sorted(referenced_tables - set(normalized_tables))
        if missing_frame_tables:
            raise LLMResponseValidationError(
                "查询Agent的语义帧引用了intent.tables之外的表："
                + ", ".join(missing_frame_tables)
            )
        return plan.model_copy(
            update={
                "intent": plan.intent.model_copy(
                    update={
                        "tables": normalized_tables,
                        "field_mappings": mappings,
                        "semantic_frame": normalized_frame,
                    }
                )
            }
        )

    @staticmethod
    def _normalize_frame_reference(
        reference: QueryFieldReference | None,
        tables: dict[str, set[str]],
    ) -> QueryFieldReference | None:
        if reference is None:
            return None
        physical_table = DatabaseQueryAgent._physical_table_name(
            reference.table_name,
            tables,
        )
        columns = tables.get(physical_table)
        if columns is None or reference.column_name not in columns:
            raise LLMResponseValidationError(
                "查询Agent的语义帧引用了不存在的字段："
                f"{physical_table}.{reference.column_name}"
            )
        return reference.model_copy(update={"table_name": physical_table})

    @classmethod
    def _validate_semantic_frame(
        cls,
        snapshot: DatabaseSnapshot,
        plan: QueryPlan,
        question: str,
        field_meanings: dict[tuple[str, str], str],
        conversation_context: dict[str, object] | None,
    ) -> None:
        if plan.plan_type != "answer":
            return
        frame = plan.intent.semantic_frame
        scope_text = cls._semantic_scope_text(question, conversation_context)
        has_time_scope = cls._has_time_scope(scope_text)
        lifecycle_requested = cls._has_lifecycle_scope(scope_text)

        if has_time_scope:
            if frame.time_scope_kind == "none" or frame.time_field is None:
                raise LLMResponseValidationError(
                    "查询计划包含时间范围，但semantic_frame没有声明时间语义和time_field"
                )
            if frame.time_scope_kind == "entity_lifecycle" and not lifecycle_requested:
                entity_table = (
                    frame.distinct_key.table_name
                    if frame.distinct_key is not None
                    else frame.time_field.table_name
                )
                candidates = cls._fact_time_candidates(
                    snapshot,
                    entity_table,
                    field_meanings,
                )
                candidate_hint = (
                    "；Schema关系中的业务事件时间候选：" + "、".join(candidates)
                    if candidates
                    else ""
                )
                raise LLMResponseValidationError(
                    "用户未表达新增、创建、注册、录入或建档等生命周期意图，"
                    "不能把时间绑定到实体主数据生命周期"
                    + candidate_hint
                )
            if frame.time_scope_kind == "business_event":
                if frame.fact_table is None:
                    raise LLMResponseValidationError(
                        "业务事件时间查询必须声明fact_table"
                    )
                if frame.time_field.table_name != frame.fact_table:
                    raise LLMResponseValidationError(
                        "业务事件时间必须绑定到fact_table字段，不能绑定维度表时间"
                    )
                meaning = field_meanings.get(
                    (frame.time_field.table_name, frame.time_field.column_name),
                    "",
                )
                if cls._is_audit_time(frame.time_field.column_name, meaning):
                    entity_table = (
                        frame.distinct_key.table_name
                        if frame.distinct_key is not None
                        else frame.time_field.table_name
                    )
                    candidates = cls._fact_time_candidates(
                        snapshot,
                        entity_table,
                        field_meanings,
                    )
                    candidate_hint = (
                        "；Schema关系中的业务事件时间候选："
                        + "、".join(candidates)
                        if candidates
                        else ""
                    )
                    raise LLMResponseValidationError(
                        "业务事件时间不能使用created_at/updated_at等审计时间；"
                        "请选择关联事实表的业务日期"
                        + candidate_hint
                    )
            sql_key = cls._sql_key(plan.sql)
            if cls._semantic_key(frame.time_field.column_name) not in sql_key:
                raise LLMResponseValidationError(
                    "semantic_frame.time_field未实际用于SQL"
                )

        requires_distinct = cls._asks_for_distinct_entity_count(scope_text)
        if requires_distinct and frame.aggregation != "count_distinct":
            raise LLMResponseValidationError(
                "用户询问实体数量，必须使用count_distinct而不是COUNT(*)"
            )
        if frame.aggregation == "count_distinct":
            if frame.distinct_key is None:
                raise LLMResponseValidationError(
                    "count_distinct必须声明distinct_key"
                )
            distinct_expression = re.search(
                r"count\s*\(\s*distinct\s+([^)]+)\)",
                plan.sql,
                flags=re.IGNORECASE,
            )
            if (
                distinct_expression is None
                or cls._semantic_key(frame.distinct_key.column_name)
                not in cls._sql_key(distinct_expression.group(1))
            ):
                raise LLMResponseValidationError(
                    "SQL必须按semantic_frame.distinct_key执行COUNT(DISTINCT ...)"
                )

        if cls._asks_for_name_contains(scope_text):
            name_bindings = [
                binding
                for binding in frame.predicate_bindings
                if binding.predicate_type == "contains"
                and cls._is_name_field(
                    binding.field.column_name,
                    field_meanings.get(
                        (
                            binding.field.table_name,
                            binding.field.column_name,
                        ),
                        "",
                    ),
                )
            ]
            if not name_bindings:
                raise LLMResponseValidationError(
                    "用户明确要求名称包含文本，predicate_bindings必须绑定名称字段并使用contains，"
                    "不能改成地区、类型或其他属性"
                )

        snapshot_tables = {table.name for table in snapshot.tables}
        if frame.fact_table is not None and frame.fact_table not in snapshot_tables:
            raise LLMResponseValidationError(
                f"查询Agent的事实表不存在：{frame.fact_table}"
            )

    @classmethod
    def _semantic_scope_text(
        cls,
        question: str,
        conversation_context: dict[str, object] | None,
    ) -> str:
        parts = [question]
        if not conversation_context:
            return " ".join(parts)
        goal = conversation_context.get("resolved_goal")
        if isinstance(goal, dict):
            for key in ("metrics", "filters", "detail_requests"):
                values = goal.get(key)
                if isinstance(values, list):
                    parts.extend(value for value in values if isinstance(value, str))
        active = conversation_context.get("active_intent")
        if isinstance(active, dict):
            for key in ("summary",):
                value = active.get(key)
                if isinstance(value, str):
                    parts.append(value)
        return " ".join(parts)

    @staticmethod
    def _has_time_scope(value: str) -> bool:
        return bool(
            re.search(
                r"(?:\d{4}年)?(?:1[0-2]|0?[1-9])月份?|"
                r"(?:今年|去年|本年|本月|上月|这个月|当月|"
                r"本季度|上季度|第一季度|第二季度|第三季度|第四季度|"
                r"近\d+[天周月年])",
                value,
            )
        )

    @staticmethod
    def _has_lifecycle_scope(value: str) -> bool:
        return bool(
            re.search(
                r"(新增|新建|创建|注册|录入|建档|开户|入职|首次加入)",
                value,
            )
        )

    @staticmethod
    def _asks_for_distinct_entity_count(value: str) -> bool:
        return bool(re.search(r"(几|多少)\s*(家|名|位)", value))

    @staticmethod
    def _asks_for_name_contains(value: str) -> bool:
        return bool(
            re.search(
                r"(名称|名字|全称).{0,8}(包含|含有|带有|中有)",
                value,
            )
        )

    @staticmethod
    def _is_name_field(column_name: str, meaning: str) -> bool:
        normalized = column_name.lower()
        return (
            "name" in normalized
            or "名称" in meaning
            or "名字" in meaning
            or "全称" in meaning
        )

    @staticmethod
    def _is_audit_time(column_name: str, meaning: str) -> bool:
        normalized = column_name.lower()
        audit_columns = {
            "created_at",
            "updated_at",
            "create_time",
            "update_time",
            "created_time",
            "updated_time",
            "ctime",
            "mtime",
        }
        return normalized in audit_columns or bool(
            re.search(r"(创建时间|更新时间|录入时间|审计时间|系统时间)", meaning)
        )

    @classmethod
    def _fact_time_candidates(
        cls,
        snapshot: DatabaseSnapshot,
        entity_table: str,
        field_meanings: dict[tuple[str, str], str],
    ) -> list[str]:
        related_fact_tables = {
            relationship.source_table
            for relationship in snapshot.declared_relationships
            if relationship.target_table == entity_table
        }
        candidates: list[str] = []
        for table in snapshot.tables:
            if table.name not in related_fact_tables:
                continue
            for column in table.columns:
                if column.data_type.lower() not in {
                    "date",
                    "datetime",
                    "timestamp",
                }:
                    continue
                meaning = field_meanings.get((table.name, column.name), "")
                if not cls._is_audit_time(column.name, meaning):
                    candidates.append(f"{table.name}.{column.name}")
        return sorted(candidates)

    @staticmethod
    def _sql_key(value: str) -> str:
        return re.sub(r"[`\s]", "", value.lower())

    @staticmethod
    def _required_frame_from_validation(
        validation_message: str,
    ) -> dict[str, object] | None:
        marker = "Schema关系中的业务事件时间候选："
        if marker not in validation_message:
            return None
        candidate_text = validation_message.split(marker, 1)[1]
        candidates = re.findall(
            r"([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)",
            candidate_text,
        )
        if not candidates:
            return None

        def candidate_score(candidate: str) -> tuple[int, str]:
            _, column_name = candidate.split(".", 1)
            penalty_tokens = (
                "required",
                "expected",
                "deadline",
                "due",
                "end",
                "updated",
                "created",
            )
            penalty = sum(token in column_name.lower() for token in penalty_tokens)
            return penalty, candidate

        selected = min(candidates, key=candidate_score)
        table_name, column_name = selected.split(".", 1)
        return {
            "fact_table": table_name,
            "time_scope_kind": "business_event",
            "time_field": {
                "table_name": table_name,
                "column_name": column_name,
            },
            "source": "deterministic_schema_relationship_guard",
        }

    @staticmethod
    def _attempt_history(attempts: list[QueryAttempt]) -> list[dict[str, object]]:
        return [
            {
                "attempt_number": attempt.attempt_number,
                "plan_type": attempt.plan.plan_type,
                "intent": attempt.plan.intent.model_dump(mode="json"),
                "sql": attempt.plan.sql,
                "result": attempt.result.model_dump(mode="json"),
                "assessment": (
                    attempt.assessment.model_dump(mode="json")
                    if attempt.assessment is not None
                    else None
                ),
            }
            for attempt in attempts
        ]

    @classmethod
    def _result_repair_context(
        cls,
        attempts: list[QueryAttempt],
        assessment: QueryResultAssessment,
    ) -> dict[str, object]:
        latest = attempts[-1]
        return {
            "attempt_history": cls._attempt_history(attempts),
            "previous_sql": latest.plan.sql,
            "previous_plan_type": latest.plan.plan_type,
            "execution_status": latest.result.status,
            "query_result": latest.result.model_dump(mode="json"),
            "result_assessment": assessment.model_dump(mode="json"),
            "instruction": (
                assessment.next_action or "根据质检问题重新规划完整查询，避免重复上一轮。"
            ),
        }

    @staticmethod
    def _physical_table_name(
        reference: str,
        tables: dict[str, set[str]],
    ) -> str:
        cleaned = reference.strip().replace("`", "")
        if cleaned in tables:
            return cleaned
        match = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\s+(?:AS\s+)?[A-Za-z_][A-Za-z0-9_]*",
            cleaned,
            flags=re.IGNORECASE,
        )
        if match and match.group(1) in tables:
            return match.group(1)
        return cleaned

    @staticmethod
    def _add_usage(left: LLMTokenUsage, right: LLMTokenUsage) -> LLMTokenUsage:
        return LLMTokenUsage(
            prompt_tokens=left.prompt_tokens + right.prompt_tokens,
            completion_tokens=left.completion_tokens + right.completion_tokens,
            total_tokens=left.total_tokens + right.total_tokens,
        )
