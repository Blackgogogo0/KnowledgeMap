from types import SimpleNamespace

import pytest

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.mcp_server import create_server


class FakeApplication:
    def session_list(self, **kwargs): return []
    async def session_analyze(self, **kwargs): return {"recommendations": []}
    def session_revoke(self, **kwargs): return {"revoked": True}
    async def source_import(self, **kwargs): return {"claims": []}
    async def source_update(self, **kwargs): return {"status": "unchanged"}
    def review_list(self, **kwargs): return []
    def review_decide(self, **kwargs): return {"review_status": "accepted"}
    def knowledge_search(self, **kwargs):
        assert kwargs.get("statuses") is None
        return [{"claim_id": "c1", "review_status": "accepted"}]
    def knowledge_trace(self, **kwargs): return {"claim_id": kwargs["claim_id"]}
    def knowledge_status(self): return {"accepted_claims": 1}
    async def session_analysis_prepare(self, **kwargs): return {"checkpoint_id": "c1"}
    async def session_analysis_submit(self, **kwargs): return {"checkpoint_id": "c1"}
    def session_analysis_get(self, **kwargs): return {"checkpoint_id": "c1"}
    def knowledge_need_list(self, **kwargs): return []
    def knowledge_need_resolve(self, **kwargs): return {"status": "open", "hits": []}


@pytest.mark.asyncio
async def test_server_exposes_exact_phase_one_tools():
    server = create_server(FakeApplication())

    tools = {tool.name for tool in await server.list_tools()}

    assert tools == {
        "session_list", "session_analyze", "session_revoke", "source_import",
        "source_update", "review_list", "review_decide", "knowledge_search",
        "knowledge_trace", "knowledge_status",
        "session_analysis_prepare", "session_analysis_submit", "session_analysis_get",
        "knowledge_need_list", "knowledge_need_resolve",
    }


@pytest.mark.asyncio
async def test_search_defaults_to_accepted():
    result = await create_server(FakeApplication()).call_tool(
        "knowledge_search", {"query": "OAuth", "top_k": 5}
    )

    assert all(
        item["review_status"] == "accepted"
        for item in result.structured_content["hits"]
    )


@pytest.mark.asyncio
async def test_domain_error_is_structured_without_stack_or_secret():
    app = FakeApplication()
    def fail(**kwargs):
        raise KnowledgeMapError("CLAIM_NOT_FOUND", "Missing claim", {"token": "secret"})
    app.knowledge_trace = fail

    result = await create_server(app).call_tool("knowledge_trace", {"claim_id": "missing"})

    assert result.structured_content == {
        "ok": False,
        "error": {"code": "CLAIM_NOT_FOUND", "message": "Missing claim"},
    }
    assert "secret" not in str(result)
