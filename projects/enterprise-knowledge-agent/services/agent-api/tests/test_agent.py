import uuid

from app.agent.service import _citations_are_valid
from app.agent.state import AgentState


def test_agent_state_deduplicates_evidence() -> None:
    state = AgentState(
        question="年假有几天？",
        knowledge_base_id=uuid.uuid4(),
        top_k=5,
    )
    first = state.add_evidence(
        document_id=uuid.uuid4(),
        chunk_index=0,
        content="员工享有十天年假。",
        similarity=0.8,
        metadata=None,
    )
    duplicate = state.add_evidence(
        document_id=first.document_id,
        chunk_index=0,
        content="员工享有十天年假。",
        similarity=0.8,
        metadata=None,
    )

    assert first.source_number == 1
    assert duplicate.source_number == 1
    assert len(state.evidence) == 1


def test_citation_validation_requires_known_source() -> None:
    state = AgentState(question="年假有几天？", knowledge_base_id=uuid.uuid4(), top_k=5)
    state.add_evidence(
        document_id=uuid.uuid4(),
        chunk_index=0,
        content="员工享有十天年假。",
        similarity=0.8,
        metadata=None,
    )

    assert _citations_are_valid("员工享有十天年假。[资料 1]", state.evidence)
    assert not _citations_are_valid("员工享有十天年假。[资料 2]", state.evidence)
    assert not _citations_are_valid("员工享有十天年假。", state.evidence)
