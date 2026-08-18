import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.main import app
from app.services.auth import AuthService


def make_service() -> AuthService:
    return AuthService(
        operator_username="db_operator",
        operator_password="correct-password",
        token_secret="test-signing-secret",
        token_ttl_minutes=30,
    )


def test_anonymous_user_is_read_only() -> None:
    service = make_service()
    principal = service.authenticate(None)

    assert principal.role == "viewer"
    assert principal.permissions == ["database:query"]
    with pytest.raises(AuthorizationError):
        service.require_operator(principal)


def test_operator_login_issues_verifiable_token() -> None:
    service = make_service()
    login, token = service.login("db_operator", "correct-password")

    principal = service.authenticate(token)

    assert principal.authenticated is True
    assert principal.role == "database_operator"
    assert "database_action:execute" in principal.permissions


def test_invalid_password_and_tampered_token_are_rejected() -> None:
    service = make_service()
    with pytest.raises(AuthenticationError):
        service.login("db_operator", "wrong-password")

    _, token = service.login("db_operator", "correct-password")
    with pytest.raises(AuthenticationError):
        service.authenticate(token + "tampered")


def test_login_cookie_persists_identity_until_logout() -> None:
    app.dependency_overrides[get_auth_service] = make_service
    try:
        with TestClient(app, base_url="http://localhost") as client:
            login = client.post(
                "/api/v1/auth/login",
                json={
                    "username": "db_operator",
                    "password": "correct-password",
                },
            )
            current = client.get("/api/v1/auth/me")
            logout = client.post("/api/v1/auth/logout")
            after_logout = client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert login.status_code == 200
    assert "HttpOnly" in login.headers["set-cookie"]
    assert current.json()["role"] == "database_operator"
    assert logout.json()["role"] == "viewer"
    assert after_logout.json()["authenticated"] is False
