from typing import Protocol

from pydantic import BaseModel, Field

from knowledgemap.sessions.base import SessionMessage
from knowledgemap.session_intelligence.models import (
    AnalysisEvent,
    GapRouteDecision,
    KnowledgeNeedDraft,
    TaskStateDelta,
    TaskStateSnapshot,
)


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


class StateExtractionDraft(BaseModel):
    deltas: list[TaskStateDelta] = Field(default_factory=list)
    unresolved_item_ids: list[str] = Field(default_factory=list)


class RouteAnalysisDraft(BaseModel):
    routes: list[GapRouteDecision] = Field(default_factory=list)


class NeedAnalysisDraft(BaseModel):
    knowledge_needs: list[KnowledgeNeedDraft] = Field(default_factory=list, max_length=5)


class Analyzer(Protocol):
    async def extract_state(
        self, events: list[AnalysisEvent], previous_state: TaskStateSnapshot | None
    ) -> StateExtractionDraft: ...

    async def route_gaps(self, state: TaskStateSnapshot) -> RouteAnalysisDraft: ...

    async def compose_needs(
        self, state: TaskStateSnapshot, routes: list[GapRouteDecision]
    ) -> NeedAnalysisDraft: ...

    async def analyze_session(
        self, messages: list[SessionMessage]
    ) -> SessionAnalysisDraft: ...

    async def extract_claims(
        self, document: ExtractableDocument
    ) -> list[ClaimDraft]: ...
