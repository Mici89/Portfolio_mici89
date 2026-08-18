from abc import ABC, abstractmethod

from app.models import SemanticCatalogEntry


class SemanticCatalogRepository(ABC):
    @abstractmethod
    def save(self, entry: SemanticCatalogEntry) -> None:
        """Persist the current entry and one immutable history version."""

    @abstractmethod
    def find(self, catalog_entry_id: str) -> SemanticCatalogEntry | None:
        """Return the current entry when it exists."""

    @abstractmethod
    def get(self, catalog_entry_id: str) -> SemanticCatalogEntry:
        """Return the current entry or raise a not-found error."""

    @abstractmethod
    def list(self, database_name: str | None = None) -> list[SemanticCatalogEntry]:
        """List current catalog entries, optionally filtered by database."""
