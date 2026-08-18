from typing import Any

from app.core.exceptions import DatabaseTableNotFoundError
from app.models import (
    DatabaseSnapshot,
    EvidenceStep,
    TableSchema,
    TableUnderstandingPayload,
)


class UnderstandingContextBuilder:
    def build(
        self,
        snapshot: DatabaseSnapshot,
        table_name: str,
        evidence_steps: list[EvidenceStep] | None = None,
        max_evidence_rounds: int = 3,
    ) -> dict[str, Any]:
        evidence_steps = evidence_steps or []
        completed_rounds = max(
            (step.round_number for step in evidence_steps),
            default=0,
        )
        tables_by_name = {table.name: table for table in snapshot.tables}
        target = tables_by_name.get(table_name)
        if target is None:
            raise DatabaseTableNotFoundError(table_name)

        relevant_relationships = [
            relationship
            for relationship in snapshot.declared_relationships
            if relationship.source_table == table_name or relationship.target_table == table_name
        ]
        related_names = {
            name
            for relationship in relevant_relationships
            for name in (relationship.source_table, relationship.target_table)
            if name != table_name
        }
        related_tables = [
            self._compact_table(tables_by_name[name])
            for name in sorted(related_names)
            if name in tables_by_name
        ]
        database_inventory = [
            {
                "name": table.name,
                "comment": table.comment,
                "primary_key": table.primary_key,
                "column_count": len(table.columns),
            }
            for table in snapshot.tables
        ]

        return {
            "task": "infer_table_semantics",
            "evidence_scope": ("schema_and_query_evidence" if evidence_steps else "schema_only"),
            "snapshot_id": snapshot.snapshot_id,
            "database": {
                "type": snapshot.source.database_type,
                "name": snapshot.database.name,
                "server_version": snapshot.database.server_version,
            },
            "target_table": target.model_dump(mode="json"),
            "declared_relationships": [
                relationship.model_dump(mode="json") for relationship in relevant_relationships
            ],
            "related_tables": related_tables,
            "database_inventory": database_inventory,
            "query_evidence": [step.model_dump(mode="json") for step in evidence_steps],
            "evidence_loop": {
                "completed_database_query_rounds": completed_rounds,
                "max_database_query_rounds": max_evidence_rounds,
                "stop_early_when_semantics_are_sufficient": True,
            },
            "known_limitations": (
                [
                    "当前没有DataProfile",
                    "当前还没有SQL取证结果，请通过evidence_requests请求所需数据",
                    "当前没有未声明关系的值匹配证据",
                ]
                if not evidence_steps
                else [
                    "SQL结果有返回行数上限，truncated=true表示仅返回部分行",
                    "只可引用query_evidence中真实出现的结果",
                    "如果关键证据仍不足，请继续通过evidence_requests请求",
                ]
            ),
            "output_json_schema": TableUnderstandingPayload.model_json_schema(),
        }

    @staticmethod
    def _compact_table(table: TableSchema) -> dict[str, Any]:
        return {
            "name": table.name,
            "comment": table.comment,
            "primary_key": table.primary_key,
            "columns": [
                {
                    "name": column.name,
                    "data_type": column.data_type,
                    "column_type": column.column_type,
                    "nullable": column.nullable,
                    "comment": column.comment,
                    "is_primary_key": column.is_primary_key,
                    "is_unique": column.is_unique,
                }
                for column in table.columns
            ],
        }
