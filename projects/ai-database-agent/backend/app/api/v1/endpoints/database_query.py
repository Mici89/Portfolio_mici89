from fastapi import APIRouter, Query

from app.api.dependencies import (
    ConversationServiceDependency,
    CurrentUserDependency,
    DatabaseQueryServiceDependency,
    QuerySessionServiceDependency,
)
from app.models import (
    ConversationMessageCreate,
    ConversationMessageResponse,
    DatabaseQueryRun,
    NaturalLanguageQueryRequest,
    QuerySession,
    QuerySessionCreate,
    QuerySessionSummary,
    QueryTurnCreate,
    QueryTurnResponse,
    WorkflowStatus,
)

router = APIRouter()


@router.post(
    "/sessions",
    response_model=QuerySession,
    summary="创建自然语言查询对话",
)
async def create_query_session(
    request: QuerySessionCreate,
    service: QuerySessionServiceDependency,
) -> QuerySession:
    return await service.create(request.snapshot_id)


@router.get(
    "/sessions",
    response_model=list[QuerySessionSummary],
    summary="列出已保存的自然语言查询对话",
)
async def list_query_sessions(
    service: QuerySessionServiceDependency,
    database_name: str | None = Query(default=None),
    connection_id: str | None = Query(default=None),
) -> list[QuerySessionSummary]:
    return await service.list(database_name, connection_id or None)


@router.get(
    "/sessions/{session_id}",
    response_model=QuerySession,
    summary="读取查询对话及结构化上下文",
)
async def get_query_session(
    session_id: str,
    service: QuerySessionServiceDependency,
) -> QuerySession:
    return await service.get(session_id)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ConversationMessageResponse,
    summary="发送查询或数据库修改消息并自动路由",
)
async def create_conversation_message(
    session_id: str,
    request: ConversationMessageCreate,
    service: ConversationServiceDependency,
    principal: CurrentUserDependency,
) -> ConversationMessageResponse:
    return await service.send(session_id, request.message, principal)


@router.post(
    "/sessions/{session_id}/turns",
    response_model=QueryTurnResponse,
    summary="在查询对话中提交一轮追问",
)
async def create_query_turn(
    session_id: str,
    request: QueryTurnCreate,
    service: QuerySessionServiceDependency,
) -> QueryTurnResponse:
    return await service.add_turn(session_id, request.message)


@router.post(
    "/sessions/{session_id}/runs/{query_id}/resume",
    response_model=QueryTurnResponse,
    summary="恢复会话中断的查询并保存为原会话的一轮",
)
async def resume_query_turn(
    session_id: str,
    query_id: str,
    service: QuerySessionServiceDependency,
) -> QueryTurnResponse:
    return await service.resume_turn(session_id, query_id)


@router.post(
    "/snapshots/{snapshot_id}",
    response_model=DatabaseQueryRun,
    summary="使用有效语义运行自然语言查询Agent",
)
async def query_database(
    snapshot_id: str,
    request: NaturalLanguageQueryRequest,
    service: DatabaseQueryServiceDependency,
) -> DatabaseQueryRun:
    return await service.query(snapshot_id, request)


@router.get(
    "/runs/{query_id}",
    response_model=DatabaseQueryRun,
    summary="读取自然语言查询运行记录",
)
async def get_database_query(
    query_id: str,
    service: DatabaseQueryServiceDependency,
) -> DatabaseQueryRun:
    return await service.get_run(query_id)


@router.get(
    "/runs/{query_id}/workflow",
    response_model=WorkflowStatus,
    summary="获取查询工作流断点状态",
)
async def get_database_query_workflow(
    query_id: str,
    service: DatabaseQueryServiceDependency,
) -> WorkflowStatus:
    return await service.workflow_status(query_id)


@router.post(
    "/runs/{query_id}/resume",
    response_model=DatabaseQueryRun,
    summary="从最后成功节点恢复数据库查询流程",
)
async def resume_database_query(
    query_id: str,
    service: DatabaseQueryServiceDependency,
) -> DatabaseQueryRun:
    return await service.resume(query_id)
