from enum import StrEnum
from datetime import datetime

from pydantic import BaseModel, Field


class ClaimStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DISPUTED = "disputed"
    STALE_CANDIDATE = "stale_candidate"
    SUPERSEDED = "superseded"


class ReviewAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    DOWNGRADE_TO_DISPUTED = "downgrade-to-disputed"
    RESEARCH_MORE = "research-more"


class SearchQuery(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    statuses: list[ClaimStatus] = Field(default_factory=lambda: [ClaimStatus.ACCEPTED])
    source_types: list[str] = Field(default_factory=list)
    created_after: datetime | None = None
    created_before: datetime | None = None
    scope: str | None = None


class SourceRecord(BaseModel):
    source_id: str
    type: str
    canonical_uri: str
    created_at: datetime


class EvidenceRecord(BaseModel):
    evidence_id: str
    source_id: str
    version: str
    content_hash: str
    retrieved_at: datetime
    local_blob_path: str
    media_type: str
    locator: dict[str, object]


class ClaimRecord(BaseModel):
    claim_id: str
    statement: str
    review_status: ClaimStatus
    created_at: datetime
