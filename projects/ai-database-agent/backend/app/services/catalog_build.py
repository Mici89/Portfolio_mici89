from datetime import UTC, datetime
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.core.exceptions import WorkflowResumeRequiredError
from app.models import CatalogBuildItem, CatalogBuildJob
from app.repositories.catalog_build_job import CatalogBuildJobRepository
from app.repositories.database_snapshot import DatabaseSnapshotRepository
from app.services.database_understanding import DatabaseUnderstandingService
from app.services.semantic_catalog import SemanticCatalogService


class CatalogBuildService:
    def __init__(
        self,
        job_repository: CatalogBuildJobRepository,
        snapshot_repository: DatabaseSnapshotRepository,
        understanding_service: DatabaseUnderstandingService,
        catalog_service: SemanticCatalogService,
    ) -> None:
        self.job_repository = job_repository
        self.snapshot_repository = snapshot_repository
        self.understanding_service = understanding_service
        self.catalog_service = catalog_service

    async def create_job(self, snapshot_id: str) -> CatalogBuildJob:
        snapshot = await run_in_threadpool(
            self.snapshot_repository.get,
            snapshot_id,
        )
        now = datetime.now(UTC)
        items = [
            CatalogBuildItem(table_name=table.name, status="pending") for table in snapshot.tables
        ]
        job = CatalogBuildJob(
            job_id=self._new_job_id(),
            snapshot_id=snapshot_id,
            database_name=snapshot.database.name,
            status="queued",
            created_at=now,
            updated_at=now,
            total_tables=len(items),
            processed_tables=0,
            completed_tables=0,
            skipped_tables=0,
            failed_tables=0,
            items=items,
        )
        await run_in_threadpool(self.job_repository.save, job)
        return job

    async def run_job(self, job_id: str) -> None:
        job = await run_in_threadpool(self.job_repository.get, job_id)
        snapshot = await run_in_threadpool(
            self.snapshot_repository.get,
            job.snapshot_id,
        )
        tables_by_name = {table.name: table for table in snapshot.tables}
        items = list(job.items)
        job = await self._persist(
            job,
            items,
            status="running",
            current_table=None,
        )

        for index, item in enumerate(items):
            table = tables_by_name[item.table_name]
            current = await self.catalog_service.find_table(
                snapshot.database.name,
                item.table_name,
            )
            fingerprint = self.catalog_service.schema_fingerprint(table.model_dump(mode="json"))
            if current is not None and current.schema_fingerprint == fingerprint:
                items[index] = item.model_copy(
                    update={
                        "status": "skipped",
                        "catalog_entry_id": current.catalog_entry_id,
                        "catalog_version": current.version,
                    }
                )
                job = await self._persist(
                    job,
                    items,
                    status="running",
                    current_table=item.table_name,
                )
                continue

            items[index] = item.model_copy(update={"status": "running"})
            job = await self._persist(
                job,
                items,
                status="running",
                current_table=item.table_name,
            )
            try:
                run = await self.understanding_service.understand_table(
                    job.snapshot_id,
                    item.table_name,
                )
                items[index] = items[index].model_copy(
                    update={
                        "status": "completed",
                        "run_id": run.run_id,
                        "catalog_entry_id": run.catalog_entry_id,
                        "catalog_version": run.catalog_version,
                    }
                )
            except WorkflowResumeRequiredError as exc:
                items[index] = items[index].model_copy(
                    update={
                        "status": "failed",
                        "run_id": exc.workflow_id,
                        "error": str(exc)[:1000] or "表理解失败",
                    }
                )
            except Exception as exc:
                items[index] = items[index].model_copy(
                    update={
                        "status": "failed",
                        "error": str(exc)[:1000] or "表理解失败",
                    }
                )
            job = await self._persist(
                job,
                items,
                status="running",
                current_table=item.table_name,
            )

        final_status = (
            "partial_failed" if any(item.status == "failed" for item in items) else "completed"
        )
        await self._persist(
            job,
            items,
            status=final_status,
            current_table=None,
        )

    async def get_job(self, job_id: str) -> CatalogBuildJob:
        return await run_in_threadpool(self.job_repository.get, job_id)

    async def _persist(
        self,
        job: CatalogBuildJob,
        items: list[CatalogBuildItem],
        *,
        status: str,
        current_table: str | None,
    ) -> CatalogBuildJob:
        completed = sum(item.status == "completed" for item in items)
        skipped = sum(item.status == "skipped" for item in items)
        failed = sum(item.status == "failed" for item in items)
        updated = job.model_copy(
            update={
                "status": status,
                "updated_at": datetime.now(UTC),
                "current_table": current_table,
                "processed_tables": completed + skipped + failed,
                "completed_tables": completed,
                "skipped_tables": skipped,
                "failed_tables": failed,
                "items": items,
            }
        )
        await run_in_threadpool(self.job_repository.save, updated)
        return updated

    @staticmethod
    def _new_job_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return f"catalog_build_{timestamp}_{uuid4().hex[:8]}"
