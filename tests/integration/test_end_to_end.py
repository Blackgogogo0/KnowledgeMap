from datetime import UTC, datetime
from pathlib import Path

import pytest

from knowledgemap.analyzer.base import (
    ClaimDraft,
    KnowledgeRecommendationDraft,
    SessionAnalysisDraft,
)
from knowledgemap.config import Settings
from knowledgemap.mcp_server import KnowledgeMapApplication
from knowledgemap.models import ReviewAction


FIXTURES = Path(__file__).parents[1] / "fixtures"


class AcceptanceAnalyzer:
    async def analyze_session(self, messages):
        return SessionAnalysisDraft(
            goal="Use versioned documentation",
            existing_knowledge=[],
            recommendations=[
                KnowledgeRecommendationDraft(
                    knowledge_question="Which release documentation is authoritative?",
                    why_needed="The answer depends on version.",
                    preferred_source_types=["official-doc"],
                )
            ],
        )

    async def extract_claims(self, document):
        return [
            ClaimDraft(
                statement="OAuth native applications should use PKCE authorization code flow.",
                evidence_id=document.evidence_id,
                locator={"line_start": 3, "line_end": 3},
            )
        ]


@pytest.mark.asyncio
async def test_session_to_recommendation_and_source_to_cited_answer(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        codex_session_root=FIXTURES / "sessions" / "codex",
        claude_session_root=FIXTURES / "sessions" / "claude",
        local_source_root=FIXTURES / "sources",
    )
    app = KnowledgeMapApplication(settings, analyzer=AcceptanceAnalyzer())

    sessions = app.session_list(client="codex")
    analysis = await app.session_analyze(
        client="codex", session_id=sessions[0].session_id, confirm_read=True
    )
    assert analysis.recommendations

    imported = await app.source_import(
        uri=str(FIXTURES / "sources" / "article.md"), source_type="paper"
    )
    assert imported.claims[0].review_status == "pending"
    app.review_decide(
        claim_id=imported.claims[0].claim_id,
        action=ReviewAction.ACCEPT,
        actor="user",
        client="test",
    )
    hit = app.knowledge_search("OAuth", top_k=5)[0]
    trace = app.knowledge_trace(hit.claim_id)

    assert hit.review_status == "accepted"
    assert trace.evidence[0].content_hash
    assert trace.evidence[0].locator
    assert "OAuth" in trace.evidence[0].excerpt
