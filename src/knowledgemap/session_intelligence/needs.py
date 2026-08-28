import re
from dataclasses import dataclass

from knowledgemap.session_intelligence.models import (
    GapRoute,
    GapRouteDecision,
    KnowledgeNeedDraft,
)


KNOWLEDGE_ROUTES = {GapRoute.SEARCH_KNOWLEDGE_MAP, GapRoute.CHECK_FRESHNESS}
RANK_WEIGHTS = {
    "decision_impact": 0.4,
    "urgency": 0.2,
    "evidence_weakness": 0.25,
    "confidence": 0.15,
}


@dataclass(frozen=True)
class DedupeResult:
    needs: list[KnowledgeNeedDraft]
    merged_ids: dict[str, str]


def build_needs(
    routes: list[GapRouteDecision], drafts: list[KnowledgeNeedDraft]
) -> list[KnowledgeNeedDraft]:
    allowed = {
        route.unresolved_item_id
        for route in routes
        if route.route in KNOWLEDGE_ROUTES
    }
    return [draft for draft in drafts if draft.unresolved_item_id in allowed]


def canonicalize_question(question: str) -> str:
    return re.sub(r"[^\w]+", " ", question.casefold()).strip()


def dedupe_needs(
    existing: list[KnowledgeNeedDraft], incoming: list[KnowledgeNeedDraft]
) -> DedupeResult:
    combined = [item.model_copy(deep=True) for item in existing]
    merged: dict[str, str] = {}
    for candidate in incoming:
        match = next(
            (
                item
                for item in combined
                if canonicalize_question(item.question)
                == canonicalize_question(candidate.question)
                and item.version_or_time_scope == candidate.version_or_time_scope
                and candidate.same_decision_purpose
            ),
            None,
        )
        if match is None:
            combined.append(candidate.model_copy(deep=True))
            continue
        known = {(e.message_id, e.excerpt) for e in match.evidence}
        match.evidence.extend(
            evidence
            for evidence in candidate.evidence
            if (evidence.message_id, evidence.excerpt) not in known
        )
        merged[candidate.need_id] = match.need_id
    return DedupeResult(needs=combined, merged_ids=merged)


def rank_need(need: KnowledgeNeedDraft) -> float:
    score = sum(getattr(need, field) * weight for field, weight in RANK_WEIGHTS.items())
    return round(max(0.0, min(1.0, score)), 6)

