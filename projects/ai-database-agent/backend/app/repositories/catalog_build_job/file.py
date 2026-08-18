from pathlib import Path

from app.core.exceptions import CatalogBuildJobNotFoundError
from app.models import CatalogBuildJob
from app.repositories.catalog_build_job.base import CatalogBuildJobRepository
from app.repositories.json_file import JsonModelFileStore


class FileCatalogBuildJobRepository(CatalogBuildJobRepository):
    def __init__(self, storage_directory: Path) -> None:
        self.store = JsonModelFileStore(
            storage_directory,
            CatalogBuildJobNotFoundError,
        )

    def save(self, job: CatalogBuildJob) -> None:
        self.store.save(job.job_id, job)

    def get(self, job_id: str) -> CatalogBuildJob:
        return self.store.get(job_id, CatalogBuildJob)
