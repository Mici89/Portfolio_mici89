from fastapi import APIRouter

from app.adapters.database import DatabaseConnectionInfo
from app.api.dependencies import (
    DatabaseConnectionServiceDependency,
    DefaultDatabaseConnectionConfigDependency,
)
from app.schemas.database_connection import (
    DatabaseConnectionProfileResponse,
    DatabaseConnectionRequest,
    DatabaseConnectionResponse,
)

router = APIRouter()


def to_response(
    info: DatabaseConnectionInfo,
    connection_id: str | None = None,
) -> DatabaseConnectionResponse:
    return DatabaseConnectionResponse(
        connection_id=connection_id,
        database_type=info.database_type,
        host=info.host,
        port=info.port,
        database=info.database,
        server_version=info.server_version,
        current_user=info.current_user,
        latency_ms=info.latency_ms,
    )


@router.post(
    "/test",
    response_model=DatabaseConnectionResponse,
    summary="测试指定数据库连接",
)
async def test_database_connection(
    payload: DatabaseConnectionRequest,
    service: DatabaseConnectionServiceDependency,
) -> DatabaseConnectionResponse:
    info = await service.test_connection(payload.to_config())
    return to_response(info)


@router.post(
    "/connect",
    response_model=DatabaseConnectionResponse,
    summary="验证并保存数据库连接",
)
async def connect_database(
    payload: DatabaseConnectionRequest,
    service: DatabaseConnectionServiceDependency,
) -> DatabaseConnectionResponse:
    profile, info = await service.register(
        payload.to_config(),
        label=payload.label,
        write_username=payload.write_username,
        write_password=(
            payload.write_password.get_secret_value()
            if payload.write_password is not None
            else None
        ),
    )
    return to_response(info, profile.connection_id)


@router.get(
    "",
    response_model=list[DatabaseConnectionProfileResponse],
    summary="列出已保存的数据库连接",
)
async def list_database_connections(
    service: DatabaseConnectionServiceDependency,
) -> list[DatabaseConnectionProfileResponse]:
    profiles = await service.list_profiles()
    return [
        DatabaseConnectionProfileResponse(
            connection_id=profile.connection_id,
            label=profile.label,
            database_type=profile.database_type,
            host=profile.host,
            port=profile.port,
            database=profile.database,
            schema_name=profile.schema_name,
            username=profile.username,
            has_separate_write_credential=profile.write_credential_ref is not None,
        )
        for profile in profiles
    ]


@router.get(
    "/default/health",
    response_model=DatabaseConnectionResponse,
    summary="检查默认数据库连接",
)
async def default_database_health(
    config: DefaultDatabaseConnectionConfigDependency,
    service: DatabaseConnectionServiceDependency,
) -> DatabaseConnectionResponse:
    info = await service.test_connection(config)
    return to_response(info)
