from datetime import UTC, datetime

import pytest

from knowledgemap.db import Database
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.session_intelligence.models import (
    EvidencePointer,
    GapRoute,
    GapRouteDecision,
    KnowledgeNeedDraft,
    KnowledgeType,
    SessionInsightSubmission,
    TaskStateSnapshot,
)
from knowledgemap.session_intelligence.repository import SessionIntelligenceRepository


NOW = datetime(2026, 8, 28, tzinfo=UTC)


def submission(checkpoint="c1", previous=None, content_hash="a" * 64):
    evidence = EvidencePointer(message_id="m1", excerpt="No official evidence exists")
    return SessionInsightSubmission(
        client="codex",
        session_id="s1",
        checkpoint_id=checkpoint,
        previous_checkpoint_id=previous,
        content_hash=content_hash,
        routes=[
            GapRouteDecision(
                unresolved_item_id="u1",
                route=GapRoute.SEARCH_KNOWLEDGE_MAP,
                rationale="External fact changes the contract",
                evidence=[evidence],
            )
        ],
        knowledge_needs=[
            KnowledgeNeedDraft(
                need_id=f"n-{checkpoint}",
                unresolved_item_id="u1",
                question="Does the SDK support structured output?",
                decision_it_changes="Choose response contract",
                knowledge_type=KnowledgeType.CAPABILITY,
                why_context_is_insufficient="No versioned source",
                evidence=[evidence],
                confidence=0.8,
            )
        ],
    )


@pytest.fixture
def repository(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    return SessionIntelligenceRepository(db, clock=lambda: NOW)


def test_commit_is_idempotent_and_persists_need(repository):
    item = submission()
    first = repository.commit_submission(item, [TaskStateSnapshot(episode_id="e1")])
    second = repository.commit_submission(item, [TaskStateSnapshot(episode_id="e1")])
    assert first.checkpoint_id == second.checkpoint_id == "c1"
    assert len(repository.list_needs(session_id="s1")) == 1


def test_out_of_order_checkpoint_is_rejected(repository):
    repository.commit_submission(submission(), [TaskStateSnapshot(episode_id="e1")])
    with pytest.raises(KnowledgeMapError, match="CHECKPOINT_CONFLICT"):
        repository.commit_submission(
            submission(checkpoint="c2", previous="wrong", content_hash="b" * 64),
            [TaskStateSnapshot(episode_id="e1")],
        )


def test_feedback_does_not_change_claim_state(repository):
    repository.commit_submission(submission(), [TaskStateSnapshot(episode_id="e1")])
    repository.record_feedback("n-c1", "not_useful")
    assert repository.list_needs(session_id="s1")[0]["status"] == "open"

