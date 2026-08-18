from pathlib import Path

from app.core.exceptions import UnderstandingRunNotFoundError
from app.models import TableUnderstandingRun
from app.repositories.json_file import JsonModelFileStore
from app.repositories.understanding_run.base import UnderstandingRunRepository


class FileUnderstandingRunRepository(UnderstandingRunRepository):
    def __init__(self, storage_directory: Path) -> None:
        self.store = JsonModelFileStore(
            storage_directory,
            UnderstandingRunNotFoundError,
        )

    def save(self, run: TableUnderstandingRun) -> None:
        self.store.save(run.run_id, run)

    def get(self, run_id: str) -> TableUnderstandingRun:
        return self.store.get(run_id, TableUnderstandingRun)
