from dataclasses import dataclass

from starlette.concurrency import run_in_threadpool

from app.models import DatabaseSnapshot, QuerySemanticSource
from app.repositories.semantic_catalog import SemanticCatalogRepository
from app.repositories.semantic_review import SemanticReviewRepository


@dataclass(frozen=True, slots=True)
class EffectiveSemanticContext:
    payload: dict[str, object]
    sources: list[QuerySemanticSource]
    field_sources: dict[tuple[str, str], str]
    field_meanings: dict[tuple[str, str], str]


class EffectiveSemanticResolver:
    def __init__(
        self,
        catalog_repository: SemanticCatalogRepository,
        review_repository: SemanticReviewRepository,
    ) -> None:
        self.catalog_repository = catalog_repository
        self.review_repository = review_repository

    async def resolve(
        self,
        snapshot: DatabaseSnapshot,
    ) -> EffectiveSemanticContext:
        catalog_entries, latest_reviews = await run_in_threadpool(
            self._load_semantics,
            snapshot.database.name,
            snapshot.source.connection_id,
        )
        entry_map = {entry.table_name: entry for entry in catalog_entries}
        review_map = {
            (review.catalog_entry_id, review.source_catalog_version): review
            for review in latest_reviews
        }
        sources: list[QuerySemanticSource] = []
        field_sources: dict[tuple[str, str], str] = {}
        field_meanings: dict[tuple[str, str], str] = {}
        table_payloads: list[dict[str, object]] = []

        for table in snapshot.tables:
            entry = entry_map.get(table.name)
            review = (
                review_map.get((entry.catalog_entry_id, entry.version))
                if entry is not None
                else None
            )
            analysis = (
                review.reviewed_analysis
                if review is not None
                else entry.analysis
                if entry is not None
                else None
            )
            reviewed_fields = (
                {decision.column_name for decision in review.field_decisions}
                if review is not None
                else set()
            )
            semantic_columns = (
                {column.column_name: column for column in analysis.columns}
                if analysis is not None
                else {}
            )
            columns = []
            for column in table.columns:
                semantic = semantic_columns.get(column.name)
                candidates = semantic.meaning_candidates if semantic is not None else []
                if column.name in reviewed_fields:
                    source = "reviewed"
                elif entry is not None:
                    source = "ai_catalog"
                else:
                    source = "schema_only"
                meaning = (
                    candidates[0].meaning
                    if candidates
                    else column.comment
                    if column.comment
                    else column.name
                )
                field_sources[(table.name, column.name)] = source
                field_meanings[(table.name, column.name)] = meaning
                columns.append(
                    {
                        "name": column.name,
                        "column_type": column.column_type,
                        "nullable": column.nullable,
                        "database_comment": column.comment,
                        "semantic_source": source,
                        "meaning": meaning,
                        "description": (candidates[0].description if candidates else ""),
                        "alternative_meanings": [
                            candidate.meaning for candidate in candidates[1:3]
                        ],
                    }
                )

            if review is not None and review.table_decision is not None:
                table_source = "reviewed"
            elif entry is not None:
                table_source = "ai_catalog"
            else:
                table_source = "schema_only"
            sources.append(
                QuerySemanticSource(
                    table_name=table.name,
                    catalog_version=entry.version if entry is not None else None,
                    review_version=review.display_version if review is not None else None,
                    source=table_source,
                )
            )
            table_payloads.append(
                {
                    "name": table.name,
                    "database_comment": table.comment,
                    "primary_key": table.primary_key,
                    "estimated_row_count": table.estimated_row_count,
                    "semantic_source": table_source,
                    "meaning": (
                        analysis.table_candidates[0].meaning
                        if analysis is not None and analysis.table_candidates
                        else table.comment
                    ),
                    "summary": analysis.summary if analysis is not None else "",
                    "columns": columns,
                }
            )

        return EffectiveSemanticContext(
            payload={
                "database": snapshot.database.name,
                "tables": table_payloads,
                "declared_relationships": [
                    relationship.model_dump(mode="json")
                    for relationship in snapshot.declared_relationships
                ],
            },
            sources=sources,
            field_sources=field_sources,
            field_meanings=field_meanings,
        )

    def _load_semantics(
        self,
        database_name: str,
        connection_id: str | None,
    ):
        entries = [
            entry
            for entry in self.catalog_repository.list(database_name)
            if entry.connection_id == connection_id
        ]
        return (
            entries,
            self.review_repository.list_latest(database_name),
        )
