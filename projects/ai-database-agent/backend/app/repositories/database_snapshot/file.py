from pathlib import Path

from app.core.exceptions import DatabaseSnapshotNotFoundError
from app.models import DatabaseSnapshot
from app.repositories.database_snapshot.base import DatabaseSnapshotRepository
from app.repositories.json_file import JsonModelFileStore


class FileDatabaseSnapshotRepository(DatabaseSnapshotRepository):
    def __init__(self, storage_directory: Path) -> None:
        self.store = JsonModelFileStore(
            storage_directory,
            DatabaseSnapshotNotFoundError,
        )

    def save(self, snapshot: DatabaseSnapshot) -> None:
        self.store.save(snapshot.snapshot_id, snapshot)

    def get(self, snapshot_id: str) -> DatabaseSnapshot:
        return self.store.get(snapshot_id, DatabaseSnapshot)
