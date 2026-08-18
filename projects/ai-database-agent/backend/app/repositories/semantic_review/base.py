from abc import ABC, abstractmethod

from app.models import CatalogReviewRevision


class SemanticReviewRepository(ABC):
    @abstractmethod
    def save(self, review: CatalogReviewRevision) -> None:
        """Persist an immutable review revision and update its current pointer."""

    @abstractmethod
    def latest(
        self,
        catalog_entry_id: str,
        source_catalog_version: int,
    ) -> CatalogReviewRevision | None:
        """Return the latest review for one generated catalog version."""

    @abstractmethod
    def list_for_entry(self, catalog_entry_id: str) -> list[CatalogReviewRevision]:
        """List all immutable review revisions for one catalog entry."""

    @abstractmethod
    def list_latest(
        self,
        database_name: str | None = None,
    ) -> list[CatalogReviewRevision]:
        """List latest review pointers, optionally filtered by database."""
