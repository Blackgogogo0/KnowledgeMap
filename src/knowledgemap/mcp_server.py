import inspect
from datetime import UTC, datetime
from typing import Any

from mcp.server import MCPServer
from pydantic import BaseModel

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.models import ReviewAction
from knowledgemap.analyzer.openai import OpenAICompatibleAnalyzer
from knowledgemap.analyzer.service import AnalysisService
from knowledgemap.audit import AuditLog
from knowledgemap.config import Settings
from knowledgemap.db import Database
from knowledgemap.evidence import EvidenceStore
from knowledgemap.ingest import ImportRequest, IngestService
from knowledgemap.models import ClaimStatus, SearchQuery
from knowledgemap.repository import ClaimRepository, EvidenceRepository, SourceRepository
from knowledgemap.review import ReviewService
from knowledgemap.search import SearchService
from knowledgemap.sessions.claude import ClaudeSessionReader
from knowledgemap.sessions.codex import CodexSessionReader
from knowledgemap.sessions.service import SessionService
from knowledgemap.sources.local import LocalSourceAdapter
from knowledgemap.sources.web import WebSourceAdapter
from knowledgemap.update import UpdateService


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


async def _call(function, **kwargs) -> dict[str, Any]:
    try:
        result = function(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return {"ok": True, "result": _normalize(result)}
    except KnowledgeMapError as error:
        return {
            "ok": False,
            "error": {"code": error.code, "message": error.message},
        }


def create_server(app) -> MCPServer:
    server = MCPServer(
        name="KnowledgeMap",
        description="Local-first evidence-backed knowledge service",
        version="0.1.0",
    )

    @server.tool(name="session_list", structured_output=True)
    async def session_list(
        client: str, project: str | None = None, since: datetime | None = None
    ) -> dict[str, Any]:
        response = await _call(app.session_list, client=client, project=project, since=since)
        if response["ok"]:
            return {"ok": True, "sessions": response.pop("result")}
        return response

    @server.tool(name="session_analyze", structured_output=True)
    async def session_analyze(
        client: str, session_id: str, confirm_read: bool
    ) -> dict[str, Any]:
        return await _call(
            app.session_analyze,
            client=client,
            session_id=session_id,
            confirm_read=confirm_read,
        )

    @server.tool(name="session_revoke", structured_output=True)
    async def session_revoke(client: str, session_id: str) -> dict[str, Any]:
        return await _call(app.session_revoke, client=client, session_id=session_id)

    @server.tool(name="source_import", structured_output=True)
    async def source_import(uri: str, source_type: str) -> dict[str, Any]:
        return await _call(app.source_import, uri=uri, source_type=source_type)

    @server.tool(name="source_update", structured_output=True)
    async def source_update(source_id: str) -> dict[str, Any]:
        return await _call(app.source_update, source_id=source_id)

    @server.tool(name="review_list", structured_output=True)
    async def review_list(status: str = "pending") -> dict[str, Any]:
        response = await _call(app.review_list, status=status)
        if response["ok"]:
            return {"ok": True, "items": response.pop("result")}
        return response

    @server.tool(name="review_decide", structured_output=True)
    async def review_decide(
        claim_id: str,
        action: ReviewAction,
        actor: str,
        client: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        return await _call(
            app.review_decide,
            claim_id=claim_id,
            action=action,
            actor=actor,
            client=client,
            note=note,
        )

    @server.tool(name="knowledge_search", structured_output=True)
    async def knowledge_search(query: str, top_k: int = 5) -> dict[str, Any]:
        response = await _call(app.knowledge_search, query=query, top_k=top_k, statuses=None)
        if response["ok"]:
            return {"ok": True, "hits": response.pop("result")}
        return response

    @server.tool(name="knowledge_trace", structured_output=True)
    async def knowledge_trace(claim_id: str) -> dict[str, Any]:
        return await _call(app.knowledge_trace, claim_id=claim_id)

    @server.tool(name="knowledge_status", structured_output=True)
    async def knowledge_status() -> dict[str, Any]:
        return await _call(app.knowledge_status)

    return server


class KnowledgeMapApplication:
    def __init__(self, settings: Settings, analyzer=None):
        self.settings = settings
        self.db = Database(settings.database_path)
        self.db.migrate()
        audit = AuditLog(self.db)
        self.sessions = SessionService(
            self.db,
            audit,
            {
                "claude-code": ClaudeSessionReader(settings.claude_session_root),
                "codex": CodexSessionReader(settings.codex_session_root),
            },
        )
        analyzer = analyzer or OpenAICompatibleAnalyzer(
            settings.analyzer_base_url,
            settings.analyzer_model,
            settings.analyzer_api_key,
        )
        self.analysis = AnalysisService(self.db, self.sessions, analyzer)
        sources = SourceRepository(self.db)
        evidence = EvidenceRepository(self.db)
        claims = ClaimRepository(self.db)
        store = EvidenceStore(settings.evidence_dir)
        self.ingest = IngestService(
            sources,
            evidence,
            claims,
            store,
            analyzer,
            LocalSourceAdapter(settings.local_source_root),
            WebSourceAdapter(),
        )
        self.review = ReviewService(self.db, audit)
        self.search = SearchService(self.db, store)
        self.updates = UpdateService(
            self.db, {}, interval_days=settings.update_interval_days
        )

    def session_list(self, **kwargs):
        return self.sessions.list(**kwargs)

    async def session_analyze(self, **kwargs):
        return await self.analysis.analyze_authorized_session(**kwargs)

    def session_revoke(self, client: str, session_id: str):
        return self.sessions.revoke(client, session_id, datetime.now(UTC))

    async def source_import(self, uri: str, source_type: str):
        return await self.ingest.import_source(
            ImportRequest(uri=uri, source_type=source_type)
        )

    async def source_update(self, source_id: str):
        return await self.updates.check_source(source_id, datetime.now(UTC))

    def review_list(self, status: str = "pending"):
        return self.review.list(ClaimStatus(status))

    def review_decide(self, **kwargs):
        return self.review.decide(**kwargs)

    def knowledge_search(
        self, query: str, top_k: int = 5, statuses: list[ClaimStatus] | None = None
    ):
        request = SearchQuery(query=query, top_k=top_k)
        if statuses is not None:
            request = request.model_copy(update={"statuses": statuses})
        return self.search.search(request)

    def knowledge_trace(self, claim_id: str):
        return self.search.trace(claim_id)

    def knowledge_status(self):
        with self.db.connect() as connection:
            return {
                "sources": connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                "accepted_claims": connection.execute(
                    "SELECT COUNT(*) FROM claims WHERE review_status = 'accepted'"
                ).fetchone()[0],
                "pending_reviews": connection.execute(
                    "SELECT COUNT(*) FROM review_items WHERE status = 'pending'"
                ).fetchone()[0],
                "indexed_claims": connection.execute(
                    "SELECT COUNT(*) FROM claims_fts"
                ).fetchone()[0],
                "recent_errors": connection.execute(
                    """
                    SELECT COUNT(*) FROM update_results
                    WHERE status IN ('failed', 'source_unavailable')
                    """
                ).fetchone()[0],
            }


def build_server(settings: Settings | None = None) -> MCPServer:
    return create_server(KnowledgeMapApplication(settings or Settings()))


server = build_server()
