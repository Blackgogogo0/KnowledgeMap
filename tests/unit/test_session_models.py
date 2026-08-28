import pytest
from pydantic import ValidationError

from knowledgemap.session_intelligence.models import (
    EvidencePointer,
    GapRoute,
    GapRouteDecision,
    KnowledgeNeedDraft,
    KnowledgeType,
    SessionInsightSubmission,
    StateField,
    TaskStateDelta,
)


def pointer(message_id="m1"):
    return EvidencePointer(message_id=message_id, excerpt="relevant text")


def test_state_delta_requires_evidence():
    with pytest.raises(ValidationError):
        TaskStateDelta(
            episode_id="episode-1",
            field=StateField.OBJECTIVE,
            operation="add",
            value="Choose an API",
            evidence=[],
        )


def test_knowledge_need_requires_decision_context_and_evidence():
    with pytest.raises(ValidationError):
        KnowledgeNeedDraft(
            need_id="need-1",
            unresolved_item_id="u1",
            question="Does the SDK support structured output?",
            decision_it_changes="",
            knowledge_type=KnowledgeType.CAPABILITY,
            why_context_is_insufficient="No API evidence",
            evidence=[pointer()],
            confidence=0.8,
        )


def test_submission_rejects_need_for_non_knowledge_route():
    route = GapRouteDecision(
        unresolved_item_id="u1",
        route=GapRoute.EXECUTE_OR_TEST,
        rationale="The next action is to run the test.",
        evidence=[pointer()],
    )
    need = KnowledgeNeedDraft(
        need_id="need-1",
        unresolved_item_id="u1",
        question="How should the test run?",
        decision_it_changes="Whether the implementation passes",
        knowledge_type=KnowledgeType.IMPLEMENTATION,
        why_context_is_insufficient="No result yet",
        evidence=[pointer()],
        confidence=0.8,
    )
    with pytest.raises(ValidationError, match="knowledge route"):
        SessionInsightSubmission(
            client="codex",
            session_id="s1",
            checkpoint_id="c1",
            content_hash="a" * 64,
            routes=[route],
            knowledge_needs=[need],
        )


def test_submission_accepts_need_for_search_route():
    route = GapRouteDecision(
        unresolved_item_id="u1",
        route=GapRoute.SEARCH_KNOWLEDGE_MAP,
        rationale="A current SDK fact changes the design.",
        evidence=[pointer()],
    )
    need = KnowledgeNeedDraft(
        need_id="need-1",
        unresolved_item_id="u1",
        question="Does the SDK support structured output?",
        decision_it_changes="Select the MCP response contract",
        knowledge_type=KnowledgeType.CAPABILITY,
        why_context_is_insufficient="No versioned source is present",
        evidence=[pointer()],
        confidence=0.8,
    )
    submission = SessionInsightSubmission(
        client="codex",
        session_id="s1",
        checkpoint_id="c1",
        content_hash="a" * 64,
        routes=[route],
        knowledge_needs=[need],
    )
    assert submission.knowledge_needs == [need]

