from datetime import UTC, datetime

from starlette.concurrency import run_in_threadpool

from app.core.exceptions import SemanticReviewValidationError
from app.models import (
    CatalogEvidenceBundle,
    CatalogReviewCreate,
    CatalogReviewRevision,
    FieldReviewDecision,
    FieldReviewInput,
    SemanticCandidate,
    TableReviewDecision,
    TableReviewInput,
    TableUnderstandingPayload,
)
from app.repositories.semantic_review import SemanticReviewRepository
from app.repositories.understanding_run import UnderstandingRunRepository
from app.services.semantic_catalog import SemanticCatalogService


class SemanticReviewService:
    def __init__(
        self,
        review_repository: SemanticReviewRepository,
        catalog_service: SemanticCatalogService,
        run_repository: UnderstandingRunRepository,
    ) -> None:
        self.review_repository = review_repository
        self.catalog_service = catalog_service
        self.run_repository = run_repository

    async def create_review(
        self,
        database_name: str,
        table_name: str,
        payload: CatalogReviewCreate,
        connection_id: str | None = None,
    ) -> CatalogReviewRevision:
        entry = await self.catalog_service.get_table(
            database_name,
            table_name,
            connection_id,
        )
        if payload.source_catalog_version != entry.version:
            raise SemanticReviewValidationError(
                "待审核版本已经不是当前AI版本，请刷新后重新审核",
                http_status_code=409,
            )

        columns = {column.column_name: column for column in entry.analysis.columns}
        submitted_names = {decision.column_name for decision in payload.field_decisions}
        unknown_names = sorted(submitted_names - columns.keys())
        if unknown_names:
            raise SemanticReviewValidationError(f"审核字段不属于当前表：{', '.join(unknown_names)}")

        if payload.scope == "table":
            if payload.table_decision is None:
                raise SemanticReviewValidationError("整表审核必须确认表含义")
            missing_names = sorted(columns.keys() - submitted_names)
            if missing_names:
                raise SemanticReviewValidationError(
                    f"整表审核必须覆盖全部字段，缺少：{', '.join(missing_names)}"
                )

        previous = await run_in_threadpool(
            self.review_repository.latest,
            entry.catalog_entry_id,
            entry.version,
        )
        revision = previous.revision + 1 if previous is not None else 1
        field_decision_map = (
            {decision.column_name: decision for decision in previous.field_decisions}
            if previous is not None
            else {}
        )
        for field_input in payload.field_decisions:
            field_decision_map[field_input.column_name] = self._field_decision(
                columns[field_input.column_name].meaning_candidates,
                field_input,
            )

        table_decision = (
            self._table_decision(entry.analysis, payload.table_decision)
            if payload.table_decision is not None
            else previous.table_decision
            if previous is not None
            else None
        )
        reviewed_analysis = self._reviewed_analysis(
            entry.analysis,
            table_decision,
            field_decision_map,
            payload.reviewer,
        )
        total_field_count = len(columns)
        reviewed_field_count = len(field_decision_map)
        status = (
            "fully_reviewed"
            if table_decision is not None and reviewed_field_count == total_field_count
            else "partially_reviewed"
        )
        review = CatalogReviewRevision(
            review_id=f"{entry.catalog_entry_id}_v{entry.version}_r{revision}",
            catalog_entry_id=entry.catalog_entry_id,
            database_name=database_name,
            table_name=table_name,
            source_catalog_version=entry.version,
            revision=revision,
            display_version=f"v{entry.version}-r{revision}",
            schema_fingerprint=entry.schema_fingerprint,
            created_at=datetime.now(UTC),
            reviewer=payload.reviewer,
            scope=payload.scope,
            status=status,
            reviewed_field_count=reviewed_field_count,
            total_field_count=total_field_count,
            submitted_field_names=[decision.column_name for decision in payload.field_decisions],
            table_decision=table_decision,
            field_decisions=sorted(
                field_decision_map.values(),
                key=lambda decision: decision.column_name,
            ),
            note=payload.note,
            reviewed_analysis=reviewed_analysis,
        )
        await run_in_threadpool(self.review_repository.save, review)
        return review

    async def list_reviews(
        self,
        database_name: str,
        table_name: str,
        connection_id: str | None = None,
    ) -> list[CatalogReviewRevision]:
        entry = await self.catalog_service.get_table(
            database_name,
            table_name,
            connection_id,
        )
        return await run_in_threadpool(
            self.review_repository.list_for_entry,
            entry.catalog_entry_id,
        )

    async def list_latest_reviews(
        self,
        database_name: str,
        connection_id: str | None = None,
    ) -> list[CatalogReviewRevision]:
        reviews = await run_in_threadpool(
            self.review_repository.list_latest,
            database_name,
        )
        entries = await self.catalog_service.list_tables(database_name, connection_id)
        entry_ids = {entry.catalog_entry_id for entry in entries}
        return [review for review in reviews if review.catalog_entry_id in entry_ids]

    async def get_evidence(
        self,
        database_name: str,
        table_name: str,
        connection_id: str | None = None,
    ) -> CatalogEvidenceBundle:
        entry = await self.catalog_service.get_table(
            database_name,
            table_name,
            connection_id,
        )
        run = await run_in_threadpool(
            self.run_repository.get,
            entry.source_run_id,
        )
        return CatalogEvidenceBundle(
            catalog_entry_id=entry.catalog_entry_id,
            catalog_version=entry.version,
            table_name=entry.table_name,
            source_run_id=entry.source_run_id,
            generated_at=run.created_at,
            declared_relationships=entry.declared_relationships,
            evidence_steps=run.evidence_steps,
        )

    @staticmethod
    def _candidate(
        candidates: list[SemanticCandidate],
        index: int | None,
    ) -> SemanticCandidate | None:
        if index is None:
            return None
        if index >= len(candidates):
            raise SemanticReviewValidationError("选择的候选解释不存在")
        return candidates[index]

    def _field_decision(
        self,
        candidates: list[SemanticCandidate],
        payload: FieldReviewInput,
    ) -> FieldReviewDecision:
        source = self._candidate(candidates, payload.source_candidate_index)
        original_meaning = source.meaning if source is not None else ""
        original_description = source.description if source is not None else ""
        decision = (
            "confirmed"
            if payload.reviewed_meaning == original_meaning
            and payload.reviewed_description == original_description
            else "edited"
        )
        return FieldReviewDecision(
            column_name=payload.column_name,
            decision=decision,
            original_meaning=original_meaning,
            original_description=original_description,
            reviewed_meaning=payload.reviewed_meaning,
            reviewed_description=payload.reviewed_description,
            source_candidate_index=payload.source_candidate_index,
            note=payload.note,
        )

    def _table_decision(
        self,
        analysis: TableUnderstandingPayload,
        payload: TableReviewInput,
    ) -> TableReviewDecision:
        source = self._candidate(
            analysis.table_candidates,
            payload.source_candidate_index,
        )
        original_meaning = source.meaning if source is not None else ""
        decision = (
            "confirmed"
            if payload.reviewed_meaning == original_meaning
            and payload.reviewed_summary == analysis.summary
            else "edited"
        )
        return TableReviewDecision(
            decision=decision,
            original_meaning=original_meaning,
            original_summary=analysis.summary,
            reviewed_meaning=payload.reviewed_meaning,
            reviewed_summary=payload.reviewed_summary,
            source_candidate_index=payload.source_candidate_index,
            note=payload.note,
        )

    def _reviewed_analysis(
        self,
        analysis: TableUnderstandingPayload,
        table_decision: TableReviewDecision | None,
        field_decisions: dict[str, FieldReviewDecision],
        reviewer: str,
    ) -> TableUnderstandingPayload:
        table_candidates = analysis.table_candidates
        summary = analysis.summary
        if table_decision is not None:
            source = self._candidate(
                analysis.table_candidates,
                table_decision.source_candidate_index,
            )
            table_candidates = self._promote_reviewed_candidate(
                analysis.table_candidates,
                source,
                table_decision.reviewed_meaning,
                source.description if source is not None else "",
                reviewer,
            )
            summary = table_decision.reviewed_summary

        reviewed_columns = []
        for column in analysis.columns:
            decision = field_decisions.get(column.column_name)
            if decision is None:
                reviewed_columns.append(column)
                continue
            source = self._candidate(
                column.meaning_candidates,
                decision.source_candidate_index,
            )
            candidates = self._promote_reviewed_candidate(
                column.meaning_candidates,
                source,
                decision.reviewed_meaning,
                decision.reviewed_description,
                reviewer,
            )
            reviewed_columns.append(
                column.model_copy(
                    update={
                        "status": "inferred",
                        "meaning_candidates": candidates,
                    }
                )
            )

        return analysis.model_copy(
            update={
                "summary": summary,
                "table_candidates": table_candidates,
                "columns": reviewed_columns,
            }
        )

    @staticmethod
    def _promote_reviewed_candidate(
        candidates: list[SemanticCandidate],
        source: SemanticCandidate | None,
        meaning: str,
        description: str,
        reviewer: str,
    ) -> list[SemanticCandidate]:
        supporting_evidence = list(source.supporting_evidence) if source else []
        supporting_evidence.append(f"人工审核：{reviewer} 已确认或修订该解释")
        reviewed = SemanticCandidate(
            meaning=meaning,
            description=description,
            confidence=source.confidence if source is not None else 1.0,
            supporting_evidence=supporting_evidence[-8:],
            counter_evidence=list(source.counter_evidence) if source else [],
        )
        remaining = [
            candidate for candidate in candidates if source is None or candidate is not source
        ]
        return [reviewed, *remaining][:3]
