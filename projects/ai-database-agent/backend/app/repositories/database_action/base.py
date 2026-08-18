from abc import ABC, abstractmethod

from app.models import DatabaseActionRecord


class DatabaseActionRepository(ABC):
    @abstractmethod
    def save(self, record: DatabaseActionRecord) -> None:
        """Persist the latest state of one database action."""

    @abstractmethod
    def get(self, action_id: str) -> DatabaseActionRecord:
        """Load one database action audit record."""

    @abstractmethod
    def list_for_session(self, session_id: str) -> list[DatabaseActionRecord]:
        """List database actions that belong to one conversation."""
