from collections import Counter

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.session_intelligence.models import GapRouteDecision


def validate_routes(
    unresolved_item_ids: list[str], routes: list[GapRouteDecision]
) -> list[GapRouteDecision]:
    expected = set(unresolved_item_ids)
    actual = [route.unresolved_item_id for route in routes]
    unknown = set(actual) - expected
    if unknown:
        raise KnowledgeMapError("ROUTE_UNKNOWN_ITEM", "A route references an unknown item.")
    if any(count > 1 for count in Counter(actual).values()):
        raise KnowledgeMapError("ROUTE_DUPLICATE", "An unresolved item has multiple routes.")
    if set(actual) != expected:
        raise KnowledgeMapError("ROUTE_INCOMPLETE", "Every unresolved item needs one route.")
    return routes

