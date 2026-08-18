import hashlib
import json
from datetime import UTC, datetime

from starlette.concurrency import run_in_threadpool

from app.core.exceptions import DatabaseTableNotFoundError
from app.models import (
    CatalogEvidenceSummary,
    DatabaseSnapshot,
    SemanticCatalogEntry,
    TableUnderstandingRun,
)
from app.repositories.database_snapshot import DatabaseSnapshotRepository
from app.repositories.semantic_catalog import SemanticCatalogRepository
from app.repositories.understanding_run import UnderstandingRunRepository


class SemanticCatalogService:
    def __init__(
        self,
        catalog_repository: SemanticCatalogRepository,
        snapshot_repository: DatabaseSnapshotRepository,
        run_repository: UnderstandingRunRepository,
    ) -> None:
        self.catalog_repository = catalog_repository
        self.snapshot_repository = snapshot_repository
        self.run_repository = run_repository

    async def publish_run(self, run_id: str) -> SemanticCatalogEntry:
        run = await run_in_threadpool(self.run_repository.get, run_id)
        snapshot = await run_in_threadpool(
            self.snapshot_repository.get,
            run.snapshot_id,
        )
        return await self.publish(run, snapshot)

    async def publish(
        self,
        run: TableUnderstandingRun,
        snapshot: DatabaseSnapshot,
    ) -> SemanticCatalogEntry:
        table = next(
            (table for table in snapshot.tables if table.name == run.table_name),
            None,
        )
        if table is None:
            raise DatabaseTableNotFoundError(run.table_name)

        entry_id = self.entry_id(
            snapshot.database.name,
            run.table_name,
            snapshot.source.connection_id,
        )
        current = await run_in_threadpool(
            self.catalog_repository.find,
            entry_id,
        )
        if current is not None and current.source_run_id == run.run_id:
            return current

        now = datetime.now(UTC)
        version = current.version + 1 if current is not None else 1
        first_published_at = current.first_published_at if current is not None else now
        statuses = [step.result.status for step in run.evidence_steps]
        entry = SemanticCatalogEntry(
            catalog_entry_id=entry_id,
            version=version,
            database_name=snapshot.database.name,
            connection_id=snapshot.source.connection_id,
            table_name=run.table_name,
            schema_fingerprint=self.schema_fingerprint(table.model_dump(mode="json")),
            snapshot_id=run.snapshot_id,
            source_run_id=run.run_id,
            first_published_at=first_published_at,
            published_at=now,
            completion_status=run.completion_status,
            termination_reason=run.termination_reason,
            prompt_version=run.prompt_version,
            provider=run.provider,
            model=run.model,
            evidence_summary=CatalogEvidenceSummary(
                database_query_rounds=run.evidence_round_count,
                generated_query_count=len(run.evidence_steps),
                executed_query_count=statuses.count("executed"),
                rejected_query_count=statuses.count("rejected"),
                failed_query_count=statuses.count("failed"),
            ),
            deferred_evidence_requests=run.deferred_evidence_requests,
            declared_relationships=[
                relationship
                for relationship in snapshot.declared_relationships
                if relationship.source_table == run.table_name
                or relationship.target_table == run.table_name
            ],
            analysis=run.analysis,
        )
        await run_in_threadpool(self.catalog_repository.save, entry)
        return entry

    async def get_table(
        self,
        database_name: str,
        table_name: str,
        connection_id: str | None = None,
    ) -> SemanticCatalogEntry:
        entry_id = self.entry_id(database_name, table_name, connection_id)
        return await run_in_threadpool(self.catalog_repository.get, entry_id)

    async def find_table(
        self,
        database_name: str,
        table_name: str,
        connection_id: str | None = None,
    ) -> SemanticCatalogEntry | None:
        entry_id = self.entry_id(database_name, table_name, connection_id)
        return await run_in_threadpool(self.catalog_repository.find, entry_id)

    async def list_tables(
        self,
        database_name: str,
        connection_id: str | None = None,
    ) -> list[SemanticCatalogEntry]:
        connection_id = connection_id or None
        entries = await run_in_threadpool(
            self.catalog_repository.list,
            database_name,
        )
        matched = [
            entry for entry in entries if entry.connection_id == connection_id
        ]
        if matched or connection_id is None:
            return matched
        # A reconnect creates a new connection id. The semantic catalog is still
        # valid for the same database/schema until a new snapshot changes it, so
        # expose the latest version per table instead of marking every table as
        # "待理解" merely because the session was reconnected.
        latest_by_table: dict[str, SemanticCatalogEntry] = {}
        for entry in entries:
            current = latest_by_table.get(entry.table_name)
            if current is None or (entry.version, entry.published_at) > (
                current.version,
                current.published_at,
            ):
                latest_by_table[entry.table_name] = entry
        return sorted(latest_by_table.values(), key=lambda entry: entry.table_name)

    @staticmethod
    def entry_id(
        database_name: str,
        table_name: str,
        connection_id: str | None = None,
    ) -> str:
        identity = (
            f"{connection_id}:{database_name}.{table_name}"
            if connection_id
            else f"{database_name}.{table_name}"
        ).encode()
        digest = hashlib.sha256(identity).hexdigest()[:20]
        return f"catalog_{digest}"

    @staticmethod
    def schema_fingerprint(table_payload: dict[str, object]) -> str:
        serialized = json.dumps(
            table_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode()).hexdigest()
