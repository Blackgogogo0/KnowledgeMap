import httpx
import pytest

from knowledgemap.analyzer.openai import OpenAICompatibleAnalyzer
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sessions.base import SessionMessage


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

