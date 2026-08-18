from pathlib import Path

from app.core.exceptions import DatabaseQueryRunNotFoundError
from app.models import DatabaseQueryRun
from app.repositories.database_query.base import DatabaseQueryRunRepository
from app.repositories.json_file import JsonModelFileStore


class FileDatabaseQueryRunRepository(DatabaseQueryRunRepository):
    def __init__(self, storage_directory: Path) -> None:
        self.store = JsonModelFileStore(
            storage_directory,
            DatabaseQueryRunNotFoundError,
        )

    def save(self, run: DatabaseQueryRun) -> None:
        self.store.save(run.query_id, run)

    def get(self, query_id: str) -> DatabaseQueryRun:
        return self.store.get(query_id, DatabaseQueryRun)
