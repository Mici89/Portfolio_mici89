from app.models import (
    ConversationContextResolution,
    ConversationRoutingDecision,
    QueryIntent,
)


class ConversationContextMerger:
    def resolve(
        self,
        routing: ConversationRoutingDecision,
        active_intent: QueryIntent | None,
    ) -> ConversationContextResolution:
        mode = self._effective_mode(routing, active_intent)
        if mode != "refine" or active_intent is None:
            return ConversationContextResolution(
                mode=mode,
                reason=routing.reason,
                added_metrics=self._unique(routing.added_metrics),
                added_dimensions=self._unique(routing.added_dimensions),
                added_filters=self._unique(routing.added_filters),
                detail_requests=self._unique(routing.detail_requests),
            )
        inherited_metrics = self._retained(
            [] if routing.replace_metrics else active_intent.metrics,
            routing.removed_metrics,
        )
        inherited_dimensions = self._retained(
            [] if routing.replace_dimensions else active_intent.dimensions,
            routing.removed_dimensions,
        )
        inherited_filters = self._retained(
            [] if routing.replace_filters else active_intent.filters,
            routing.removed_filters,
        )
        inherited_tables = self._unique(active_intent.tables)
        return ConversationContextResolution(
            mode="refine",
            reason=routing.reason,
            inherited_metrics=inherited_metrics,
            inherited_dimensions=inherited_dimensions,
            inherited_filters=inherited_filters,
            inherited_tables=inherited_tables,
            added_metrics=self._unique(routing.added_metrics),
            added_dimensions=self._unique(routing.added_dimensions),
            added_filters=self._unique(routing.added_filters),
            detail_requests=self._unique([*active_intent.detail_requests, *routing.detail_requests]),
            required_metrics=inherited_metrics,
            required_dimensions=inherited_dimensions,
            required_filters=inherited_filters,
            required_tables=inherited_tables,
        )

    @staticmethod
    def _effective_mode(
        routing: ConversationRoutingDecision,
        active_intent: QueryIntent | None,
    ) -> str:
        if active_intent is None:
            return "standalone"
        if not routing.standalone_intent_complete:
            return "refine"
        if routing.context_mode == "refine":
            return "refine"
        return "switch"

    @classmethod
    def _retained(cls, values: list[str], removed: list[str]) -> list[str]:
        removed_keys = {cls._key(value) for value in removed}
        return cls._unique(
            [value for value in values if cls._key(value) not in removed_keys]
        )

    @classmethod
    def _unique(cls, values: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = " ".join(value.split())
            key = cls._key(cleaned)
            if cleaned and key not in seen:
                unique.append(cleaned)
                seen.add(key)
        return unique

    @staticmethod
    def _key(value: str) -> str:
        return "".join(value.lower().split())
