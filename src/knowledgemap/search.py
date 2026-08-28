import json
import re
from pathlib import Path

from pydantic import BaseModel

from knowledgemap.db import Database
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.evidence import EvidenceStore
from knowledgemap.models import ClaimStatus, SearchQuery


class SearchHit(BaseModel):
    claim_id: str
    statement: str
    score: float
    review_status: ClaimStatus
    evidence_ids: list[str]
    source_types: list[str]
    source_uris: list[str]


class EvidenceTrace(BaseModel):
    evidence_id: str
    content_hash: str
    locator: dict[str, object]
    excerpt: str
    local_blob_path: str
    source_uri: str


class ClaimTrace(BaseModel):
    claim_id: str
    statement: str
    evidence: list[EvidenceTrace]


class SearchService:
    def __init__(self, db: Database, evidence_store: EvidenceStore | None = None):
        self.db = db
        self.evidence_store = evidence_store

    def search(self, query: SearchQuery) -> list[SearchHit]:
        expression = self._fts_expression(query.query)
        statuses = [status.value for status in query.statuses]
        clauses = [f"c.review_status IN ({','.join('?' for _ in statuses)})"]
        parameters: list[object] = [expression, *statuses]
        if query.source_types:
            clauses.append(
                f"s.type IN ({','.join('?' for _ in query.source_types)})"
            )
            parameters.extend(query.source_types)
        if query.created_after:
            clauses.append("c.created_at >= ?")
            parameters.append(query.created_after.isoformat())
        if query.created_before:
            clauses.append("c.created_at <= ?")
            parameters.append(query.created_before.isoformat())
        if query.scope:
            clauses.append("c.scope = ?")
            parameters.append(query.scope)
        sql = f"""
            SELECT c.claim_id, c.statement, c.review_status, bm25(claims_fts) AS rank,
                   ce.evidence_id, s.type AS source_type, s.canonical_uri
            FROM claims_fts
            JOIN claims c ON c.claim_id = claims_fts.claim_id
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            LEFT JOIN evidence e ON e.evidence_id = ce.evidence_id
            LEFT JOIN sources s ON s.source_id = e.source_id
            WHERE claims_fts MATCH ? AND {' AND '.join(clauses)}
            ORDER BY rank, c.claim_id, ce.evidence_id
        """
        with self.db.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        grouped: dict[str, SearchHit] = {}
        for row in rows:
            hit = grouped.get(row["claim_id"])
            if hit is None:
                hit = SearchHit(
                    claim_id=row["claim_id"],
                    statement=row["statement"],
                    score=1.0 / (1.0 + abs(float(row["rank"]))),
                    review_status=ClaimStatus(row["review_status"]),
                    evidence_ids=[],
                    source_types=[],
                    source_uris=[],
                )
                grouped[hit.claim_id] = hit
            if row["evidence_id"] and row["evidence_id"] not in hit.evidence_ids:
                hit.evidence_ids.append(row["evidence_id"])
            if row["source_type"] and row["source_type"] not in hit.source_types:
                hit.source_types.append(row["source_type"])
            if row["canonical_uri"] and row["canonical_uri"] not in hit.source_uris:
                hit.source_uris.append(row["canonical_uri"])
        return list(grouped.values())[: query.top_k]

    def trace(self, claim_id: str) -> ClaimTrace:
        if self.evidence_store is None:
            raise KnowledgeMapError("EVIDENCE_STORE_REQUIRED", "Tracing requires an evidence store.")
        with self.db.connect() as connection:
            claim = connection.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
            rows = connection.execute(
                """
                SELECT e.*, s.canonical_uri FROM claim_evidence ce
                JOIN evidence e ON e.evidence_id = ce.evidence_id
                JOIN sources s ON s.source_id = e.source_id
                WHERE ce.claim_id = ? ORDER BY e.evidence_id
                """,
                (claim_id,),
            ).fetchall()
        if claim is None:
            raise KnowledgeMapError("CLAIM_NOT_FOUND", "Claim was not found.")
        traces = []
        for row in rows:
            raw = self.evidence_store.read(row["content_hash"])
            locator = json.loads(row["locator_json"])
            text = raw.decode("utf-8", errors="replace")
            excerpt = self._excerpt(text, locator)
            traces.append(
                EvidenceTrace(
                    evidence_id=row["evidence_id"],
                    content_hash=row["content_hash"],
                    locator=locator,
                    excerpt=excerpt,
                    local_blob_path=str(Path(self.evidence_store.root) / row["local_blob_path"]),
                    source_uri=row["canonical_uri"],
                )
            )
        return ClaimTrace(claim_id=claim_id, statement=claim["statement"], evidence=traces)

    @staticmethod
    def _fts_expression(value: str) -> str:
        tokens = re.findall(r'"([^"]+)"|([+-]?\w+)', value, flags=re.UNICODE)
        positive: list[str] = []
        negative: list[str] = []
        for phrase, word in tokens:
            token = phrase or word
            if word.startswith("-") and len(word) > 1:
                negative.append(word[1:])
            else:
                positive.append(token.lstrip("+"))
        if not positive:
            raise KnowledgeMapError("SEARCH_QUERY_INVALID", "Search needs a positive term.")
        quote = lambda item: '"' + item.replace('"', '""') + '"'
        expression = " AND ".join(quote(item) for item in positive)
        if negative:
            expression += " " + " ".join(f"NOT {quote(item)}" for item in negative)
        return expression

    @staticmethod
    def _excerpt(text: str, locator: dict[str, object]) -> str:
        lines = text.splitlines()
        start = int(locator.get("line_start", 1))
        end = int(locator.get("line_end", min(start + 2, len(lines))))
        return "\n".join(lines[max(0, start - 1) : max(start, end)]).strip()
