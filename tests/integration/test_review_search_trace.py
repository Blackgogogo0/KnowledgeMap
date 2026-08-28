from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from knowledgemap.audit import AuditLog
from knowledgemap.db import Database
from knowledgemap.evidence import EvidenceStore
from knowledgemap.models import ClaimStatus, ReviewAction, SearchQuery
from knowledgemap.repository import ClaimRepository, EvidenceRepository, SourceRepository
from knowledgemap.review import ReviewService
from knowledgemap.search import SearchService


NOW = datetime(2026, 8, 28, 8, 0, tzinfo=UTC)


def test_accept_indexes_claim_and_trace_reads_original(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    store = EvidenceStore(tmp_path / "evidence")
    raw = b"Header\nOAuth native apps use PKCE.\nFooter\n"
    blob = store.put(raw)
    source = SourceRepository(db).create("official-doc", "https://example.test/oauth", NOW)
    evidence = EvidenceRepository(db).create(
        source.source_id,
        "v1",
        blob.content_hash,
        NOW,
        blob.relative_path,
        "text/plain",
        {"line_start": 2, "line_end": 2, "stable_url": "https://example.test/oauth#L2"},
    )
    claim = ClaimRepository(db).create_pending(
        "OAuth native apps use PKCE", [evidence.evidence_id], NOW
    )
    ReviewService(db, AuditLog(db), clock=lambda: NOW).decide(
        claim.claim_id, ReviewAction.ACCEPT, actor="user", client="test"
    )
    search = SearchService(db, store)

    hit = search.search(SearchQuery(query="OAuth PKCE", top_k=5))[0]
    trace = search.trace(hit.claim_id)

    assert hit.review_status == ClaimStatus.ACCEPTED
    assert hit.evidence_ids == [evidence.evidence_id]
    assert trace.evidence[0].content_hash == blob.content_hash
    assert trace.evidence[0].excerpt == "OAuth native apps use PKCE."
    assert trace.evidence[0].locator["stable_url"].endswith("#L2")


def test_alias_projection_is_searchable(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    claim = ClaimRepository(db).create_pending("OpenID Connect adds identity", [], NOW)
    with db.transaction() as connection:
        view_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO knowledge_views (
                knowledge_view_id, title, tags_json, aliases_json
            ) VALUES (?, 'Identity protocols', '["identity"]', '["OIDC"]')
            """,
            (view_id,),
        )
        connection.execute(
            "INSERT INTO knowledge_view_claims VALUES (?, ?)",
            (view_id, claim.claim_id),
        )
    ReviewService(db, AuditLog(db), clock=lambda: NOW).decide(
        claim.claim_id, ReviewAction.ACCEPT, actor="user", client="test"
    )

    hits = SearchService(db).search(SearchQuery(query="OIDC"))

    assert [hit.claim_id for hit in hits] == [claim.claim_id]


def test_retrieval_regression_recall_and_evidence_hit_rate(tmp_path):
    fixture_path = Path(__file__).parents[1] / "retrieval" / "fixture.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    store = EvidenceStore(tmp_path / "evidence")
    source = SourceRepository(db).create("test-standard", "https://example.test/spec", NOW)
    review = ReviewService(db, AuditLog(db), clock=lambda: NOW)
    names: dict[str, str] = {}
    for index, item in enumerate(fixture["claims"], start=1):
        raw = (item["text"] + "\n").encode()
        blob = store.put(raw)
        evidence = EvidenceRepository(db).create(
            source.source_id,
            f"v{index}",
            blob.content_hash,
            NOW,
            blob.relative_path,
            "text/plain",
            {"line_start": 1, "line_end": 1},
        )
        claim = ClaimRepository(db).create_pending(item["text"], [evidence.evidence_id], NOW)
        names[item["name"]] = claim.claim_id
        action = (
            ReviewAction.ACCEPT
            if item["status"] == "accepted"
            else ReviewAction.DOWNGRADE_TO_DISPUTED
        )
        review.decide(claim.claim_id, action, actor="fixture", client="test")
    search = SearchService(db, store)
    recalled = 0
    expected_total = 0
    traced_hits = 0
    total_hits = 0
    for query in fixture["queries"]:
        hits = search.search(SearchQuery(query=query["query"], top_k=5))
        hit_ids = {hit.claim_id for hit in hits}
        expected_ids = {names[name] for name in query["expected"]}
        recalled += len(hit_ids & expected_ids)
        expected_total += len(expected_ids)
        for hit in hits:
            total_hits += 1
            if search.trace(hit.claim_id).evidence:
                traced_hits += 1

    assert recalled / expected_total >= 0.90
    assert traced_hits / total_hits == 1.0
