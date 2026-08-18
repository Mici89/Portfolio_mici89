from abc import ABC, abstractmethod

from app.models import DatabaseSnapshot


class DatabaseSnapshotRepository(ABC):
    @abstractmethod
    def save(self, snapshot: DatabaseSnapshot) -> None:
        """Persist a complete, validated database snapshot."""

    @abstractmethod
    def get(self, snapshot_id: str) -> DatabaseSnapshot:
        """Load a database snapshot or raise DatabaseSnapshotNotFoundError."""
