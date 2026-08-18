from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from starlette.concurrency import run_in_threadpool

from app.adapters.database import get_dialect
from app.agents.database_action import ActionSQLBuilder
from app.core.exceptions import (
    LLMResponseValidationError,
    WorkflowCheckpointNotFoundError,
)
from app.graphs.workflow import inspect_workflow, workflow_config
from app.models import (
    ActionLookupResolution,
    ActionPlanningStep,
    DatabaseActionDraft,
    DatabaseActionRecord,
    DatabaseSnapshot,
    LLMTokenUsage,
    QuerySemanticSource,
    UserPrincipal,
    WorkflowStatus,
)

from .state import ActionGraphState

if TYPE_CHECKING:
    from app.services.database_action import DatabaseActionService


class ActionGraphRunner:
    """Durable planning and execution graph for bounded database writes."""

    def __init__(
        self,
        service: "DatabaseActionService",
        checkpoint_path: Path,
    ) -> None:
        self.service = service
        self.checkpoint_path = checkpoint_path

    async def plan(
        self,
        *,
        action_id: str,
        session_id: str,
        message: str,
        principal: UserPrincipal,
        conversation_context: dict[str, object] | None,
    ) -> DatabaseActionRecord:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(
            str(self.checkpoint_path)
        ) as checkpointer:
            await checkpointer.setup()
            graph = self._build_graph().compile(
                checkpointer=checkpointer,
                name="database-action-graph",
            )
            final_state = await graph.ainvoke(
                {
                    "action_id": action_id,
                    "session_id": session_id,
                    "message": message,
                    "principal": principal.model_dump(mode="json"),
                    "conversation_context": conversation_context,
                    "planning_round": 1,
                    "max_planning_rounds": self.service.max_planning_rounds,
                    "planning_context": None,
                    "planning_steps": [],
                    "lookup_resolutions": [],
                    "provider": "",
                    "model": "",
                    "usage": LLMTokenUsage().model_dump(mode="json"),
                    "validation_error": None,
                },
                config=workflow_config(
                    action_id,
                    recursion_limit=self.service.max_planning_rounds * 4 + 16,
                ),
            )
        return DatabaseActionRecord.model_validate(final_state["record"])

    async def confirm(
        self,
        *,
        action_id: str,
        principal: UserPrincipal,
    ) -> DatabaseActionRecord:
        return await self._resume_confirmation(
            action_id=action_id,
            principal=principal,
            decision="confirm",
        )

    async def cancel(
        self,
        *,
        action_id: str,
        principal: UserPrincipal,
    ) -> DatabaseActionRecord:
        return await self._resume_confirmation(
            action_id=action_id,
            principal=principal,
            decision="cancel",
        )

    async def status(self, action_id: str) -> WorkflowStatus:
        async with AsyncSqliteSaver.from_conn_string(
            str(self.checkpoint_path)
        ) as checkpointer:
            await checkpointer.setup()
            graph = self._build_graph().compile(
                checkpointer=checkpointer,
                name="database-action-graph",
            )
            return await inspect_workflow(
                graph,
                workflow_id=action_id,
                workflow_kind="action",
            )

    async def _resume_confirmation(
        self,
        *,
        action_id: str,
        principal: UserPrincipal,
        decision: Literal["confirm", "cancel"],
    ) -> DatabaseActionRecord:
        record = await self.service.get(action_id)
        self.service._validate_confirmable(record)
        try:
            status = await self.status(action_id)
        except WorkflowCheckpointNotFoundError:
            status = None
        if status is None or status.status != "interrupted":
            if decision == "cancel":
                return await self.service._cancel_pending_record(
                    record,
                    principal,
                )
            return await self.service._execute_confirmed_record(
                record,
                principal,
            )
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(
            str(self.checkpoint_path)
        ) as checkpointer:
            await checkpointer.setup()
            graph = self._build_graph().compile(
                checkpointer=checkpointer,
                name="database-action-graph",
            )
            final_state = await graph.ainvoke(
                Command(
                    resume={
                        "decision": decision,
                        "principal": principal.model_dump(mode="json"),
                    }
                ),
                config=workflow_config(
                    action_id,
                    recursion_limit=self.service.max_planning_rounds * 4 + 16,
                ),
            )
        return DatabaseActionRecord.model_validate(final_state["record"])

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(ActionGraphState)
        graph.add_node("load_action_context", self._load_context)
        graph.add_node("plan_single_table_action", self._plan_draft)
        graph.add_node("resolve_cross_table_values", self._resolve_lookups)
        graph.add_node("prepare_action_replan", self._prepare_retry)
        graph.add_node("preview_target_rows", self._build_preview_record)
        graph.add_node("finalize_blocked_action", self._build_blocked_record)
        graph.add_node("await_user_confirmation", self._await_confirmation)
        graph.add_node(
            "execute_transaction_and_verify",
            self._execute_transaction_and_verify,
        )
        graph.add_edge(START, "load_action_context")
        graph.add_edge("load_action_context", "plan_single_table_action")
        graph.add_conditional_edges(
            "plan_single_table_action",
            self._route_after_plan,
            {
                "retry": "prepare_action_replan",
                "resolve": "resolve_cross_table_values",
                "blocked": "finalize_blocked_action",
            },
        )
        graph.add_conditional_edges(
            "resolve_cross_table_values",
            self._route_after_lookup,
            {
                "retry": "prepare_action_replan",
                "preview": "preview_target_rows",
                "blocked": "finalize_blocked_action",
            },
        )
        graph.add_edge("prepare_action_replan", "plan_single_table_action")
        graph.add_conditional_edges(
            "preview_target_rows",
            self._route_after_preview,
            {
                "wait": "await_user_confirmation",
                "finish": END,
            },
        )
        graph.add_conditional_edges(
            "await_user_confirmation",
            self._route_after_confirmation,
            {
                "execute": "execute_transaction_and_verify",
                "finish": END,
            },
        )
        graph.add_edge("execute_transaction_and_verify", END)
        graph.add_edge("finalize_blocked_action", END)
        return graph

    async def _load_context(
        self,
        state: ActionGraphState,
    ) -> dict[str, Any]:
        session = await run_in_threadpool(
            self.service.session_repository.get,
            state["session_id"],
        )
        snapshot = await run_in_threadpool(
            self.service.snapshot_repository.get,
            session.snapshot_id,
        )
        semantics = await self.service.semantic_resolver.resolve(snapshot)
        return {
            "snapshot": snapshot.model_dump(mode="json"),
            "semantic_payload": semantics.payload,
            "semantic_sources": [
                source.model_dump(mode="json") for source in semantics.sources
            ],
            "field_sources": self._serialize_field_map(
                semantics.field_sources
            ),
            "field_meanings": self._serialize_field_map(
                semantics.field_meanings
            ),
        }

    async def _plan_draft(
        self,
        state: ActionGraphState,
    ) -> dict[str, Any]:
        snapshot = DatabaseSnapshot.model_validate(state["snapshot"])
        usage = LLMTokenUsage.model_validate(state["usage"])
        try:
            draft, provider, model, round_usage = (
                await self.service.planning_agent.plan(
                    snapshot,
                    state["message"],
                    state["semantic_payload"],
                    state.get("conversation_context"),
                    self._repair_context(state),
                )
            )
            usage = self.service._add_usage(usage, round_usage)
            draft = self.service._normalize_draft(
                snapshot,
                draft,
                self._field_map(state["field_sources"]),
                self._field_map(state["field_meanings"]),
            )
        except LLMResponseValidationError as exc:
            return {
                "validation_error": exc.message,
                "usage": usage.model_dump(mode="json"),
            }
        return {
            "draft": draft.model_dump(mode="json"),
            "provider": provider,
            "model": model,
            "usage": usage.model_dump(mode="json"),
            "validation_error": None,
        }

    async def _resolve_lookups(
        self,
        state: ActionGraphState,
    ) -> dict[str, Any]:
        snapshot = DatabaseSnapshot.model_validate(state["snapshot"])
        draft = DatabaseActionDraft.model_validate(state["draft"])
        adapter = await self.service._read_adapter(snapshot)
        builder = ActionSQLBuilder(
            get_dialect(snapshot.source.database_type)
        )
        resolved, resolutions = await self.service._resolve_value_lookups(
            draft,
            adapter,
            builder,
        )
        unresolved = [
            resolution
            for resolution in resolutions
            if resolution.status != "resolved"
        ]
        final_round = (
            state["planning_round"] >= state["max_planning_rounds"]
        )
        steps = self._planning_steps(state)
        steps.append(
            ActionPlanningStep(
                round_number=state["planning_round"],
                summary=draft.summary,
                outcome=(
                    "blocked"
                    if unresolved and final_round
                    else "retrying"
                    if unresolved
                    else "resolved"
                ),
                lookup_resolutions=resolutions,
                message=(
                    self.service._lookup_round_message(
                        unresolved,
                        final_round,
                    )
                    if unresolved
                    else (
                        f"已唯一解析 {len(resolutions)} 个跨表业务值。"
                        if resolutions
                        else "草案不需要跨表取值，可以进入影响预览。"
                    )
                ),
            )
        )
        return {
            "draft": resolved.model_dump(mode="json"),
            "lookup_resolutions": [
                item.model_dump(mode="json") for item in resolutions
            ],
            "planning_steps": [
                step.model_dump(mode="json") for step in steps
            ],
        }

    async def _prepare_retry(
        self,
        state: ActionGraphState,
    ) -> dict[str, Any]:
        if state.get("validation_error"):
            repair = {
                "round_number": state["planning_round"],
                "validation_error": state["validation_error"],
                "instruction": (
                    "修正目标表、字段、外键lookup或结构化协议后"
                    "重新生成完整草案。"
                ),
            }
        else:
            repair = {
                "round_number": state["planning_round"],
                "previous_draft": state["draft"],
                "lookup_resolutions": state["lookup_resolutions"],
                "instruction": (
                    "根据真实lookup结果收紧或修正条件。不得猜测ID；"
                    "若没有唯一结果，继续使用数据库证据消歧。"
                ),
            }
        return {
            "planning_round": state["planning_round"] + 1,
            "planning_context": {
                "action_repair": repair,
            },
            "validation_error": None,
        }

    async def _build_preview_record(
        self,
        state: ActionGraphState,
    ) -> dict[str, Any]:
        record = await self.service._create_preview_record(
            action_id=state["action_id"],
            session_id=state["session_id"],
            snapshot=DatabaseSnapshot.model_validate(state["snapshot"]),
            message=state["message"],
            principal=UserPrincipal.model_validate(state["principal"]),
            provider=state["provider"],
            model=state["model"],
            usage=LLMTokenUsage.model_validate(state["usage"]),
            draft=DatabaseActionDraft.model_validate(state["draft"]),
            planning_steps=self._planning_steps(state),
            lookup_resolutions=self._lookup_resolutions(state),
            semantic_sources=self._semantic_sources(state),
            workflow_engine="langgraph",
        )
        return {"record": record.model_dump(mode="json")}

    async def _build_blocked_record(
        self,
        state: ActionGraphState,
    ) -> dict[str, Any]:
        if state.get("validation_error"):
            raise LLMResponseValidationError(state["validation_error"])
        record = await self.service._blocked_lookup_record(
            action_id=state["action_id"],
            session_id=state["session_id"],
            snapshot=DatabaseSnapshot.model_validate(state["snapshot"]),
            message=state["message"],
            principal=UserPrincipal.model_validate(state["principal"]),
            provider=state["provider"],
            model=state["model"],
            usage=LLMTokenUsage.model_validate(state["usage"]),
            draft=DatabaseActionDraft.model_validate(state["draft"]),
            planning_steps=self._planning_steps(state),
            lookup_resolutions=self._lookup_resolutions(state),
            semantic_sources=self._semantic_sources(state),
            workflow_engine="langgraph",
        )
        return {"record": record.model_dump(mode="json")}

    async def _await_confirmation(
        self,
        state: ActionGraphState,
    ) -> dict[str, Any]:
        checkpoint_record = DatabaseActionRecord.model_validate(
            state["record"]
        )
        response = interrupt(
            {
                "action_id": checkpoint_record.action_id,
                "status": "pending_confirmation",
                "preview_signature": checkpoint_record.preview_signature,
                "matched_row_count": (
                    checkpoint_record.preview.matched_row_count
                ),
                "message": "写操作已暂停，等待数据库操作员确认或取消。",
            }
        )
        if not isinstance(response, dict):
            raise ValueError("Action恢复命令缺少确认信息")
        decision = response.get("decision")
        if decision not in {"confirm", "cancel"}:
            raise ValueError("Action恢复命令必须明确confirm或cancel")
        principal = UserPrincipal.model_validate(response.get("principal"))
        current = await self.service.get(state["action_id"])
        self.service._validate_confirmable(current)
        self.service._validate_preview_integrity(checkpoint_record)
        self.service._validate_preview_integrity(current)
        if (
            self.service._preview_signature(current)
            != self.service._preview_signature(checkpoint_record)
        ):
            raise ValueError("待确认操作与原工作流预览不一致，拒绝继续执行")
        if decision == "cancel":
            current = await self.service._cancel_pending_record(
                current,
                principal,
            )
        return {
            "record": current.model_dump(mode="json"),
            "principal": principal.model_dump(mode="json"),
            "confirmation_decision": decision,
        }

    async def _execute_transaction_and_verify(
        self,
        state: ActionGraphState,
    ) -> dict[str, Any]:
        record = DatabaseActionRecord.model_validate(state["record"])
        executed = await self.service._execute_confirmed_record(
            record,
            UserPrincipal.model_validate(state["principal"]),
        )
        return {"record": executed.model_dump(mode="json")}

    @staticmethod
    def _route_after_plan(
        state: ActionGraphState,
    ) -> Literal["retry", "resolve", "blocked"]:
        if not state.get("validation_error"):
            return "resolve"
        return (
            "retry"
            if state["planning_round"] < state["max_planning_rounds"]
            else "blocked"
        )

    @staticmethod
    def _route_after_lookup(
        state: ActionGraphState,
    ) -> Literal["retry", "preview", "blocked"]:
        unresolved = [
            item
            for item in ActionGraphRunner._lookup_resolutions(state)
            if item.status != "resolved"
        ]
        if not unresolved:
            return "preview"
        return (
            "retry"
            if state["planning_round"] < state["max_planning_rounds"]
            else "blocked"
        )

    @staticmethod
    def _route_after_preview(
        state: ActionGraphState,
    ) -> Literal["wait", "finish"]:
        record = DatabaseActionRecord.model_validate(state["record"])
        return "wait" if record.status == "pending_confirmation" else "finish"

    @staticmethod
    def _route_after_confirmation(
        state: ActionGraphState,
    ) -> Literal["execute", "finish"]:
        return (
            "execute"
            if state["confirmation_decision"] == "confirm"
            else "finish"
        )

    @staticmethod
    def _repair_context(
        state: ActionGraphState,
    ) -> dict[str, object] | None:
        context = state.get("planning_context")
        if (
            isinstance(context, dict)
            and "action_repair" in context
        ):
            value = context["action_repair"]
            return value if isinstance(value, dict) else None
        return None

    @staticmethod
    def _serialize_field_map(
        values: dict[tuple[str, str], str],
    ) -> list[dict[str, str]]:
        return [
            {
                "table_name": key[0],
                "column_name": key[1],
                "value": value,
            }
            for key, value in sorted(values.items())
        ]

    @staticmethod
    def _field_map(
        values: list[dict[str, str]],
    ) -> dict[tuple[str, str], str]:
        return {
            (item["table_name"], item["column_name"]): item["value"]
            for item in values
        }

    @staticmethod
    def _planning_steps(
        state: ActionGraphState,
    ) -> list[ActionPlanningStep]:
        return [
            ActionPlanningStep.model_validate(item)
            for item in state.get("planning_steps", [])
        ]

    @staticmethod
    def _lookup_resolutions(
        state: ActionGraphState,
    ) -> list[ActionLookupResolution]:
        return [
            ActionLookupResolution.model_validate(item)
            for item in state.get("lookup_resolutions", [])
        ]

    @staticmethod
    def _semantic_sources(
        state: ActionGraphState,
    ) -> list[QuerySemanticSource]:
        return [
            QuerySemanticSource.model_validate(item)
            for item in state.get("semantic_sources", [])
        ]
