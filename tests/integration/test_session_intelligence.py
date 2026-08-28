from datetime import UTC, datetime

import pytest

from knowledgemap.audit import AuditLog
from knowledgemap.db import Database
from knowledgemap.search import SearchService
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
from knowledgemap.session_intelligence.repository import SessionIntelligenceRepository
from knowledgemap.session_intelligence.service import SessionIntelligenceService
from knowledgemap.sessions.service import SessionService


NOW = datetime(2026, 8, 28, tzinfo=UTC)


class NoReadSessionService:
    def grant_and_read(self, *args, **kwargs):
        raise AssertionError("client-assisted submit must not read the session")


def submission(client="codex", checkpoint_id="c1", need_id="n1"):
    evidence = EvidencePointer(message_id="m7", excerpt="SDK support was only guessed")
    return SessionInsightSubmission(
        client=client,
        session_id="s1",
        checkpoint_id=checkpoint_id,
        last_message_id="m7",
        content_hash="a" * 64,
        episode_deltas=[
            TaskStateDelta(
                episode_id="e1",
                field=StateField.OBJECTIVE,
                operation="add",
                value="Choose the response contract",
                evidence=[evidence],
            )
        ],
        routes=[
            GapRouteDecision(
                unresolved_item_id="u1",
                route=GapRoute.SEARCH_KNOWLEDGE_MAP,
                rationale="Versioned evidence is required",
                evidence=[evidence],
            )
        ],
        knowledge_needs=[
            KnowledgeNeedDraft(
                need_id=need_id,
                unresolved_item_id="u1",
                question="Does the SDK support structured output?",
                decision_it_changes="Choose response contract",
                knowledge_type=KnowledgeType.CAPABILITY,
                why_context_is_insufficient="No official source",
                evidence=[evidence],
                confidence=0.9,
            )
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("client", ["codex", "claude-code"])
async def test_client_submission_never_reads_full_session(tmp_path, client):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    service = SessionIntelligenceService(
        SessionIntelligenceRepository(db, clock=lambda: NOW),
        NoReadSessionService(),
        analyzer=None,
        search=SearchService(db),
    )
    result = await service.submit(submission(client=client))
    assert result.checkpoint_id == "c1"
    with db.connect() as connection:
        serialized = " ".join(
            str(value)
            for row in connection.execute("SELECT excerpt FROM knowledge_need_evidence")
            for value in row
        )
    assert serialized == "SDK support was only guessed"


@pytest.mark.asyncio
async def test_resolve_without_hit_keeps_need_open(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    repository = SessionIntelligenceRepository(db, clock=lambda: NOW)
    service = SessionIntelligenceService(repository, NoReadSessionService(), None, SearchService(db))
    await service.submit(submission())
    result = service.resolve_need("n1")
    assert result.status == "open"
    assert result.hits == []
