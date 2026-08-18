import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.adapters.database import (
    DatabaseAdapterFactory,
    DatabaseQueryError,
    DatabaseWriteRequest,
    get_dialect,
)
from app.adapters.database.base import BaseDatabaseAdapter
from app.agents.database_action import ActionSQLBuilder, DatabaseActionPlanningAgent
from app.core.exceptions import (
    DatabaseActionStateError,
    LLMResponseValidationError,
)
from app.models import (
    ActionExecution,
    ActionLookupReference,
    ActionLookupResolution,
    ActionPlanningStep,
    ActionPreview,
    ActionSafetyCheck,
    DatabaseActionDraft,
    DatabaseActionRecord,
    DatabaseSnapshot,
    LLMTokenUsage,
    UserPrincipal,
    WorkflowStatus,
)
from app.repositories.database_action import DatabaseActionRepository
from app.repositories.database_snapshot import DatabaseSnapshotRepository
from app.repositories.query_session import QuerySessionRepository
from app.services.database_connection import DatabaseConnectionService
from app.services.effective_semantics import EffectiveSemanticResolver


class DatabaseActionService:
    def __init__(
        self,
        action_repository: DatabaseActionRepository,
        session_repository: QuerySessionRepository,
        snapshot_repository: DatabaseSnapshotRepository,
        semantic_resolver: EffectiveSemanticResolver,
        planning_agent: DatabaseActionPlanningAgent,
        connection_service: DatabaseConnectionService | BaseDatabaseAdapter,
        adapter_factory: DatabaseAdapterFactory | BaseDatabaseAdapter,
        *,
        max_affected_rows: int = 100,
        max_planning_rounds: int = 3,
        graph_checkpoint_path: Path | None = None,
    ) -> None:
        self.action_repository = action_repository
        self.session_repository = session_repository
        self.snapshot_repository = snapshot_repository
        self.semantic_resolver = semantic_resolver
        self.planning_agent = planning_agent
        if isinstance(connection_service, DatabaseConnectionService):
            self.connection_service: DatabaseConnectionService | None = connection_service
            assert isinstance(adapter_factory, DatabaseAdapterFactory)
            self.adapter_factory: DatabaseAdapterFactory | None = adapter_factory
            self.legacy_read_adapter: BaseDatabaseAdapter | None = None
            self.legacy_write_adapter: BaseDatabaseAdapter | None = None
        else:
            self.connection_service = None
            self.adapter_factory = None
            self.legacy_read_adapter = connection_service
            self.legacy_write_adapter = adapter_factory
        self.max_affected_rows = max_affected_rows
        self.max_planning_rounds = max_planning_rounds
        self.graph_runner = None
        if graph_checkpoint_path is not None:
            from app.graphs.action import ActionGraphRunner

            self.graph_runner = ActionGraphRunner(
                self,
                graph_checkpoint_path,
            )

    async def plan(
        self,
        session_id: str,
        message: str,
        principal: UserPrincipal,
        conversation_context: dict[str, object] | None = None,
    ) -> DatabaseActionRecord:
        if self.graph_runner is not None:
            return await self.graph_runner.plan(
                action_id=self._new_id(),
                session_id=session_id,
                message=message,
                principal=principal,
                conversation_context=conversation_context,
            )
        return await self._plan_legacy(
            session_id,
            message,
            principal,
            conversation_context,
        )

    async def _plan_legacy(
        self,
        session_id: str,
        message: str,
        principal: UserPrincipal,
        conversation_context: dict[str, object] | None = None,
    ) -> DatabaseActionRecord:
        session = await run_in_threadpool(self.session_repository.get, session_id)
        snapshot = await run_in_threadpool(
            self.snapshot_repository.get,
            session.snapshot_id,
        )
        semantics = await self.semantic_resolver.resolve(snapshot)
        if self.connection_service is not None and self.adapter_factory is not None:
            read_config = await self.connection_service.resolve_snapshot(snapshot)
            read_adapter = self.adapter_factory.create(read_config)
        else:
            assert self.legacy_read_adapter is not None
            read_adapter = self.legacy_read_adapter
        sql_builder = ActionSQLBuilder(get_dialect(snapshot.source.database_type))
        provider = ""
        model = ""
        usage = LLMTokenUsage()
        planning_context: dict[str, object] | None = None
        planning_steps: list[ActionPlanningStep] = []
        draft: DatabaseActionDraft | None = None
        lookup_resolutions: list[ActionLookupResolution] = []

        for round_number in range(1, self.max_planning_rounds + 1):
            try:
                candidate, provider, model, round_usage = await self.planning_agent.plan(
                    snapshot,
                    message,
                    semantics.payload,
                    conversation_context,
                    planning_context,
                )
                usage = self._add_usage(usage, round_usage)
                candidate = self._normalize_draft(
                    snapshot,
                    candidate,
                    semantics.field_sources,
                    semantics.field_meanings,
                )
            except LLMResponseValidationError as exc:
                if round_number >= self.max_planning_rounds:
                    raise
                planning_context = {
                    "round_number": round_number,
                    "validation_error": exc.message,
                    "instruction": ("修正目标表、字段、外键lookup或结构化协议后重新生成完整草案。"),
                }
                continue

            resolved_candidate, lookup_resolutions = await self._resolve_value_lookups(
                candidate,
                read_adapter,
                sql_builder,
            )
            unresolved = [
                resolution for resolution in lookup_resolutions if resolution.status != "resolved"
            ]
            if not unresolved:
                draft = resolved_candidate
                planning_steps.append(
                    ActionPlanningStep(
                        round_number=round_number,
                        summary=candidate.summary,
                        outcome="resolved",
                        lookup_resolutions=lookup_resolutions,
                        message=(
                            f"已唯一解析 {len(lookup_resolutions)} 个跨表业务值。"
                            if lookup_resolutions
                            else "草案不需要跨表取值，可以进入影响预览。"
                        ),
                    )
                )
                break

            final_round = round_number >= self.max_planning_rounds
            planning_steps.append(
                ActionPlanningStep(
                    round_number=round_number,
                    summary=candidate.summary,
                    outcome="blocked" if final_round else "retrying",
                    lookup_resolutions=lookup_resolutions,
                    message=self._lookup_round_message(unresolved, final_round),
                )
            )
            draft = candidate
            if final_round:
                return await self._blocked_lookup_record(
                    session_id=session_id,
                    snapshot=snapshot,
                    message=message,
                    principal=principal,
                    provider=provider,
                    model=model,
                    usage=usage,
                    draft=candidate,
                    planning_steps=planning_steps,
                    lookup_resolutions=lookup_resolutions,
                    semantic_sources=semantics.sources,
                )
            planning_context = {
                "round_number": round_number,
                "previous_draft": candidate.model_dump(mode="json"),
                "lookup_resolutions": [
                    resolution.model_dump(mode="json") for resolution in lookup_resolutions
                ],
                "instruction": (
                    "根据真实lookup结果收紧或修正条件。不得猜测ID；若没有唯一结果，"
                    "继续使用数据库证据消歧。"
                ),
            }

        if draft is None:
            raise LLMResponseValidationError("数据库操作规划Agent没有生成可执行草案")
        built = sql_builder.build(draft, max_rows=self.max_affected_rows)
        preview = await self._preview(draft, built, read_adapter)
        checks = [
            ActionSafetyCheck(
                code="lookup_values_resolved",
                passed=True,
                message=(
                    f"已通过只读查询唯一解析 {len(lookup_resolutions)} 个跨表业务值"
                    if lookup_resolutions
                    else "本次写入不需要跨表业务值解析"
                ),
            ),
            *self._safety_checks(snapshot, draft, preview.matched_row_count),
        ]
        can_execute = all(check.passed for check in checks)
        now = datetime.now(UTC)
        record = DatabaseActionRecord(
            action_id=self._new_id(),
            session_id=session_id,
            snapshot_id=snapshot.snapshot_id,
            database_name=snapshot.database.name,
            user_message=message,
            requested_by=principal.username,
            requested_by_role=principal.role,
            created_at=now,
            updated_at=now,
            status="pending_confirmation" if can_execute else "blocked",
            provider=provider,
            model=model,
            usage=usage,
            draft=draft,
            parameterized_sql=built.statement,
            sql_parameters=list(built.parameters),
            sql_parameter_values=built.parameters,
            display_sql=built.display_statement,
            preview=preview,
            preview_signature=self._preview_signature_values(
                snapshot_id=snapshot.snapshot_id,
                draft=draft,
                parameterized_sql=built.statement,
                parameters=built.parameters,
                preview=preview,
            ),
            safety_checks=checks,
            semantic_sources=self._used_semantic_sources(
                draft,
                semantics.sources,
            ),
            planning_steps=planning_steps,
            lookup_resolutions=lookup_resolutions,
        )
        await run_in_threadpool(self.action_repository.save, record)
        await self._touch_session(session_id, message)
        return record

    async def get(self, action_id: str) -> DatabaseActionRecord:
        return await run_in_threadpool(self.action_repository.get, action_id)

    async def list_for_session(self, session_id: str) -> list[DatabaseActionRecord]:
        records = await run_in_threadpool(
            self.action_repository.list_for_session,
            session_id,
        )
        return sorted(records, key=lambda record: record.created_at)

    async def _read_adapter(
        self,
        snapshot: DatabaseSnapshot,
    ) -> BaseDatabaseAdapter:
        if self.connection_service is not None and self.adapter_factory is not None:
            config = await self.connection_service.resolve_snapshot(snapshot)
            return self.adapter_factory.create(config)
        assert self.legacy_read_adapter is not None
        return self.legacy_read_adapter

    async def cancel(
        self,
        action_id: str,
        principal: UserPrincipal,
    ) -> DatabaseActionRecord:
        record = await self.get(action_id)
        self._validate_confirmable(record)
        if self.graph_runner is not None:
            return await self.graph_runner.cancel(
                action_id=action_id,
                principal=principal,
            )
        return await self._cancel_pending_record(record, principal)

    async def _cancel_pending_record(
        self,
        record: DatabaseActionRecord,
        principal: UserPrincipal,
    ) -> DatabaseActionRecord:
        self._validate_confirmable(record)
        updated = record.model_copy(
            update={
                "status": "cancelled",
                "updated_at": datetime.now(UTC),
                "cancelled_by": principal.username,
            }
        )
        await run_in_threadpool(self.action_repository.save, updated)
        return updated

    async def workflow_status(self, action_id: str) -> WorkflowStatus:
        if self.graph_runner is None:
            raise DatabaseActionStateError(
                "当前数据库操作没有启用LangGraph工作流。"
            )
        return await self.graph_runner.status(action_id)

    async def confirm(
        self,
        action_id: str,
        principal: UserPrincipal,
    ) -> DatabaseActionRecord:
        if self.graph_runner is not None:
            return await self.graph_runner.confirm(
                action_id=action_id,
                principal=principal,
            )
        record = await self.get(action_id)
        self._validate_confirmable(record)
        return await self._execute_confirmed_record(record, principal)

    @staticmethod
    def _validate_confirmable(record: DatabaseActionRecord) -> None:
        if record.status != "pending_confirmation":
            raise DatabaseActionStateError("该数据库操作已经处理，不能重复执行")

    async def _execute_confirmed_record(
        self,
        record: DatabaseActionRecord,
        principal: UserPrincipal,
    ) -> DatabaseActionRecord:
        current = await self.get(record.action_id)
        if current.status == "executing":
            recovery = current.model_copy(
                update={
                    "status": "recovery_required",
                    "updated_at": datetime.now(UTC),
                    "error": (
                        "上次执行在事务结果写回操作记录前中断，系统不会自动重复写入；"
                        "请核对数据库实际结果后重新生成操作计划。"
                    ),
                }
            )
            await run_in_threadpool(
                self.action_repository.save,
                recovery,
            )
            return recovery
        self._validate_confirmable(current)
        if self._preview_signature(current) != self._preview_signature(record):
            raise DatabaseActionStateError(
                "待确认操作与原预览不一致，请重新生成操作计划"
            )
        self._validate_preview_integrity(current)
        self._validate_preview_integrity(record)
        executing = current.model_copy(
            update={
                "status": "executing",
                "updated_at": datetime.now(UTC),
                "confirmed_by": principal.username,
            }
        )
        await run_in_threadpool(self.action_repository.save, executing)

        snapshot = await run_in_threadpool(
            self.snapshot_repository.get,
            executing.snapshot_id,
        )
        draft = executing.draft
        table = next(table for table in snapshot.tables if table.name == draft.table_name)
        if self.connection_service is not None and self.adapter_factory is not None:
            write_config = await self.connection_service.resolve_snapshot(snapshot, write=True)
            write_adapter = self.adapter_factory.create(write_config)
        else:
            assert self.legacy_write_adapter is not None
            write_adapter = self.legacy_write_adapter
        sql_builder = ActionSQLBuilder(get_dialect(snapshot.source.database_type))
        built = sql_builder.build(draft, max_rows=self.max_affected_rows)
        try:
            result = await run_in_threadpool(
                write_adapter.execute_write_transaction,
                DatabaseWriteRequest(
                    action_type=draft.action_type,
                    table_name=draft.table_name,
                    sql=built.statement,
                    parameters=built.parameters,
                    lock_sql=built.lock_statement,
                    lock_parameters=built.preview_parameters,
                    expected_target_count=(
                        0
                        if draft.action_type == "INSERT"
                        else executing.preview.matched_row_count
                    ),
                    max_affected_rows=self.max_affected_rows,
                    primary_key_columns=tuple(table.primary_key),
                    expected_before_rows=tuple(
                        executing.preview.sample_rows
                    ),
                    expected_values=tuple(
                        (assignment.column_name, assignment.value)
                        for assignment in draft.assignments
                    ),
                    insert_lookup_sql=built.insert_lookup_statement,
                    insert_lookup_parameters=built.insert_lookup_parameters,
                ),
            )
        except DatabaseQueryError as exc:
            failed = executing.model_copy(
                update={
                    "status": "failed",
                    "updated_at": datetime.now(UTC),
                    "error": str(exc),
                    "confirmed_by": principal.username,
                }
            )
            await run_in_threadpool(self.action_repository.save, failed)
            return failed

        now = datetime.now(UTC)
        executed = executing.model_copy(
            update={
                "status": "executed",
                "updated_at": now,
                "confirmed_by": principal.username,
                "execution": ActionExecution(
                    executed_at=now,
                    affected_row_count=result.affected_row_count,
                    verification_passed=result.verification_passed,
                    before_rows=result.before_rows,
                    after_rows=result.after_rows,
                    message=self._execution_message(
                        draft.action_type,
                        result.affected_row_count,
                    ),
                ),
            }
        )
        await run_in_threadpool(self.action_repository.save, executed)
        return executed

    async def _resolve_value_lookups(
        self,
        draft: DatabaseActionDraft,
        read_adapter: BaseDatabaseAdapter,
        sql_builder: ActionSQLBuilder,
    ) -> tuple[DatabaseActionDraft, list[ActionLookupResolution]]:
        resolutions: list[ActionLookupResolution] = []
        for lookup in draft.value_lookups:
            built = sql_builder.build_lookup(lookup)
            try:
                result = await run_in_threadpool(
                    read_adapter.execute_select,
                    built.statement,
                    10,
                    built.parameters,
                )
            except DatabaseQueryError as exc:
                resolutions.append(
                    ActionLookupResolution(
                        lookup_id=lookup.lookup_id,
                        purpose=lookup.purpose,
                        target_kind=lookup.target_kind,
                        target_column_name=lookup.target_column_name,
                        source_table=lookup.source_table,
                        source_value_column=lookup.source_value_column,
                        display_sql=built.display_statement,
                        status="failed",
                        matched_row_count=0,
                        message=f"跨表取值查询失败：{str(exc)[:300]}",
                    )
                )
                continue

            matched_count = len(result.rows)
            if matched_count == 1 and not result.truncated:
                status = "resolved"
                resolved_value = result.rows[0].get(lookup.source_value_column)
                message = (
                    f"唯一匹配 {lookup.source_table}.{lookup.source_value_column}={resolved_value}"
                )
            elif matched_count == 0:
                status = "not_found"
                resolved_value = None
                message = "没有匹配到跨表业务值，需要修正取值条件。"
            else:
                status = "ambiguous"
                resolved_value = None
                count_label = f"{matched_count}+" if result.truncated else str(matched_count)
                message = f"匹配到 {count_label} 条候选记录，不能猜测写入值。"
            resolutions.append(
                ActionLookupResolution(
                    lookup_id=lookup.lookup_id,
                    purpose=lookup.purpose,
                    target_kind=lookup.target_kind,
                    target_column_name=lookup.target_column_name,
                    source_table=lookup.source_table,
                    source_value_column=lookup.source_value_column,
                    display_sql=built.display_statement,
                    status=status,
                    matched_row_count=matched_count,
                    truncated=result.truncated,
                    rows=result.rows,
                    resolved_value=resolved_value,
                    message=message,
                )
            )

        values = {
            resolution.lookup_id: resolution.resolved_value
            for resolution in resolutions
            if resolution.status == "resolved"
        }
        if len(values) != len(draft.value_lookups):
            return draft, resolutions
        assignments = [
            assignment.model_copy(
                update={
                    "value": values[assignment.value.lookup_id]
                    if isinstance(assignment.value, ActionLookupReference)
                    else assignment.value
                }
            )
            for assignment in draft.assignments
        ]
        conditions = [
            condition.model_copy(
                update={
                    "value": values[condition.value.lookup_id]
                    if isinstance(condition.value, ActionLookupReference)
                    else condition.value
                }
            )
            for condition in draft.conditions
        ]
        return (
            draft.model_copy(
                update={
                    "assignments": assignments,
                    "conditions": conditions,
                }
            ),
            resolutions,
        )

    async def _create_preview_record(
        self,
        *,
        action_id: str,
        session_id: str,
        snapshot: DatabaseSnapshot,
        message: str,
        principal: UserPrincipal,
        provider: str,
        model: str,
        usage: LLMTokenUsage,
        draft: DatabaseActionDraft,
        planning_steps: list[ActionPlanningStep],
        lookup_resolutions: list[ActionLookupResolution],
        semantic_sources: list,
        workflow_engine: Literal["legacy", "langgraph"],
    ) -> DatabaseActionRecord:
        sql_builder = ActionSQLBuilder(
            get_dialect(snapshot.source.database_type)
        )
        built = sql_builder.build(draft, max_rows=self.max_affected_rows)
        preview = await self._preview(
            draft,
            built,
            await self._read_adapter(snapshot),
        )
        checks = [
            ActionSafetyCheck(
                code="lookup_values_resolved",
                passed=True,
                message=(
                    f"已通过只读查询唯一解析 {len(lookup_resolutions)} 个跨表业务值"
                    if lookup_resolutions
                    else "本次写入不需要跨表业务值解析"
                ),
            ),
            *self._safety_checks(
                snapshot,
                draft,
                preview.matched_row_count,
            ),
        ]
        now = datetime.now(UTC)
        record = DatabaseActionRecord(
            action_id=action_id,
            session_id=session_id,
            snapshot_id=snapshot.snapshot_id,
            database_name=snapshot.database.name,
            user_message=message,
            requested_by=principal.username,
            requested_by_role=principal.role,
            created_at=now,
            updated_at=now,
            status=(
                "pending_confirmation"
                if all(check.passed for check in checks)
                else "blocked"
            ),
            workflow_engine=workflow_engine,
            workflow_thread_id=(
                action_id if workflow_engine == "langgraph" else None
            ),
            provider=provider,
            model=model,
            usage=usage,
            draft=draft,
            parameterized_sql=built.statement,
            sql_parameters=list(built.parameters),
            sql_parameter_values=built.parameters,
            display_sql=built.display_statement,
            preview=preview,
            safety_checks=checks,
            semantic_sources=self._used_semantic_sources(
                draft,
                semantic_sources,
            ),
            planning_steps=planning_steps,
            lookup_resolutions=lookup_resolutions,
        )
        await run_in_threadpool(self.action_repository.save, record)
        await self._touch_session(session_id, message)
        return record

    async def _blocked_lookup_record(
        self,
        *,
        action_id: str | None = None,
        session_id: str,
        snapshot: DatabaseSnapshot,
        message: str,
        principal: UserPrincipal,
        provider: str,
        model: str,
        usage: LLMTokenUsage,
        draft: DatabaseActionDraft,
        planning_steps: list[ActionPlanningStep],
        lookup_resolutions: list[ActionLookupResolution],
        semantic_sources: list,
        workflow_engine: Literal["legacy", "langgraph"] = "legacy",
    ) -> DatabaseActionRecord:
        now = datetime.now(UTC)
        unresolved = [
            resolution for resolution in lookup_resolutions if resolution.status != "resolved"
        ]
        record = DatabaseActionRecord(
            action_id=action_id or self._new_id(),
            session_id=session_id,
            snapshot_id=snapshot.snapshot_id,
            database_name=snapshot.database.name,
            user_message=message,
            requested_by=principal.username,
            requested_by_role=principal.role,
            created_at=now,
            updated_at=now,
            status="blocked",
            workflow_engine=workflow_engine,
            workflow_thread_id=(
                action_id
                if workflow_engine == "langgraph" and action_id is not None
                else None
            ),
            provider=provider,
            model=model,
            usage=usage,
            draft=draft,
            parameterized_sql="-- 未生成写入SQL：跨表业务值没有唯一解析",
            sql_parameters=[],
            display_sql="-- 未生成写入SQL：跨表业务值没有唯一解析",
            preview=ActionPreview(
                matched_row_count=0,
                columns=[],
            ),
            safety_checks=[
                ActionSafetyCheck(
                    code="lookup_values_resolved",
                    passed=False,
                    message=self._lookup_round_message(unresolved, True),
                ),
                ActionSafetyCheck(
                    code="write_sql_generated",
                    passed=False,
                    message="未生成、未预览、未执行任何写入SQL",
                ),
            ],
            semantic_sources=self._used_semantic_sources(
                draft,
                semantic_sources,
            ),
            planning_steps=planning_steps,
            lookup_resolutions=lookup_resolutions,
            error=self._lookup_round_message(unresolved, True),
        )
        await run_in_threadpool(self.action_repository.save, record)
        await self._touch_session(session_id, message)
        return record

    async def _touch_session(self, session_id: str, message: str) -> None:
        session = await run_in_threadpool(self.session_repository.get, session_id)
        updated = session.model_copy(
            update={
                "title": (
                    self._session_title(message)
                    if not session.turns and session.title == "新分析对话"
                    else session.title
                ),
                "updated_at": datetime.now(UTC),
            }
        )
        await run_in_threadpool(self.session_repository.save, updated)

    @staticmethod
    def _session_title(message: str) -> str:
        compact = " ".join(message.split())
        return compact[:32] + ("…" if len(compact) > 32 else "")

    async def _preview(
        self,
        draft,
        built,
        read_adapter: BaseDatabaseAdapter,
    ) -> ActionPreview:
        if draft.action_type == "INSERT":
            proposed = {
                assignment.column_name: assignment.value for assignment in draft.assignments
            }
            return ActionPreview(
                matched_row_count=1,
                columns=list(proposed),
                proposed_rows=[proposed],
            )
        count_result = await run_in_threadpool(
            read_adapter.execute_select,
            built.count_statement,
            1,
            built.count_parameters,
        )
        matched = int(count_result.rows[0]["matched_row_count"]) if count_result.rows else 0
        preview_result = await run_in_threadpool(
            read_adapter.execute_select,
            built.preview_statement,
            self.max_affected_rows,
            built.preview_parameters,
        )
        return ActionPreview(
            matched_row_count=matched,
            columns=preview_result.columns,
            sample_rows=preview_result.rows,
            truncated=matched > len(preview_result.rows),
        )

    def _preview_signature(
        self,
        record: DatabaseActionRecord,
    ) -> str:
        parameters = record.sql_parameter_values
        if not parameters:
            parameters = ActionSQLBuilder().build(
                record.draft,
                max_rows=self.max_affected_rows,
            ).parameters
        return self._preview_signature_values(
            snapshot_id=record.snapshot_id,
            draft=record.draft,
            parameterized_sql=record.parameterized_sql,
            parameters=parameters,
            preview=record.preview,
        )

    def _validate_preview_integrity(
        self,
        record: DatabaseActionRecord,
    ) -> None:
        if (
            record.preview_signature
            and record.preview_signature != self._preview_signature(record)
        ):
            raise DatabaseActionStateError(
                "写操作草案、参数或预览内容已发生变化，请重新生成操作计划"
            )

    @staticmethod
    def _preview_signature_values(
        *,
        snapshot_id: str,
        draft: DatabaseActionDraft,
        parameterized_sql: str,
        parameters: dict,
        preview: ActionPreview,
    ) -> str:
        payload = {
            "snapshot_id": snapshot_id,
            "draft": draft.model_dump(mode="json"),
            "parameterized_sql": parameterized_sql,
            "parameters": parameters,
            "preview": preview.model_dump(mode="json"),
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _safety_checks(
        self,
        snapshot: DatabaseSnapshot,
        draft: DatabaseActionDraft,
        matched_row_count: int,
    ) -> list[ActionSafetyCheck]:
        table = next(table for table in snapshot.tables if table.name == draft.table_name)
        return [
            ActionSafetyCheck(
                code="single_base_table",
                passed=table.table_type == "BASE TABLE",
                message=(
                    "目标是可写基础表"
                    if table.table_type == "BASE TABLE"
                    else "视图和系统表不允许写入"
                ),
            ),
            ActionSafetyCheck(
                code="bounded_scope",
                passed=matched_row_count <= self.max_affected_rows,
                message=(
                    f"预计影响 {matched_row_count} 行，未超过 {self.max_affected_rows} 行上限"
                    if matched_row_count <= self.max_affected_rows
                    else f"预计影响 {matched_row_count} 行，超过安全上限"
                ),
            ),
            ActionSafetyCheck(
                code="target_exists",
                passed=draft.action_type == "INSERT" or matched_row_count > 0,
                message=(
                    "新增操作将创建一条记录"
                    if draft.action_type == "INSERT"
                    else f"已精确匹配 {matched_row_count} 行目标数据"
                    if matched_row_count > 0
                    else "没有匹配到目标数据，禁止进入确认执行"
                ),
            ),
            ActionSafetyCheck(
                code="where_required",
                passed=draft.action_type == "INSERT" or bool(draft.conditions),
                message=(
                    "INSERT不需要WHERE条件"
                    if draft.action_type == "INSERT"
                    else "已包含明确的WHERE条件"
                    if draft.conditions
                    else "UPDATE或DELETE缺少WHERE条件"
                ),
            ),
            ActionSafetyCheck(
                code="primary_key_verification",
                passed=draft.action_type == "INSERT" or bool(table.primary_key),
                message=(
                    "新增记录将在事务内回查"
                    if draft.action_type == "INSERT"
                    else "目标表存在主键，可在事务内逐行回查"
                    if table.primary_key
                    else "目标表没有主键，无法可靠回查修改结果"
                ),
            ),
        ]

    @staticmethod
    def _normalize_draft(
        snapshot: DatabaseSnapshot,
        draft: DatabaseActionDraft,
        field_sources: dict[tuple[str, str], str],
        field_meanings: dict[tuple[str, str], str],
    ) -> DatabaseActionDraft:
        tables = {table.name: table for table in snapshot.tables}
        table = tables.get(draft.table_name)
        if table is None:
            raise LLMResponseValidationError(
                f"数据库操作规划Agent引用了不存在的表：{draft.table_name}"
            )
        column_names = {column.name for column in table.columns}
        referenced_columns = {assignment.column_name for assignment in draft.assignments} | {
            condition.column_name for condition in draft.conditions
        }
        unknown_columns = sorted(referenced_columns - column_names)
        if unknown_columns:
            raise LLMResponseValidationError(
                "数据库操作规划Agent引用了不存在的字段：" + ", ".join(unknown_columns)
            )
        if draft.action_type in {"UPDATE", "DELETE"} and not draft.conditions:
            raise LLMResponseValidationError("UPDATE和DELETE必须包含定位条件")
        if draft.action_type == "DELETE" and draft.assignments:
            raise LLMResponseValidationError("DELETE不能包含字段赋值")
        if draft.action_type in {"INSERT", "UPDATE"} and not draft.assignments:
            raise LLMResponseValidationError(f"{draft.action_type}必须包含字段赋值")

        lookup_ids = [lookup.lookup_id for lookup in draft.value_lookups]
        if len(lookup_ids) != len(set(lookup_ids)):
            raise LLMResponseValidationError("数据库操作规划Agent生成了重复的lookup_id")
        lookups = {lookup.lookup_id: lookup for lookup in draft.value_lookups}
        referenced_lookups: dict[str, tuple[str, str]] = {}
        for assignment in draft.assignments:
            if isinstance(assignment.value, ActionLookupReference):
                referenced_lookups[assignment.value.lookup_id] = (
                    "assignment",
                    assignment.column_name,
                )
        for condition in draft.conditions:
            if isinstance(condition.value, ActionLookupReference):
                referenced_lookups[condition.value.lookup_id] = (
                    "condition",
                    condition.column_name,
                )
        unknown_lookup_ids = sorted(set(referenced_lookups) - set(lookups))
        if unknown_lookup_ids:
            raise LLMResponseValidationError(
                "数据库操作规划Agent引用了未定义的跨表取值：" + ", ".join(unknown_lookup_ids)
            )
        unused_lookup_ids = sorted(set(lookups) - set(referenced_lookups))
        if unused_lookup_ids:
            raise LLMResponseValidationError(
                "数据库操作规划Agent生成了未被字段使用的跨表取值：" + ", ".join(unused_lookup_ids)
            )

        relationship_edges = {
            (
                relationship.source_table,
                source_column,
                relationship.target_table,
                target_column,
            )
            for relationship in snapshot.declared_relationships
            for source_column, target_column in zip(
                relationship.source_columns,
                relationship.target_columns,
                strict=True,
            )
        }
        for lookup in draft.value_lookups:
            expected_target = referenced_lookups[lookup.lookup_id]
            if expected_target != (lookup.target_kind, lookup.target_column_name):
                raise LLMResponseValidationError(
                    f"跨表取值 {lookup.lookup_id} 的目标字段声明不一致"
                )
            source_table = tables.get(lookup.source_table)
            if source_table is None:
                raise LLMResponseValidationError(f"跨表取值引用了不存在的表：{lookup.source_table}")
            source_columns = {column.name for column in source_table.columns}
            lookup_columns = {
                lookup.source_value_column,
                *(condition.column_name for condition in lookup.conditions),
            }
            unknown_lookup_columns = sorted(lookup_columns - source_columns)
            if unknown_lookup_columns:
                raise LLMResponseValidationError(
                    f"跨表取值 {lookup.lookup_id} 引用了不存在的字段："
                    + ", ".join(unknown_lookup_columns)
                )
            edge = (
                draft.table_name,
                lookup.target_column_name,
                lookup.source_table,
                lookup.source_value_column,
            )
            if edge not in relationship_edges:
                raise LLMResponseValidationError(
                    "跨表取值不符合已声明外键："
                    f"{draft.table_name}.{lookup.target_column_name} -> "
                    f"{lookup.source_table}.{lookup.source_value_column}"
                )

        normalized_mappings = []
        for mapping in draft.field_mappings:
            mapping_table = tables.get(mapping.table_name)
            mapping_columns = (
                {column.name for column in mapping_table.columns}
                if mapping_table is not None
                else set()
            )
            if mapping_table is None or mapping.column_name not in mapping_columns:
                raise LLMResponseValidationError(
                    "数据库操作规划Agent引用了不存在的字段映射："
                    f"{mapping.table_name}.{mapping.column_name}"
                )
            key = (mapping.table_name, mapping.column_name)
            normalized_mappings.append(
                mapping.model_copy(
                    update={
                        "source": field_sources.get(key, "schema_only"),
                        "semantic_meaning": field_meanings.get(
                            key,
                            mapping.semantic_meaning,
                        ),
                    }
                )
            )
        return draft.model_copy(update={"field_mappings": normalized_mappings})

    @staticmethod
    def _lookup_round_message(
        unresolved: list[ActionLookupResolution],
        final_round: bool,
    ) -> str:
        details = "；".join(
            f"{resolution.lookup_id}：{resolution.message}" for resolution in unresolved
        )
        prefix = (
            "跨表业务值在规划轮数内仍未唯一解析，操作已阻止。"
            if final_round
            else "跨表业务值尚未唯一解析，将携带真实候选继续规划。"
        )
        return f"{prefix}{details}"[:500]

    @staticmethod
    def _used_semantic_sources(
        draft: DatabaseActionDraft,
        semantic_sources: list,
    ) -> list:
        used_tables = {
            draft.table_name,
            *(lookup.source_table for lookup in draft.value_lookups),
            *(mapping.table_name for mapping in draft.field_mappings),
        }
        return [source for source in semantic_sources if source.table_name in used_tables]

    @staticmethod
    def _add_usage(left: LLMTokenUsage, right: LLMTokenUsage) -> LLMTokenUsage:
        return LLMTokenUsage(
            prompt_tokens=left.prompt_tokens + right.prompt_tokens,
            completion_tokens=left.completion_tokens + right.completion_tokens,
            total_tokens=left.total_tokens + right.total_tokens,
        )

    @staticmethod
    def _execution_message(action_type: str, affected_rows: int) -> str:
        labels = {"INSERT": "新增", "UPDATE": "更新", "DELETE": "删除"}
        return f"已完成{labels[action_type]}，数据库报告影响 {affected_rows} 行，回查通过。"

    @staticmethod
    def _new_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return f"action_{timestamp}_{uuid4().hex[:8]}"
