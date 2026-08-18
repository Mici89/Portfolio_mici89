from pathlib import Path

from app.core.exceptions import DatabaseConnectionProfileNotFoundError
from app.models import DatabaseConnectionProfile
from app.repositories.database_connection.base import DatabaseConnectionProfileRepository
from app.repositories.json_file import JsonModelFileStore


class FileDatabaseConnectionProfileRepository(DatabaseConnectionProfileRepository):
    def __init__(self, storage_directory: Path) -> None:
        self.store = JsonModelFileStore(
            storage_directory,
            DatabaseConnectionProfileNotFoundError,
        )

    def save(self, profile: DatabaseConnectionProfile) -> None:
        self.store.save(profile.connection_id, profile)

    def get(self, connection_id: str) -> DatabaseConnectionProfile:
        return self.store.get(connection_id, DatabaseConnectionProfile)

    def list(self) -> list[DatabaseConnectionProfile]:
        return self.store.list(DatabaseConnectionProfile)
