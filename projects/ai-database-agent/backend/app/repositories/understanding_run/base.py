from abc import ABC, abstractmethod

from app.models import TableUnderstandingRun


class UnderstandingRunRepository(ABC):
    @abstractmethod
    def save(self, run: TableUnderstandingRun) -> None:
        """Persist a validated table-understanding run."""

    @abstractmethod
    def get(self, run_id: str) -> TableUnderstandingRun:
        """Load one table-understanding run."""
