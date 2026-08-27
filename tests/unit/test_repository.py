from datetime import UTC, datetime

from knowledgemap.audit import AuditEvent, AuditLog
from knowledgemap.db import Database
from knowledgemap.models import ClaimStatus
from knowledgemap.repository import ClaimRepository, EvidenceRepository, SourceRepository


NOW = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def migrated_db(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    return db


def create_evidence(db):
    source = SourceRepository(db).create(
        source_type="web_documentation",
        canonical_uri="https://example.test/auth",
        created_at=NOW,
    )
    return EvidenceRepository(db).create(
        source_id=source.source_id,
        version="v1",
        content_hash="a" * 64,
        retrieved_at=NOW,
        local_blob_path="aa/" + "a" * 64,
        media_type="text/markdown",
        locator={"section": "Authentication"},
    )


def test_claim_replacement_creates_new_version_without_mutating_original(tmp_path):
    db = migrated_db(tmp_path)
    evidence = create_evidence(db)
    claims = ClaimRepository(db)
    original = claims.create_pending("The API uses OAuth.", [evidence.evidence_id], NOW)

    replacement = claims.propose_replacement(
        original.claim_id,
        "The API uses OAuth 2.1.",
        [evidence.evidence_id],
        NOW,
    )

    assert original.claim_id != replacement.claim_id
    assert claims.get(original.claim_id).statement == "The API uses OAuth."
    assert claims.get(original.claim_id).review_status == ClaimStatus.PENDING
    assert claims.relations_from(replacement.claim_id) == [
        (original.claim_id, "supersedes")
    ]


def test_claim_evidence_links_are_persisted(tmp_path):
    db = migrated_db(tmp_path)
    evidence = create_evidence(db)
    claims = ClaimRepository(db)

    claim = claims.create_pending("The API uses OAuth.", [evidence.evidence_id], NOW)

    assert claims.evidence_ids(claim.claim_id) == [evidence.evidence_id]


def test_audit_log_preserves_before_and_after_state(tmp_path):
    db = migrated_db(tmp_path)
    audit = AuditLog(db)
    event = AuditEvent(
        actor="user",
        client="codex",
        event_type="claim.reviewed",
        target_id="claim-1",
        before={"review_status": "pending"},
        after={"review_status": "accepted"},
        created_at=NOW,
    )

    stored = audit.append(event)

    assert audit.get(stored.event_id) == stored
    assert stored.before == {"review_status": "pending"}
    assert stored.after == {"review_status": "accepted"}
