from datetime import UTC, datetime

from knowledgemap.audit import AuditLog
from knowledgemap.db import Database
from knowledgemap.evidence import EvidenceStore
from knowledgemap.models import ReviewAction
from knowledgemap.repository import ClaimRepository, EvidenceRepository, SourceRepository
from knowledgemap.review import ReviewService
from knowledgemap.sources.github import GitHubSourceAdapter


NOW = datetime(2026, 8, 28, tzinfo=UTC)


def test_modified_file_creates_stale_proposal_without_mutating_claim(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    store = EvidenceStore(tmp_path / "evidence")
    blob = store.put(b"old docs")
    source = SourceRepository(db).create("github", "https://github.com/o/r", NOW)
    evidence = EvidenceRepository(db).create(
        source.source_id, "aaa111", blob.content_hash, NOW, blob.relative_path,
        "text/markdown", {"path": "README.md", "commit": "aaa111"}
    )
    claims = ClaimRepository(db)
    claim = claims.create_pending("Repository uses old behavior", [evidence.evidence_id], NOW)
    ReviewService(db, AuditLog(db), clock=lambda: NOW).decide(
        claim.claim_id, ReviewAction.ACCEPT, actor="user", client="test"
    )
    adapter = GitHubSourceAdapter()
    diff = adapter.compare({"README.md": "old"}, {"README.md": "new"})

    proposals = adapter.propose_impacts(db, source.source_id, diff, NOW)

    assert proposals == [claim.claim_id]
    assert claims.get(claim.claim_id).review_status == "accepted"
    with db.connect() as connection:
        item = connection.execute("SELECT * FROM review_items").fetchone()
    assert item["proposed_action"] == "stale_candidate"


def test_contradiction_creates_disputed_proposal_without_mutating_claim(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    claims = ClaimRepository(db)
    claim = claims.create_pending("The API is stable", [], NOW)
    ReviewService(db, AuditLog(db), clock=lambda: NOW).decide(
        claim.claim_id, ReviewAction.ACCEPT, actor="user", client="test"
    )

    proposed = GitHubSourceAdapter.propose_conflicts(db, [claim.claim_id], NOW)

    assert proposed == [claim.claim_id]
    assert claims.get(claim.claim_id).review_status == "accepted"
    with db.connect() as connection:
        item = connection.execute("SELECT * FROM review_items").fetchone()
    assert item["proposed_action"] == "disputed"
