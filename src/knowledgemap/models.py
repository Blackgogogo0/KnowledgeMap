from enum import StrEnum

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
