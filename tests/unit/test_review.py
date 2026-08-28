from datetime import UTC, datetime

from knowledgemap.audit import AuditLog
from knowledgemap.db import Database
from knowledgemap.models import ClaimStatus, ReviewAction
from knowledgemap.repository import ClaimRepository
from knowledgemap.review import ReviewService


NOW = datetime(2026, 8, 28, 8, 0, tzinfo=UTC)


def test_research_more_leaves_claim_pending_and_records_review_item(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    claim = ClaimRepository(db).create_pending("OAuth needs evidence", [], NOW)
    review = ReviewService(db, AuditLog(db), clock=lambda: NOW)

    result = review.decide(
        claim.claim_id,
        ReviewAction.RESEARCH_MORE,
        actor="user",
        client="test",
        note="Find the current standard",
    )

    assert result.review_status == ClaimStatus.PENDING
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM review_items").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 1


def test_reject_updates_status_and_audits_decision(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    claim = ClaimRepository(db).create_pending("Unsupported claim", [], NOW)
    review = ReviewService(db, AuditLog(db), clock=lambda: NOW)

    result = review.decide(
        claim.claim_id, ReviewAction.REJECT, actor="user", client="test"
    )

    assert result.review_status == ClaimStatus.REJECTED
    with db.connect() as connection:
        event = connection.execute("SELECT * FROM audit_events").fetchone()
    assert event["event_type"] == "claim.reviewed"


def test_accepting_replacement_supersedes_original_atomically(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    claims = ClaimRepository(db)
    original = claims.create_pending("Old guidance", [], NOW)
    replacement = claims.propose_replacement(
        original.claim_id, "Current guidance", [], NOW
    )
    review = ReviewService(db, AuditLog(db), clock=lambda: NOW)
    review.decide(original.claim_id, ReviewAction.ACCEPT, actor="user", client="test")

    accepted = review.decide(
        replacement.claim_id, ReviewAction.ACCEPT, actor="user", client="test"
    )

    assert accepted.review_status == ClaimStatus.ACCEPTED
    assert claims.get(original.claim_id).review_status == ClaimStatus.SUPERSEDED
