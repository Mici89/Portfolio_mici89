from pathlib import Path

from app.core.exceptions import SemanticReviewNotFoundError
from app.models import CatalogReviewRevision
from app.repositories.json_file import JsonModelFileStore
from app.repositories.semantic_review.base import SemanticReviewRepository


class FileSemanticReviewRepository(SemanticReviewRepository):
    def __init__(self, storage_directory: Path) -> None:
        self.current_directory = storage_directory / "current"
        self.history_directory = storage_directory / "history"
        self.current_store = JsonModelFileStore(
            self.current_directory,
            SemanticReviewNotFoundError,
        )
        self.history_store = JsonModelFileStore(
            self.history_directory,
            SemanticReviewNotFoundError,
        )

    def save(self, review: CatalogReviewRevision) -> None:
        self.history_store.save(review.review_id, review)
        current_id = self._current_id(
            review.catalog_entry_id,
            review.source_catalog_version,
        )
        self.current_store.save(current_id, review)

    def latest(
        self,
        catalog_entry_id: str,
        source_catalog_version: int,
    ) -> CatalogReviewRevision | None:
        current_id = self._current_id(catalog_entry_id, source_catalog_version)
        try:
            return self.current_store.get(current_id, CatalogReviewRevision)
        except SemanticReviewNotFoundError:
            return None

    def list_for_entry(self, catalog_entry_id: str) -> list[CatalogReviewRevision]:
        if not self.history_directory.is_dir():
            return []
        reviews = [
            CatalogReviewRevision.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self.history_directory.glob(f"{catalog_entry_id}_v*_r*.json")
            if path.is_file()
        ]
        return sorted(
            reviews,
            key=lambda review: (review.source_catalog_version, review.revision),
        )

    def list_latest(
        self,
        database_name: str | None = None,
    ) -> list[CatalogReviewRevision]:
        if not self.current_directory.is_dir():
            return []
        reviews = [
            CatalogReviewRevision.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self.current_directory.glob("*.json")
            if path.is_file()
        ]
        if database_name is not None:
            reviews = [review for review in reviews if review.database_name == database_name]
        return sorted(
            reviews,
            key=lambda review: (
                review.database_name,
                review.table_name,
                review.source_catalog_version,
            ),
        )

    @staticmethod
    def _current_id(catalog_entry_id: str, source_catalog_version: int) -> str:
        return f"{catalog_entry_id}_v{source_catalog_version}"
