import pytest
from pydantic import ValidationError

from knowledgemap.models import ClaimStatus, ReviewAction, SearchQuery


def test_claim_status_rejects_unknown_value():
    with pytest.raises(ValueError):
        ClaimStatus("published")


def test_review_action_exposes_exact_review_gate_actions():
    assert {action.value for action in ReviewAction} == {
        "accept",
        "reject",
        "downgrade-to-disputed",
        "research-more",
    }


def test_search_query_rejects_non_positive_top_k():
    with pytest.raises(ValidationError):
        SearchQuery(query="OAuth", top_k=0)
