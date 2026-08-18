from abc import ABC, abstractmethod

from app.models import DatabaseQueryRun


class DatabaseQueryRunRepository(ABC):
    @abstractmethod
    def save(self, run: DatabaseQueryRun) -> None:
        """Persist one immutable natural-language query run."""

    @abstractmethod
    def get(self, query_id: str) -> DatabaseQueryRun:
        """Load one natural-language query run."""
