from fastapi import APIRouter, Query

from app.api.dependencies import (
    DatabaseActionServiceDependency,
    DatabaseOperatorDependency,
)
from app.models import DatabaseActionRecord, WorkflowStatus

router = APIRouter()


@router.get(
    "",
    response_model=list[DatabaseActionRecord],
    summary="列出一个对话中的数据库写操作记录",
)
async def list_database_actions(
    service: DatabaseActionServiceDependency,
    _: DatabaseOperatorDependency,
    session_id: str = Query(min_length=1, max_length=100),
) -> list[DatabaseActionRecord]:
    return await service.list_for_session(session_id)


@router.get(
    "/{action_id}",
    response_model=DatabaseActionRecord,
    summary="读取数据库写操作计划及审计记录",
)
async def get_database_action(
    action_id: str,
    service: DatabaseActionServiceDependency,
    _: DatabaseOperatorDependency,
) -> DatabaseActionRecord:
    return await service.get(action_id)


@router.get(
    "/{action_id}/workflow",
    response_model=WorkflowStatus,
    summary="读取数据库写操作工作流状态",
)
async def get_database_action_workflow(
    action_id: str,
    service: DatabaseActionServiceDependency,
    _: DatabaseOperatorDependency,
) -> WorkflowStatus:
    return await service.workflow_status(action_id)


@router.post(
    "/{action_id}/confirm",
    response_model=DatabaseActionRecord,
    summary="确认并在事务内执行数据库写操作",
)
async def confirm_database_action(
    action_id: str,
    service: DatabaseActionServiceDependency,
    principal: DatabaseOperatorDependency,
) -> DatabaseActionRecord:
    return await service.confirm(action_id, principal)


@router.post(
    "/{action_id}/cancel",
    response_model=DatabaseActionRecord,
    summary="取消待确认的数据库写操作",
)
async def cancel_database_action(
    action_id: str,
    service: DatabaseActionServiceDependency,
    principal: DatabaseOperatorDependency,
) -> DatabaseActionRecord:
    return await service.cancel(action_id, principal)
