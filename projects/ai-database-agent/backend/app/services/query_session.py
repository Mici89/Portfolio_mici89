from datetime import UTC, datetime
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.core.exceptions import (
    WorkflowResumeRequiredError,
    WorkflowStateError,
)
from app.models import (
    ConversationContextResolution,
    NaturalLanguageQueryRequest,
    PendingQueryTurn,
    QueryResultDigest,
    QuerySession,
    QuerySessionSummary,
    QuerySessionTurn,
    QueryTurnResponse,
)
from app.repositories.database_snapshot import DatabaseSnapshotRepository
from app.repositories.query_session import QuerySessionRepository
from app.services.database_query import DatabaseQueryService


class QuerySessionService:
    def __init__(
        self,
        session_repository: QuerySessionRepository,
        snapshot_repository: DatabaseSnapshotRepository,
        query_service: DatabaseQueryService,
    ) -> None:
        self.session_repository = session_repository
        self.snapshot_repository = snapshot_repository
        self.query_service = query_service

    async def create(self, snapshot_id: str) -> QuerySession:
        snapshot = await run_in_threadpool(
            self.snapshot_repository.get,
            snapshot_id,
        )
        now = datetime.now(UTC)
        session = QuerySession(
            session_id=self._new_id("session"),
            snapshot_id=snapshot_id,
            database_name=snapshot.database.name,
            connection_id=snapshot.source.connection_id,
            title="新分析对话",
            created_at=now,
            updated_at=now,
        )
        await run_in_threadpool(self.session_repository.save, session)
        return session

    async def get(self, session_id: str) -> QuerySession:
        return await run_in_threadpool(self.session_repository.get, session_id)

    async def list(
        self,
        database_name: str | None = None,
        connection_id: str | None = None,
    ) -> list[QuerySessionSummary]:
        sessions = await run_in_threadpool(self.session_repository.list)
        if database_name:
            sessions = [
                session for session in sessions if session.database_name == database_name
            ]
        if connection_id is not None:
            sessions = [
                session for session in sessions if session.connection_id == connection_id
            ]
        ordered = sorted(sessions, key=lambda session: session.updated_at, reverse=True)
        return [
            QuerySessionSummary(
                session_id=session.session_id,
                snapshot_id=session.snapshot_id,
                database_name=session.database_name,
                connection_id=session.connection_id,
                title=session.title,
                created_at=session.created_at,
                updated_at=session.updated_at,
                turn_count=len(session.turns),
            )
            for session in ordered
        ]

    async def add_turn(
        self,
        session_id: str,
        message: str,
        *,
        use_context: bool = True,
        context_resolution: ConversationContextResolution | None = None,
    ) -> QueryTurnResponse:
        session = await self.get(session_id)
        context = (
            self.conversation_context(session, context_resolution)
            if use_context
            else None
        )
        try:
            run = await self.query_service.query(
                session.snapshot_id,
                NaturalLanguageQueryRequest(question=message),
                context,
            )
        except WorkflowResumeRequiredError as exc:
            pending = PendingQueryTurn(
                query_id=exc.workflow_id,
                message=message,
                created_at=datetime.now(UTC),
                context_resolution=context_resolution,
            )
            updated = session.model_copy(
                update={
                    "pending_query": pending,
                    "updated_at": datetime.now(UTC),
                }
            )
            await run_in_threadpool(
                self.session_repository.save,
                updated,
            )
            raise
        return await self._complete_turn(
            session,
            message,
            run,
            context_resolution,
        )

    async def resume_turn(
        self,
        session_id: str,
        query_id: str,
    ) -> QueryTurnResponse:
        session = await self.get(session_id)
        pending = session.pending_query
        if pending is None or pending.query_id != query_id:
            raise WorkflowStateError(
                "该查询断点不属于当前会话，或已经恢复完成。"
            )
        run = await self.query_service.resume(query_id)
        return await self._complete_turn(
            session,
            pending.message,
            run,
            pending.context_resolution,
        )

    async def _complete_turn(
        self,
        session: QuerySession,
        message: str,
        run,
        context_resolution: ConversationContextResolution | None,
    ) -> QueryTurnResponse:
        final_attempt = run.attempts[-1]
        result = final_attempt.result
        turn = QuerySessionTurn(
            turn_id=self._new_id("turn"),
            parent_turn_id=session.active_turn_id,
            query_id=run.query_id,
            created_at=run.created_at,
            user_message=message,
            context_resolution=context_resolution,
            status=run.status,
            intent=final_attempt.plan.intent,
            sql=final_attempt.plan.sql,
            result_digest=QueryResultDigest(
                columns=result.columns,
                row_count=result.returned_row_count,
                sample_rows=result.rows[:5],
                truncated=result.truncated,
            ),
            result_rows=result.rows,
            answer=run.explanation.answer,
            observations=run.explanation.observations,
            limitations=run.explanation.limitations,
            semantic_sources=run.semantic_sources,
            attempts=run.attempts,
        )
        successful = run.status == "completed"
        updated = session.model_copy(
            update={
                "title": (self._title(message) if not session.turns else session.title),
                "updated_at": datetime.now(UTC),
                "active_turn_id": turn.turn_id if successful else session.active_turn_id,
                "current_intent": (turn.intent if successful else session.current_intent),
                "pending_query": None,
                "turns": [*session.turns, turn],
            }
        )
        await run_in_threadpool(self.session_repository.save, updated)
        return QueryTurnResponse(session=updated, turn=turn, run=run)

    @staticmethod
    def conversation_context(
        session: QuerySession,
        resolution: ConversationContextResolution | None = None,
    ) -> dict[str, object] | None:
        successful_turns = [turn for turn in session.turns if turn.status == "completed"]
        if not successful_turns and resolution is None:
            return None
        return {
            "active_turn_id": session.active_turn_id,
            "active_intent": (
                session.current_intent.model_dump(mode="json")
                if session.current_intent is not None
                else None
            ),
            "recent_turns": [
                {
                    "turn_id": turn.turn_id,
                    "user_message": turn.user_message,
                    "intent": turn.intent.model_dump(mode="json"),
                    "sql": turn.sql,
                    "answer": turn.answer,
                    "result_digest": turn.result_digest.model_dump(mode="json"),
                    "result_rows": turn.result_rows,
                    "observations": turn.observations,
                    "limitations": turn.limitations,
                }
                for turn in successful_turns
            ],
            "context_resolution": (
                resolution.model_dump(mode="json")
                if resolution is not None
                else None
            ),
            "instruction": (
                "这是完整历史上下文。请由大模型自行判断当前问题是延续、修正还是切换主题；"
                "不得依赖代码生成的inherited/required槽位。历史result_rows是真实数据库结果。"
            ),
        }

    @staticmethod
    def _title(message: str) -> str:
        compact = " ".join(message.split())
        return compact[:32] + ("…" if len(compact) > 32 else "")

    @staticmethod
    def _new_id(prefix: str) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return f"{prefix}_{timestamp}_{uuid4().hex[:8]}"
