from pathlib import Path

from app.core.exceptions import SemanticCatalogEntryNotFoundError
from app.models import SemanticCatalogEntry
from app.repositories.json_file import JsonModelFileStore
from app.repositories.semantic_catalog.base import SemanticCatalogRepository


class FileSemanticCatalogRepository(SemanticCatalogRepository):
    def __init__(self, storage_directory: Path) -> None:
        self.current_directory = storage_directory / "current"
        self.history_directory = storage_directory / "history"
        self.current_store = JsonModelFileStore(
            self.current_directory,
            SemanticCatalogEntryNotFoundError,
        )
        self.history_store = JsonModelFileStore(
            self.history_directory,
            SemanticCatalogEntryNotFoundError,
        )

    def save(self, entry: SemanticCatalogEntry) -> None:
        history_id = f"{entry.catalog_entry_id}_v{entry.version}"
        self.history_store.save(history_id, entry)
        self.current_store.save(entry.catalog_entry_id, entry)

    def find(self, catalog_entry_id: str) -> SemanticCatalogEntry | None:
        try:
            return self.current_store.get(catalog_entry_id, SemanticCatalogEntry)
        except SemanticCatalogEntryNotFoundError:
            return None

    def get(self, catalog_entry_id: str) -> SemanticCatalogEntry:
        return self.current_store.get(catalog_entry_id, SemanticCatalogEntry)

    def list(self, database_name: str | None = None) -> list[SemanticCatalogEntry]:
        if not self.current_directory.is_dir():
            return []
        entries = [
            SemanticCatalogEntry.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self.current_directory.glob("*.json")
            if path.is_file()
        ]
        if database_name is not None:
            entries = [entry for entry in entries if entry.database_name == database_name]
        return sorted(entries, key=lambda entry: (entry.database_name, entry.table_name))
