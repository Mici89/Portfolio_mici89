from datetime import UTC, datetime
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.adapters.database import DatabaseAdapterFactory, DatabaseConnectionConfig
from app.models import DatabaseSnapshot, ScanStatistics
from app.repositories.database_snapshot import DatabaseSnapshotRepository


class DatabaseSnapshotService:
    def __init__(
        self,
        repository: DatabaseSnapshotRepository,
        adapter_factory: DatabaseAdapterFactory,
    ) -> None:
        self.repository = repository
        self.adapter_factory = adapter_factory

    async def create_snapshot(
        self,
        config: DatabaseConnectionConfig,
    ) -> DatabaseSnapshot:
        adapter = self.adapter_factory.create(config)
        inspection = await run_in_threadpool(adapter.inspect_schema)
        statistics = ScanStatistics(
            table_count=sum(table.table_type == "BASE TABLE" for table in inspection.tables),
            view_count=sum(table.table_type != "BASE TABLE" for table in inspection.tables),
            column_count=sum(len(table.columns) for table in inspection.tables),
            foreign_key_count=len(inspection.declared_relationships),
            index_count=sum(len(table.indexes) for table in inspection.tables),
        )
        snapshot = DatabaseSnapshot(
            snapshot_id=self._new_snapshot_id(),
            captured_at=datetime.now(UTC),
            source=inspection.source,
            database=inspection.database,
            tables=inspection.tables,
            declared_relationships=inspection.declared_relationships,
            scan_statistics=statistics,
        )
        await run_in_threadpool(self.repository.save, snapshot)
        return snapshot

    async def get_snapshot(self, snapshot_id: str) -> DatabaseSnapshot:
        return await run_in_threadpool(self.repository.get, snapshot_id)

    @staticmethod
    def _new_snapshot_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return f"snap_{timestamp}_{uuid4().hex[:8]}"
