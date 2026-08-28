from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GapRoute(StrEnum):
    ASK_USER = "ask_user"
    SEARCH_KNOWLEDGE_MAP = "search_knowledge_map"
    CHECK_FRESHNESS = "check_freshness"
    INSPECT_LOCAL = "inspect_local"
    EXECUTE_OR_TEST = "execute_or_test"
    IGNORE = "ignore"


class KnowledgeNeedStatus(StrEnum):
    OPEN = "open"
    NEEDS_REFRESH = "needs_refresh"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class KnowledgeType(StrEnum):
    CONCEPT = "concept"
    CAPABILITY = "capability"
    IMPLEMENTATION = "implementation"
    COMPATIBILITY = "compatibility"
    SECURITY = "security"
    EVALUATION = "evaluation"
    VERSION_CHANGE = "version_change"


class StateField(StrEnum):
    OBJECTIVE = "objective"
    CONSTRAINTS = "constraints"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    DECISIONS = "decisions"
    KNOWN_FACTS = "known_facts"
    ASSUMPTIONS = "assumptions"
    UNRESOLVED_ITEMS = "unresolved_items"
    BLOCKERS = "blockers"
    ACTIONS_AND_OUTCOMES = "actions_and_outcomes"


class EvidencePointer(BaseModel):
    message_id: str = Field(min_length=1)
    excerpt: str = Field(min_length=1, max_length=500)


class TaskStateDelta(BaseModel):
    episode_id: str = Field(min_length=1)
    field: StateField
    operation: Literal["add", "replace", "remove"]
    value: str = Field(min_length=1)
    previous_value: str | None = None
    evidence: list[EvidencePointer] = Field(min_length=1)


class TaskStateSnapshot(BaseModel):
    episode_id: str
    objective: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    known_facts: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    actions_and_outcomes: list[str] = Field(default_factory=list)


class GapRouteDecision(BaseModel):
    unresolved_item_id: str = Field(min_length=1)
    route: GapRoute
    rationale: str = Field(min_length=1)
    evidence: list[EvidencePointer] = Field(min_length=1)


class KnowledgeNeedDraft(BaseModel):
    need_id: str = Field(min_length=1)
    unresolved_item_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    decision_it_changes: str = Field(min_length=1)
    current_assumption: str | None = None
    knowledge_type: KnowledgeType
    preferred_source_types: list[str] = Field(default_factory=list)
    version_or_time_scope: str | None = None
    why_context_is_insufficient: str = Field(min_length=1)
    evidence: list[EvidencePointer] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    decision_impact: float = Field(default=0.5, ge=0, le=1)
    urgency: float = Field(default=0.5, ge=0, le=1)
    evidence_weakness: float = Field(default=0.5, ge=0, le=1)
    same_decision_purpose: bool = False


class SessionInsightSubmission(BaseModel):
    client: Literal["codex", "claude-code"]
    session_id: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    previous_checkpoint_id: str | None = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    episode_deltas: list[TaskStateDelta] = Field(default_factory=list)
    routes: list[GapRouteDecision] = Field(default_factory=list)
    knowledge_needs: list[KnowledgeNeedDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_need_routes(self):
        routes = {route.unresolved_item_id: route.route for route in self.routes}
        valid = {GapRoute.SEARCH_KNOWLEDGE_MAP, GapRoute.CHECK_FRESHNESS}
        for need in self.knowledge_needs:
            if routes.get(need.unresolved_item_id) not in valid:
                raise ValueError("knowledge need requires a knowledge route")
        return self


class AnalysisEvent(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    text: str

