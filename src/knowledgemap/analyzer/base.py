from typing import Protocol

from pydantic import BaseModel, Field

from knowledgemap.sessions.base import SessionMessage


class KnowledgeRecommendationDraft(BaseModel):
    knowledge_question: str = Field(min_length=1)
    why_needed: str = Field(min_length=1)
    preferred_source_types: list[str] = Field(default_factory=list)


class SessionAnalysisDraft(BaseModel):
    goal: str = Field(min_length=1)
    existing_knowledge: list[str] = Field(default_factory=list)
    recommendations: list[KnowledgeRecommendationDraft] = Field(default_factory=list)


class ExtractableDocument(BaseModel):
    evidence_id: str
    content_hash: str
    text: str = Field(min_length=1)
    media_type: str


class ClaimDraft(BaseModel):
    statement: str = Field(min_length=1)
    evidence_id: str
    locator: dict[str, object]


class _ClaimDraftList(BaseModel):
    claims: list[ClaimDraft]


class Analyzer(Protocol):
    async def analyze_session(
        self, messages: list[SessionMessage]
    ) -> SessionAnalysisDraft: ...

    async def extract_claims(
        self, document: ExtractableDocument
    ) -> list[ClaimDraft]: ...
