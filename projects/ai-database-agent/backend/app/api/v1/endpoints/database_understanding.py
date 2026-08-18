from fastapi import APIRouter, BackgroundTasks, status

from app.api.dependencies import (
    CatalogBuildServiceDependency,
    DatabaseUnderstandingServiceDependency,
)
from app.models import CatalogBuildJob, TableUnderstandingRun, WorkflowStatus

router = APIRouter()


@router.post(
    "/snapshots/{snapshot_id}/tables/{table_name}",
    response_model=TableUnderstandingRun,
    summary="运行表级数据库理解Agent",
)
async def understand_table(
    snapshot_id: str,
    table_name: str,
    service: DatabaseUnderstandingServiceDependency,
) -> TableUnderstandingRun:
    return await service.understand_table(snapshot_id, table_name)


@router.get(
    "/runs/{run_id}",
    response_model=TableUnderstandingRun,
    summary="获取数据库理解结果",
)
async def get_understanding_run(
    run_id: str,
    service: DatabaseUnderstandingServiceDependency,
) -> TableUnderstandingRun:
    return await service.get_run(run_id)


@router.get(
    "/runs/{run_id}/workflow",
    response_model=WorkflowStatus,
    summary="获取数据库理解工作流断点状态",
)
async def get_understanding_workflow(
    run_id: str,
    service: DatabaseUnderstandingServiceDependency,
) -> WorkflowStatus:
    return await service.workflow_status(run_id)


@router.post(
    "/runs/{run_id}/resume",
    response_model=TableUnderstandingRun,
    summary="从最后成功节点恢复数据库理解流程",
)
async def resume_understanding_run(
    run_id: str,
    service: DatabaseUnderstandingServiceDependency,
) -> TableUnderstandingRun:
    return await service.resume(run_id)


@router.post(
    "/snapshots/{snapshot_id}/catalog-builds",
    response_model=CatalogBuildJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="启动全库理解与语义目录构建",
)
async def create_catalog_build(
    snapshot_id: str,
    background_tasks: BackgroundTasks,
    service: CatalogBuildServiceDependency,
) -> CatalogBuildJob:
    job = await service.create_job(snapshot_id)
    background_tasks.add_task(service.run_job, job.job_id)
    return job


@router.get(
    "/catalog-builds/{job_id}",
    response_model=CatalogBuildJob,
    summary="获取全库理解任务进度",
)
async def get_catalog_build(
    job_id: str,
    service: CatalogBuildServiceDependency,
) -> CatalogBuildJob:
    return await service.get_job(job_id)
