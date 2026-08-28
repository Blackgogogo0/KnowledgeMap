from pathlib import Path

import pytest

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sources.local import LocalSourceAdapter
from knowledgemap.sources.web import WebSourceAdapter


FIXTURES = Path(__file__).parents[1] / "fixtures" / "sources"


def test_local_adapter_reads_utf8_markdown_inside_allowed_root():
    result = LocalSourceAdapter(FIXTURES).fetch(FIXTURES / "article.md")

    assert result.media_type == "text/markdown"
    assert "authorization code flow" in result.text
    assert result.raw.startswith(b"# OAuth")


def test_local_adapter_rejects_pdf(tmp_path):
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.7")

    with pytest.raises(KnowledgeMapError, match="UNSUPPORTED_VISUAL_DOCUMENT"):
        LocalSourceAdapter(tmp_path).fetch(path)


def test_local_adapter_rejects_path_outside_allowed_root(tmp_path):
    outside = tmp_path.parent / "outside.md"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(KnowledgeMapError, match="SOURCE_PATH_NOT_ALLOWED"):
        LocalSourceAdapter(tmp_path).fetch(outside)


@pytest.mark.asyncio
async def test_web_adapter_extracts_html_and_records_redirect_metadata(respx_mock):
    respx_mock.get("https://docs.example/start").respond(
        status_code=302, headers={"location": "/article"}
    )
    respx_mock.get("https://docs.example/article").respond(
        content=(FIXTURES / "article.html").read_bytes(),
        headers={
            "content-type": "text/html; charset=utf-8",
            "etag": '"v2"',
            "last-modified": "Thu, 27 Aug 2026 01:00:00 GMT",
        },
    )
    adapter = WebSourceAdapter(resolver=lambda host: ["93.184.216.34"])

    result = await adapter.fetch("https://docs.example/start")

    assert result.canonical_uri == "https://docs.example/article"
    assert "Stable releases use semantic versioning" in result.text
    assert result.retrieval["redirects"] == ["https://docs.example/article"]
    assert result.retrieval["etag"] == '"v2"'
    assert result.retrieval["last_modified"].startswith("Thu")


@pytest.mark.asyncio
async def test_web_adapter_rejects_private_target_before_request(respx_mock):
    route = respx_mock.get("http://metadata.internal/latest").respond(text="secret")
    adapter = WebSourceAdapter(resolver=lambda host: ["169.254.169.254"])

    with pytest.raises(KnowledgeMapError, match="SOURCE_NETWORK_NOT_ALLOWED"):
        await adapter.fetch("http://metadata.internal/latest")

    assert route.call_count == 0


@pytest.mark.asyncio
async def test_web_adapter_rejects_oversized_response(respx_mock):
    respx_mock.get("https://docs.example/large").respond(content=b"x" * 33)
    adapter = WebSourceAdapter(
        resolver=lambda host: ["93.184.216.34"], max_bytes=32
    )

    with pytest.raises(KnowledgeMapError, match="SOURCE_TOO_LARGE"):
        await adapter.fetch("https://docs.example/large")
