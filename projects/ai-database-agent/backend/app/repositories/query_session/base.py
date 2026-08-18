from abc import ABC, abstractmethod

from app.models import QuerySession


class QuerySessionRepository(ABC):
    @abstractmethod
    def save(self, session: QuerySession) -> None:
        """Persist the current state of one query conversation."""

    @abstractmethod
    def get(self, session_id: str) -> QuerySession:
        """Load one query conversation."""

    @abstractmethod
    def list(self) -> list[QuerySession]:
        """List persisted query conversations."""
