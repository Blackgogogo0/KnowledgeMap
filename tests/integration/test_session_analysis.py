from datetime import UTC, datetime
from pathlib import Path

import pytest

from knowledgemap.analyzer.base import (
    KnowledgeRecommendationDraft,
    SessionAnalysisDraft,
)
from knowledgemap.analyzer.service import AnalysisService
from knowledgemap.audit import AuditLog
from knowledgemap.db import Database
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.repository import ClaimRepository
from knowledgemap.sessions.codex import CodexSessionReader
from knowledgemap.sessions.service import SessionService


FIXTURES = Path(__file__).parents[1] / "fixtures" / "sessions"
NOW = datetime(2026, 8, 27, 10, 0, tzinfo=UTC)


class FakeAnalyzer:
    async def analyze_session(self, messages):
        assert messages
        return SessionAnalysisDraft(
            goal="Select versioned technical guidance",
            existing_knowledge=["Release docs exist"],
            recommendations=[
                KnowledgeRecommendationDraft(
                    knowledge_question="Which release changed the API?",
                    why_needed="The answer must match the installed version.",
                    preferred_source_types=["official-doc", "github"],
                )
            ],
        )

    async def extract_claims(self, document):
        raise AssertionError("session analysis must not extract claims")


def make_services(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    sessions = SessionService(
        db,
        AuditLog(db),
        {"codex": CodexSessionReader(FIXTURES / "codex")},
    )
    analysis = AnalysisService(db, sessions, FakeAnalyzer(), clock=lambda: NOW)
    return db, sessions, analysis


@pytest.mark.asyncio
async def test_session_analysis_only_creates_recommendations(tmp_path):
    db, _, service = make_services(tmp_path)

    result = await service.analyze_authorized_session(
        client="codex",
        session_id="session-codex",
        confirm_read=True,
    )

    assert result.goal == "Select versioned technical guidance"
    assert len(result.recommendations) == 1
    assert result.recommendations[0].status == "pending"
    assert ClaimRepository(db).count() == 0
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM session_analyses"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM recommendations"
        ).fetchone()[0] == 1


@pytest.mark.asyncio
async def test_revoked_grant_cannot_be_analyzed(tmp_path):
    _, sessions, service = make_services(tmp_path)
    sessions.grant_and_read("codex", "session-codex", confirm_read=True, now=NOW)
    sessions.revoke("codex", "session-codex", now=NOW)

    with pytest.raises(KnowledgeMapError, match="SESSION_NOT_AUTHORIZED"):
        await service.analyze_existing_grant("codex", "session-codex")
