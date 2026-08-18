import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_database_snapshot_repository
from app.main import app
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository


@pytest.mark.integration
def test_default_mysql_connection() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/database-connections/default/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "connected"
    assert body["database_type"] == "mysql"
    assert body["database"] == "legacy_enterprise"
    assert body["current_user"] == "ai_reader@%"
    assert body["latency_ms"] >= 0


@pytest.mark.integration
def test_scan_and_reload_mysql_schema_snapshot(tmp_path) -> None:
    repository = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    app.dependency_overrides[get_database_snapshot_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            scan_response = client.post("/api/v1/database-snapshots/default/scan")

            assert scan_response.status_code == 201
            snapshot = scan_response.json()
            snapshot_id = snapshot["snapshot_id"]
            assert snapshot["scan_statistics"]["table_count"] == 28
            assert snapshot["scan_statistics"]["view_count"] == 0
            assert snapshot["scan_statistics"]["column_count"] == 256
            assert snapshot["scan_statistics"]["foreign_key_count"] == 27
            assert snapshot["scan_statistics"]["index_count"] > 27
            assert snapshot["database"]["name"] == "legacy_enterprise"
            assert snapshot["source"]["database_type"] == "mysql"
            assert snapshot["source"]["host"] == "127.0.0.1"
            assert snapshot["source"]["port"] == 3307
            assert snapshot["source"]["database"] == "legacy_enterprise"
            assert snapshot["source"]["schema_name"] == "legacy_enterprise"
            assert snapshot["source"]["connection_id"].startswith("conn_")
            assert "local_reader_ChangeMe_2026" not in scan_response.text

            tables = {table["name"]: table for table in snapshot["tables"]}
            assert tables["org_employee"]["comment"] == "员工主数据"
            assert tables["org_employee"]["primary_key"] == ["employee_id"]
            assert len(tables["org_employee"]["columns"]) == 14
            assert tables["t_a01"]["comment"] == ""
            assert all(column["comment"] == "" for column in tables["t_a01"]["columns"])

            get_response = client.get(f"/api/v1/database-snapshots/{snapshot_id}")
            assert get_response.status_code == 200
            assert get_response.json() == snapshot
    finally:
        app.dependency_overrides.clear()


def test_missing_snapshot_returns_structured_error(tmp_path) -> None:
    repository = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    app.dependency_overrides[get_database_snapshot_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/database-snapshots/snap_missing")

        assert response.status_code == 404
        assert response.json() == {
            "error": {
                "code": "database_snapshot_not_found",
                "message": "数据库快照不存在：snap_missing",
            }
        }
    finally:
        app.dependency_overrides.clear()
