from pathlib import Path

import pytest

from app.adapters.database import DatabaseConnectionConfig
from app.adapters.database.base import DatabaseConnectionInfo
from app.repositories.database_connection import FileDatabaseConnectionProfileRepository
from app.repositories.database_connection.credentials import EncryptedFileCredentialStore
from app.services.database_connection import DatabaseConnectionService


class FakeFactory:
    def create(self, config):
        return FakeAdapter(config)


class FakeAdapter:
    def __init__(self, config):
        self.config = config

    def test_connection(self):
        return DatabaseConnectionInfo(
            database_type=self.config.database_type,
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            server_version="test",
            current_user=self.config.username,
            latency_ms=1,
        )


@pytest.mark.asyncio
async def test_profile_keeps_credentials_out_of_snapshot_and_profile_json(
    tmp_path: Path,
) -> None:
    profiles = FileDatabaseConnectionProfileRepository(tmp_path / "profiles")
    credentials = EncryptedFileCredentialStore(tmp_path / "credentials", "encryption-key")
    default = DatabaseConnectionConfig(
        database_type="postgresql",
        host="db-a",
        port=5432,
        database="enterprise",
        username="reader",
        password="plain-secret",
        schema_name="public",
    )
    service = DatabaseConnectionService(
        FakeFactory(),  # type: ignore[arg-type]
        profiles,
        credentials,
        default,
    )

    profile, _ = await service.register(default, label="企业库")
    resolved = await service.resolve(profile.connection_id)

    assert resolved.connection_id == profile.connection_id
    assert resolved.password == "plain-secret"
    profile_text = (tmp_path / "profiles" / f"{profile.connection_id}.json").read_text()
    credential_bytes = next((tmp_path / "credentials").glob("*.bin")).read_bytes()
    assert "plain-secret" not in profile_text
    assert b"plain-secret" not in credential_bytes
