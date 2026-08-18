from pathlib import Path

from app.core.exceptions import DatabaseActionNotFoundError
from app.models import DatabaseActionRecord
from app.repositories.database_action.base import DatabaseActionRepository
from app.repositories.json_file import JsonModelFileStore


class FileDatabaseActionRepository(DatabaseActionRepository):
    def __init__(self, storage_directory: Path) -> None:
        self.store = JsonModelFileStore(
            storage_directory,
            DatabaseActionNotFoundError,
        )

    def save(self, record: DatabaseActionRecord) -> None:
        self.store.save(record.action_id, record)

    def get(self, action_id: str) -> DatabaseActionRecord:
        return self.store.get(action_id, DatabaseActionRecord)

    def list_for_session(self, session_id: str) -> list[DatabaseActionRecord]:
        return [
            record
            for record in self.store.list(DatabaseActionRecord)
            if record.session_id == session_id
        ]
