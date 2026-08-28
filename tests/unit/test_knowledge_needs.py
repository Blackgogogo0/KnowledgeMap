from knowledgemap.session_intelligence.models import (
    EvidencePointer,
    GapRoute,
    GapRouteDecision,
    KnowledgeNeedDraft,
    KnowledgeType,
)
from knowledgemap.session_intelligence.needs import build_needs, dedupe_needs, rank_need


def evidence(message_id):
    return EvidencePointer(message_id=message_id, excerpt="relevant evidence")


def route(item_id, value):
    return GapRouteDecision(
        unresolved_item_id=item_id,
        route=value,
        rationale="reason",
        evidence=[evidence("m1")],
    )


def need(need_id="n1", scope="v2", message_id="m1", same=False):
    return KnowledgeNeedDraft(
        need_id=need_id,
        unresolved_item_id="u1",
        question="Does the MCP SDK support structured output?",
        decision_it_changes="Choose the response contract",
        knowledge_type=KnowledgeType.CAPABILITY,
        version_or_time_scope=scope,
        why_context_is_insufficient="No versioned evidence exists",
        evidence=[evidence(message_id)],
        confidence=0.8,
        decision_impact=0.9,
        urgency=0.7,
        evidence_weakness=1.0,
        same_decision_purpose=same,
    )


def test_only_knowledge_routes_build_needs():
    drafts = [need()]
    assert build_needs([route("u1", GapRoute.SEARCH_KNOWLEDGE_MAP)], drafts) == drafts
    assert build_needs([route("u1", GapRoute.EXECUTE_OR_TEST)], drafts) == []


def test_dedupe_preserves_all_evidence_for_same_scope_and_purpose():
    result = dedupe_needs([need(message_id="m1")], [need("n2", message_id="m2", same=True)])
    assert len(result.needs) == 1
    assert {item.message_id for item in result.needs[0].evidence} == {"m1", "m2"}


def test_dedupe_keeps_different_version_scopes_separate():
    result = dedupe_needs([need(scope="v1")], [need("n2", scope="v2", same=True)])
    assert len(result.needs) == 2


def test_rank_is_bounded_and_prioritizes_decision_impact():
    high = rank_need(need())
    low_need = need().model_copy(update={"decision_impact": 0.0, "urgency": 0.0})
    assert 0 <= rank_need(low_need) < high <= 1

