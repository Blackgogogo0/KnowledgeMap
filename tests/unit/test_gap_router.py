import pytest

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.session_intelligence.models import EvidencePointer, GapRoute, GapRouteDecision
from knowledgemap.session_intelligence.router import validate_routes


def route(item_id, value):
    return GapRouteDecision(
        unresolved_item_id=item_id,
        route=value,
        rationale="classified from the task state",
        evidence=[EvidencePointer(message_id="m1", excerpt="context")],
    )


def test_every_unresolved_item_has_exactly_one_route():
    assert validate_routes(["u1", "u2"], [route("u1", GapRoute.ASK_USER), route("u2", GapRoute.IGNORE)])


def test_missing_or_duplicate_route_is_rejected():
    with pytest.raises(KnowledgeMapError, match="ROUTE_INCOMPLETE"):
        validate_routes(["u1", "u2"], [route("u1", GapRoute.ASK_USER)])
    with pytest.raises(KnowledgeMapError, match="ROUTE_DUPLICATE"):
        validate_routes(
            ["u1"],
            [route("u1", GapRoute.ASK_USER), route("u1", GapRoute.SEARCH_KNOWLEDGE_MAP)],
        )


def test_route_for_unknown_item_is_rejected():
    with pytest.raises(KnowledgeMapError, match="ROUTE_UNKNOWN_ITEM"):
        validate_routes(["u1"], [route("u1", GapRoute.ASK_USER), route("u2", GapRoute.IGNORE)])

