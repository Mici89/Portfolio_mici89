from abc import ABC, abstractmethod

from app.models import CatalogBuildJob


class CatalogBuildJobRepository(ABC):
    @abstractmethod
    def save(self, job: CatalogBuildJob) -> None:
        """Persist the latest build-job state."""

    @abstractmethod
    def get(self, job_id: str) -> CatalogBuildJob:
        """Return a build job or raise a not-found error."""
