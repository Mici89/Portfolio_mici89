from datetime import UTC, datetime
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.adapters.database import (
    DatabaseAdapterFactory,
    DatabaseConnectionConfig,
    DatabaseConnectionInfo,
)
from app.core.exceptions import SnapshotConnectionMismatchError
from app.models import DatabaseConnectionProfile, DatabaseSnapshot
from app.repositories.database_connection import DatabaseConnectionProfileRepository
from app.repositories.database_connection.credentials import EncryptedFileCredentialStore


class DatabaseConnectionService:
    def __init__(
        self,
        adapter_factory: DatabaseAdapterFactory | None = None,
        profile_repository: DatabaseConnectionProfileRepository | None = None,
        credential_store: EncryptedFileCredentialStore | None = None,
        default_config: DatabaseConnectionConfig | None = None,
        default_write_config: DatabaseConnectionConfig | None = None,
    ) -> None:
        self.adapter_factory = adapter_factory or DatabaseAdapterFactory()
        self.profile_repository = profile_repository
        self.credential_store = credential_store
        self.default_config = default_config
        self.default_write_config = default_write_config

    async def test_connection(
        self,
        config: DatabaseConnectionConfig,
    ) -> DatabaseConnectionInfo:
        adapter = self.adapter_factory.create(config)
        return await run_in_threadpool(adapter.test_connection)

    async def register(
        self,
        config: DatabaseConnectionConfig,
        *,
        label: str = "",
        write_username: str | None = None,
        write_password: str | None = None,
    ) -> tuple[DatabaseConnectionProfile, DatabaseConnectionInfo]:
        self._require_profile_storage()
        info = await self.test_connection(config)
        if write_username and write_password:
            await self.test_connection(
                DatabaseConnectionConfig(
                    database_type=config.database_type,
                    host=config.host,
                    port=config.port,
                    database=config.database,
                    username=write_username,
                    password=write_password,
                    schema_name=config.schema_name,
                    options=config.options,
                    connect_timeout_seconds=config.connect_timeout_seconds,
                )
            )
        connection_id = self._new_id("conn")
        credential_ref = self._new_id("cred")
        write_credential_ref = self._new_id("cred") if write_password else None
        assert self.credential_store is not None
        assert self.profile_repository is not None
        await run_in_threadpool(self.credential_store.save, credential_ref, config.password)
        if write_credential_ref and write_password:
            await run_in_threadpool(
                self.credential_store.save,
                write_credential_ref,
                write_password,
            )
        now = datetime.now(UTC)
        profile = DatabaseConnectionProfile(
            connection_id=connection_id,
            label=label or f"{info.database_type}:{info.database}",
            database_type=config.database_type,
            host=config.host,
            port=config.port,
            database=config.database,
            schema_name=config.schema_name,
            username=config.username,
            credential_ref=credential_ref,
            write_username=write_username,
            write_credential_ref=write_credential_ref,
            options=dict(config.options or {}),
            created_at=now,
            updated_at=now,
        )
        await run_in_threadpool(self.profile_repository.save, profile)
        return profile, info

    async def get_profile(self, connection_id: str) -> DatabaseConnectionProfile:
        self._require_profile_storage()
        assert self.profile_repository is not None
        return await run_in_threadpool(self.profile_repository.get, connection_id)

    async def list_profiles(self) -> list[DatabaseConnectionProfile]:
        self._require_profile_storage()
        assert self.profile_repository is not None
        return await run_in_threadpool(self.profile_repository.list)

    async def resolve(
        self,
        connection_id: str,
        *,
        write: bool = False,
    ) -> DatabaseConnectionConfig:
        profile = await self.get_profile(connection_id)
        assert self.credential_store is not None
        use_write = write and profile.write_credential_ref is not None
        credential_ref = (
            profile.write_credential_ref if use_write else profile.credential_ref
        )
        assert credential_ref is not None
        password = await run_in_threadpool(self.credential_store.get, credential_ref)
        return DatabaseConnectionConfig(
            connection_id=profile.connection_id,
            database_type=profile.database_type,
            host=profile.host,
            port=profile.port,
            database=profile.database,
            username=(
                profile.write_username
                if use_write and profile.write_username
                else profile.username
            ),
            password=password,
            schema_name=profile.schema_name,
            options=profile.options,
            connect_timeout_seconds=(
                self.default_config.connect_timeout_seconds if self.default_config else 5
            ),
        )

    async def resolve_snapshot(
        self,
        snapshot: DatabaseSnapshot,
        *,
        write: bool = False,
    ) -> DatabaseConnectionConfig:
        if snapshot.source.connection_id:
            return await self.resolve(snapshot.source.connection_id, write=write)
        if self.default_config and self._matches_default(snapshot):
            return self.default_config
        raise SnapshotConnectionMismatchError()

    async def register_default(self) -> tuple[DatabaseConnectionProfile, DatabaseConnectionInfo]:
        if self.default_config is None:
            raise RuntimeError("Default database connection is not configured")
        return await self.register(
            self.default_config,
            label=f"默认连接 · {self.default_config.database}",
            write_username=(
                self.default_write_config.username
                if self.default_write_config is not None
                else None
            ),
            write_password=(
                self.default_write_config.password
                if self.default_write_config is not None
                else None
            ),
        )

    def _matches_default(self, snapshot: DatabaseSnapshot) -> bool:
        assert self.default_config is not None
        return (
            snapshot.source.database_type == self.default_config.database_type
            and snapshot.source.host == self.default_config.host
            and snapshot.source.port == self.default_config.port
            and snapshot.source.database == self.default_config.database
        )

    def _require_profile_storage(self) -> None:
        if self.profile_repository is None or self.credential_store is None:
            raise RuntimeError("Database connection profile storage is not configured")

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"
