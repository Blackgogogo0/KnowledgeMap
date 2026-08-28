import httpx
import pytest

from knowledgemap.analyzer.openai import OpenAICompatibleAnalyzer
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sessions.base import SessionMessage
from knowledgemap.session_intelligence.models import AnalysisEvent, TaskStateSnapshot


@pytest.fixture
def analyzer():
    return OpenAICompatibleAnalyzer(
        base_url="http://llm.test",
        model="test-model",
        timeout=1.0,
    )


@pytest.mark.asyncio
async def test_analyzer_validates_structured_session_output(respx_mock, analyzer):
    route = respx_mock.post("http://llm.test/v1/chat/completions").respond(
        json={
            "choices": [
                {
                    "message": {
                        "content": """{
                            "goal": "Choose an OAuth design",
                            "existing_knowledge": ["OAuth uses tokens"],
                            "recommendations": [{
                                "knowledge_question": "Which OAuth flow fits native apps?",
                                "why_needed": "The flow changes the threat model.",
                                "preferred_source_types": ["standard", "official-doc"]
                            }]
                        }"""
                    }
                }
            ]
        }
    )

    result = await analyzer.analyze_session(
        [SessionMessage(role="user", text="Help choose an OAuth flow")]
    )

    assert route.call_count == 1
    assert result.goal == "Choose an OAuth design"
    assert result.recommendations[0].knowledge_question.startswith("Which OAuth")
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer local"
    assert request.url.path == "/v1/chat/completions"


@pytest.mark.asyncio
async def test_analyzer_rejects_invalid_json(respx_mock, analyzer):
    respx_mock.post("http://llm.test/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "not-json"}}]}
    )

    with pytest.raises(KnowledgeMapError, match="ANALYZER_INVALID_OUTPUT"):
        await analyzer.analyze_session(
            [SessionMessage(role="user", text="Learn OAuth")]
        )


@pytest.mark.asyncio
async def test_analyzer_retries_timeout_only_within_bound(respx_mock, analyzer):
    route = respx_mock.post("http://llm.test/v1/chat/completions").mock(
        side_effect=httpx.ReadTimeout("slow analyzer")
    )

    with pytest.raises(KnowledgeMapError, match="ANALYZER_UNAVAILABLE"):
        await analyzer.analyze_session(
            [SessionMessage(role="user", text="Learn OAuth")]
        )

    assert route.call_count == 2


@pytest.mark.asyncio
async def test_staged_analyzer_extracts_state(respx_mock, analyzer):
    route = respx_mock.post("http://llm.test/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": """{
            "deltas": [{
                "episode_id": "e1", "field": "objective", "operation": "add",
                "value": "Choose an SDK", "evidence": [{"message_id": "m1", "excerpt": "Choose SDK"}]
            }],
            "unresolved_item_ids": ["u1"]
        }"""}}]}
    )
    result = await analyzer.extract_state(
        [AnalysisEvent(message_id="m1", role="user", text="Choose SDK")], None
    )
    assert result.deltas[0].value == "Choose an SDK"
    assert "Task state" in route.calls[0].request.content.decode()


@pytest.mark.asyncio
async def test_staged_analyzer_routes_gaps(respx_mock, analyzer):
    respx_mock.post("http://llm.test/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": """{
            "routes": [{"unresolved_item_id": "u1", "route": "ask_user",
            "rationale": "Acceptance criteria missing",
            "evidence": [{"message_id": "m1", "excerpt": "make it better"}]}]
        }"""}}]}
    )
    result = await analyzer.route_gaps(TaskStateSnapshot(episode_id="e1", unresolved_items=["u1"]))
    assert result.routes[0].route == "ask_user"


@pytest.mark.asyncio
async def test_staged_analyzer_composes_needs(respx_mock, analyzer):
    respx_mock.post("http://llm.test/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": """{
            "knowledge_needs": [{
                "need_id": "n1", "unresolved_item_id": "u1",
                "question": "Does SDK v2 support structured output?",
                "decision_it_changes": "Choose response contract",
                "knowledge_type": "capability",
                "why_context_is_insufficient": "No official evidence",
                "evidence": [{"message_id": "m1", "excerpt": "SDK might support it"}],
                "confidence": 0.8
            }]
        }"""}}]}
    )
    result = await analyzer.compose_needs(TaskStateSnapshot(episode_id="e1"), [])
    assert result.knowledge_needs[0].need_id == "n1"

