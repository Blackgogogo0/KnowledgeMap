from datetime import UTC, datetime

from knowledgemap.audit import AuditLog
from knowledgemap.db import Database
from knowledgemap.models import ReviewAction, SearchQuery
from knowledgemap.repository import ClaimRepository
from knowledgemap.review import ReviewService
from knowledgemap.search import SearchService


NOW = datetime(2026, 8, 28, 8, 0, tzinfo=UTC)


def test_pending_claim_is_not_searchable(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    ClaimRepository(db).create_pending("OAuth authorization code", [], NOW)

    assert SearchService(db).search(SearchQuery(query="OAuth")) == []


def test_accept_indexes_claim_and_escapes_fts_operators(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    claim = ClaimRepository(db).create_pending("OAuth authorization code", [], NOW)
    ReviewService(db, AuditLog(db), clock=lambda: NOW).decide(
        claim.claim_id, ReviewAction.ACCEPT, actor="user", client="test"
    )

    hits = SearchService(db).search(SearchQuery(query='OAuth: "authorization code"'))

    assert [hit.claim_id for hit in hits] == [claim.claim_id]
    assert hits[0].score > 0


def test_excluded_term_removes_matching_claim(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    claims = ClaimRepository(db)
    legacy = claims.create_pending("OAuth legacy implicit flow", [], NOW)
    current = claims.create_pending("OAuth PKCE authorization flow", [], NOW)
    review = ReviewService(db, AuditLog(db), clock=lambda: NOW)
    for claim in (legacy, current):
        review.decide(claim.claim_id, ReviewAction.ACCEPT, actor="user", client="test")

    hits = SearchService(db).search(SearchQuery(query="OAuth -legacy"))

    assert [hit.claim_id for hit in hits] == [current.claim_id]
