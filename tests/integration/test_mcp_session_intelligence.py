import pytest

from knowledgemap.mcp_server import create_server


class FakeApplication:
    async def session_analysis_submit(self, **kwargs): return {"checkpoint_id": "c1"}
    def knowledge_need_list(self, **kwargs): return []


@pytest.mark.asyncio
async def test_session_submission_returns_structured_checkpoint():
    server = create_server(FakeApplication())
    result = await server.call_tool(
        "session_analysis_submit",
        {
            "submission": {
                "client": "codex",
                "session_id": "s1",
                "checkpoint_id": "c1",
                "content_hash": "a" * 64,
                "episode_deltas": [],
                "routes": [],
                "knowledge_needs": [],
            }
        },
    )
    assert result.structured_content["result"]["checkpoint_id"] == "c1"


@pytest.mark.asyncio
async def test_empty_knowledge_need_list_is_successful():
    result = await create_server(FakeApplication()).call_tool(
        "knowledge_need_list", {"status": "open", "top_k": 10}
    )
    assert result.structured_content == {"ok": True, "items": []}
