from datetime import UTC, datetime
from pathlib import Path

import pytest

from knowledgemap.analyzer.base import ClaimDraft
from knowledgemap.db import Database
from knowledgemap.evidence import EvidenceStore
from knowledgemap.ingest import ImportRequest, IngestService
from knowledgemap.repository import ClaimRepository, EvidenceRepository, SourceRepository
from knowledgemap.sources.local import LocalSourceAdapter
from knowledgemap.errors import KnowledgeMapError


FIXTURES = Path(__file__).parents[1] / "fixtures" / "sources"
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


class CheckingAnalyzer:
    def __init__(self, store):
        self.store = store
        self.snapshot_seen = False

    async def extract_claims(self, document):
        self.snapshot_seen = bool(self.store.read(document.content_hash))
        return [
            ClaimDraft(
                statement="Native applications should use authorization code flow with PKCE.",
                evidence_id=document.evidence_id,
                locator={"line_start": 3, "line_end": 3},
            )
        ]

    async def analyze_session(self, messages):
        raise AssertionError


class FailingAnalyzer(CheckingAnalyzer):
    async def extract_claims(self, document):
        assert self.store.read(document.content_hash)
        raise KnowledgeMapError("ANALYZER_UNAVAILABLE", "offline")


def make_service(tmp_path, analyzer_type=CheckingAnalyzer):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    store = EvidenceStore(tmp_path / "evidence")
    analyzer = analyzer_type(store)
    service = IngestService(
        sources=SourceRepository(db),
        evidence=EvidenceRepository(db),
        claims=ClaimRepository(db),
        evidence_store=store,
        analyzer=analyzer,
        local=LocalSourceAdapter(FIXTURES),
        clock=lambda: NOW,
    )
    return db, store, analyzer, service


@pytest.mark.asyncio
async def test_markdown_is_snapshotted_before_claim_extraction(tmp_path):
    _, store, analyzer, service = make_service(tmp_path)

    result = await service.import_source(
        ImportRequest(uri=str(FIXTURES / "article.md"), source_type="paper")
    )

    assert analyzer.snapshot_seen
    assert store.read(result.evidence.content_hash)
    assert all(claim.review_status == "pending" for claim in result.claims)


@pytest.mark.asyncio
async def test_duplicate_content_reuses_source_and_evidence(tmp_path):
    db, _, _, service = make_service(tmp_path)

    first = await service.import_source(
        ImportRequest(uri=str(FIXTURES / "article.md"), source_type="paper")
    )
    second = await service.import_source(
        ImportRequest(uri=str(FIXTURES / "article.md"), source_type="paper")
    )

    assert second.source.source_id == first.source.source_id
    assert second.evidence.evidence_id == first.evidence.evidence_id
    assert second.claims == []
    assert ClaimRepository(db).count() == 1


@pytest.mark.asyncio
async def test_analyzer_failure_retains_evidence_and_records_error(tmp_path):
    db, store, _, service = make_service(tmp_path, FailingAnalyzer)

    with pytest.raises(KnowledgeMapError, match="ANALYZER_UNAVAILABLE"):
        await service.import_source(
            ImportRequest(uri=str(FIXTURES / "article.md"), source_type="paper")
        )

    with db.connect() as connection:
        evidence = connection.execute("SELECT content_hash FROM evidence").fetchone()
        errors = connection.execute(
            "SELECT COUNT(*) FROM review_items WHERE target_type = 'source_import_error'"
        ).fetchone()[0]
    assert store.read(evidence["content_hash"])
    assert ClaimRepository(db).count() == 0
    assert errors == 1
