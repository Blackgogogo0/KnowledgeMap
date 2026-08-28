from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from knowledgemap.analyzer.base import Analyzer, ExtractableDocument
from knowledgemap.evidence import EvidenceStore
from knowledgemap.models import ClaimRecord, EvidenceRecord, SourceRecord
from knowledgemap.repository import ClaimRepository, EvidenceRepository, SourceRepository
from knowledgemap.sources.local import LocalSourceAdapter
from knowledgemap.sources.web import WebSourceAdapter


class ImportRequest(BaseModel):
    uri: str = Field(min_length=1)
    source_type: str = Field(min_length=1)


class ImportResult(BaseModel):
    source: SourceRecord
    evidence: EvidenceRecord
    claims: list[ClaimRecord]


class IngestService:
    def __init__(
        self,
        sources: SourceRepository,
        evidence: EvidenceRepository,
        claims: ClaimRepository,
        evidence_store: EvidenceStore,
        analyzer: Analyzer,
        local: LocalSourceAdapter,
        web: WebSourceAdapter | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.sources = sources
        self.evidence = evidence
        self.claims = claims
        self.evidence_store = evidence_store
        self.analyzer = analyzer
        self.local = local
        self.web = web
        self.clock = clock or (lambda: datetime.now(UTC))

    async def import_source(self, request: ImportRequest) -> ImportResult:
        if urlsplit(request.uri).scheme in {"http", "https"}:
            if self.web is None:
                raise ValueError("WebSourceAdapter is required for HTTP(S) imports")
            fetched = await self.web.fetch(request.uri)
        else:
            fetched = self.local.fetch(request.uri)
        now = self.clock()
        source, _ = self.sources.get_or_create(
            request.source_type, fetched.canonical_uri, now
        )
        blob = self.evidence_store.put(fetched.raw)
        evidence = self.evidence.find(source.source_id, fetched.version, blob.content_hash)
        if evidence is not None:
            return ImportResult(source=source, evidence=evidence, claims=[])
        evidence = self.evidence.create(
            source_id=source.source_id,
            version=fetched.version,
            content_hash=blob.content_hash,
            retrieved_at=now,
            local_blob_path=blob.relative_path,
            media_type=fetched.media_type,
            locator={"canonical_uri": fetched.canonical_uri, **fetched.retrieval},
        )
        try:
            drafts = await self.analyzer.extract_claims(
                ExtractableDocument(
                    evidence_id=evidence.evidence_id,
                    content_hash=evidence.content_hash,
                    text=fetched.text,
                    media_type=fetched.media_type,
                )
            )
        except Exception as error:
            with self.sources.db.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO review_items (
                        review_item_id, target_type, target_id, proposed_action,
                        note, status, created_at
                    ) VALUES (?, 'source_import_error', ?, 'retry-analysis', ?, 'pending', ?)
                    """,
                    (str(uuid4()), evidence.evidence_id, type(error).__name__, now.isoformat()),
                )
            raise
        claims = []
        for draft in drafts:
            if draft.evidence_id != evidence.evidence_id or not draft.locator:
                continue
            claims.append(
                self.claims.create_pending(draft.statement, [evidence.evidence_id], now)
            )
        return ImportResult(source=source, evidence=evidence, claims=claims)
