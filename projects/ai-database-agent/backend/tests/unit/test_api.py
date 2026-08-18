from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient

from app.adapters.database import DatabaseConnectionInfo
from app.api.dependencies import get_database_connection_service
from app.core.exceptions import DatabaseConnectionError
from app.main import app
from app.services.database_connection import DatabaseConnectionService


class SuccessfulConnectionService(DatabaseConnectionService):
    async def test_connection(self, _config: Any) -> DatabaseConnectionInfo:
        return DatabaseConnectionInfo(
            database_type="mysql",
            host="127.0.0.1",
            port=3307,
            database="legacy_enterprise",
            server_version="8.4.10",
            current_user="ai_reader@%",
            latency_ms=1.25,
        )


class FailedAuthenticationService(DatabaseConnectionService):
    async def test_connection(self, _config: Any) -> DatabaseConnectionInfo:
        raise DatabaseConnectionError(
            "authentication_failed",
            "数据库身份验证失败，请检查用户名和密码",
            http_status_code=401,
        )


@contextmanager
def overridden_client(service: DatabaseConnectionService) -> Iterator[TestClient]:
    app.dependency_overrides[get_database_connection_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_liveness() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "AI Database Agent API",
        "version": "0.1.0",
    }


def test_connection_request_does_not_return_password() -> None:
    with overridden_client(SuccessfulConnectionService()) as client:
        response = client.post(
            "/api/v1/database-connections/test",
            json={
                "database_type": "mysql",
                "host": "127.0.0.1",
                "port": 3307,
                "database": "legacy_enterprise",
                "username": "ai_reader",
                "password": "local_reader_ChangeMe_2026",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    assert "password" not in response.text
    assert "local_reader_ChangeMe_2026" not in response.text


def test_authentication_error_is_sanitized() -> None:
    with overridden_client(FailedAuthenticationService()) as client:
        response = client.post(
            "/api/v1/database-connections/test",
            json={
                "database_type": "mysql",
                "host": "127.0.0.1",
                "port": 3307,
                "database": "legacy_enterprise",
                "username": "ai_reader",
                "password": "wrong-password",
            },
        )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "authentication_failed",
            "message": "数据库身份验证失败，请检查用户名和密码",
        }
    }
    assert "wrong-password" not in response.text
