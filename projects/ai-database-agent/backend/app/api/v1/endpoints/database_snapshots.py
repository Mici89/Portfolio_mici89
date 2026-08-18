from fastapi import APIRouter, status

from app.api.dependencies import (
    DatabaseConnectionServiceDependency,
    DatabaseSnapshotServiceDependency,
)
from app.models import DatabaseSnapshot
from app.schemas.database_connection import DatabaseConnectionRequest

router = APIRouter()


@router.post(
    "/default/scan",
    response_model=DatabaseSnapshot,
    status_code=status.HTTP_201_CREATED,
    summary="扫描默认数据库并创建结构快照",
)
async def scan_default_database(
    connection_service: DatabaseConnectionServiceDependency,
    service: DatabaseSnapshotServiceDependency,
) -> DatabaseSnapshot:
    profile, _ = await connection_service.register_default()
    config = await connection_service.resolve(profile.connection_id)
    return await service.create_snapshot(config)


@router.post(
    "/scan",
    response_model=DatabaseSnapshot,
    status_code=status.HTTP_201_CREATED,
    summary="使用指定连接扫描数据库结构",
)
async def scan_database(
    payload: DatabaseConnectionRequest,
    connection_service: DatabaseConnectionServiceDependency,
    service: DatabaseSnapshotServiceDependency,
) -> DatabaseSnapshot:
    profile, _ = await connection_service.register(
        payload.to_config(),
        label=payload.label,
        write_username=payload.write_username,
        write_password=(
            payload.write_password.get_secret_value()
            if payload.write_password is not None
            else None
        ),
    )
    config = await connection_service.resolve(profile.connection_id)
    return await service.create_snapshot(config)


@router.post(
    "/connections/{connection_id}/scan",
    response_model=DatabaseSnapshot,
    status_code=status.HTTP_201_CREATED,
    summary="使用已保存连接扫描数据库结构",
)
async def scan_saved_connection(
    connection_id: str,
    connection_service: DatabaseConnectionServiceDependency,
    service: DatabaseSnapshotServiceDependency,
) -> DatabaseSnapshot:
    config = await connection_service.resolve(connection_id)
    return await service.create_snapshot(config)


@router.get(
    "/{snapshot_id}",
    response_model=DatabaseSnapshot,
    summary="获取数据库结构快照",
)
async def get_database_snapshot(
    snapshot_id: str,
    service: DatabaseSnapshotServiceDependency,
) -> DatabaseSnapshot:
    return await service.get_snapshot(snapshot_id)
