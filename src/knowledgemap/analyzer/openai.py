import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from knowledgemap.analyzer.base import (
    ClaimDraft,
    ExtractableDocument,
    NeedAnalysisDraft,
    RouteAnalysisDraft,
    SessionAnalysisDraft,
    StateExtractionDraft,
    _ClaimDraftList,
)
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sessions.base import SessionMessage
from knowledgemap.session_intelligence.models import (
    AnalysisEvent,
    GapRouteDecision,
    TaskStateSnapshot,
)


OutputModel = TypeVar("OutputModel", bound=BaseModel)


class OpenAICompatibleAnalyzer:
    provider_mode = "local_ollama"
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_attempts: int = 2,
    ):
        normalized = base_url.rstrip("/")
        if normalized.endswith("/v1"):
            normalized = normalized[:-3]
        self.endpoint = f"{normalized}/api/chat"
        self.model = model
        self.api_key = api_key or "local"
        self.timeout = httpx.Timeout(timeout, connect=min(timeout, 10.0))
        self.max_attempts = max(1, max_attempts)
        self.trust_env = False

    async def extract_state(
        self, events: list[AnalysisEvent], previous_state: TaskStateSnapshot | None
    ) -> StateExtractionDraft:
        prompt = (
            "Task state extraction. Return only evidence-backed state deltas and "
            "unresolved item IDs. Put inferences under assumptions, never known facts.\n"
            f"Previous state: {previous_state.model_dump_json() if previous_state else 'null'}\n"
            "Incremental events:\n"
            + "\n".join(event.model_dump_json() for event in events)
        )
        return await self._request(prompt, StateExtractionDraft)

    async def route_gaps(self, state: TaskStateSnapshot) -> RouteAnalysisDraft:
        prompt = (
            "Route each unresolved item exactly once to ask_user, search_knowledge_map, "
            "check_freshness, inspect_local, execute_or_test, or ignore. A failure alone "
            "is not a knowledge gap. Return evidence-backed routes.\nTask state:\n"
            + state.model_dump_json()
        )
        return await self._request(prompt, RouteAnalysisDraft)

    async def compose_needs(
        self, state: TaskStateSnapshot, routes: list[GapRouteDecision]
    ) -> NeedAnalysisDraft:
        prompt = (
            "Compose at most five independently searchable Knowledge Needs only for "
            "search_knowledge_map or check_freshness routes. Each need must state the "
            "decision it changes and why current evidence is insufficient.\nState:\n"
            + state.model_dump_json()
            + "\nRoutes:\n"
            + "\n".join(route.model_dump_json() for route in routes)
        )
        return await self._request(prompt, NeedAnalysisDraft)

    async def analyze_session(
        self, messages: list[SessionMessage]
    ) -> SessionAnalysisDraft:
        transcript = "\n".join(f"{item.role}: {item.text}" for item in messages)
        prompt = (
            "Analyze the authorized session. Return the session goal, knowledge "
            "already present, and a minimal list of decision-relevant knowledge "
            "questions. For each question explain why it is needed and name "
            "preferred authoritative source types.\n\nSession:\n" + transcript
        )
        return await self._request(prompt, SessionAnalysisDraft)

    async def extract_claims(
        self, document: ExtractableDocument
    ) -> list[ClaimDraft]:
        prompt = (
            "Extract only evidence-supported claims from this document. Every claim "
            "must use the supplied evidence_id and include a precise text locator. "
            f"evidence_id: {document.evidence_id}\nmedia_type: {document.media_type}"
            f"\n\nDocument:\n{document.text}"
        )
        result = await self._request(prompt, _ClaimDraftList)
        return result.claims

    async def _request(self, prompt: str, output_type: type[OutputModel]) -> OutputModel:
        constrained_prompt = (
            prompt
            + "\nReturn JSON only. It must validate against this JSON Schema:\n"
            + json.dumps(output_type.model_json_schema(), separators=(",", ":"))
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": constrained_prompt}],
            "format": "json",
            "think": False,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 1024},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_error: Exception | None = None
        async with httpx.AsyncClient(
            timeout=self.timeout, trust_env=self.trust_env
        ) as client:
            for attempt in range(self.max_attempts):
                try:
                    response = await client.post(
                        self.endpoint, json=payload, headers=headers
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        response.raise_for_status()
                    if response.is_error:
                        raise KnowledgeMapError(
                            "ANALYZER_REQUEST_FAILED",
                            f"Analyzer returned HTTP {response.status_code}.",
                        )
                    return self._parse_response(response, output_type)
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
                    last_error = error
                    if attempt + 1 == self.max_attempts:
                        break
        raise KnowledgeMapError(
            "ANALYZER_UNAVAILABLE",
            "Analyzer did not respond after bounded retries.",
        ) from last_error

    @staticmethod
    def _parse_response(
        response: httpx.Response, output_type: type[OutputModel]
    ) -> OutputModel:
        try:
            envelope = response.json()
            content = envelope["message"]["content"]
            if isinstance(content, dict):
                data = content
            else:
                data = json.loads(content)
            return output_type.model_validate(data)
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as error:
            raise KnowledgeMapError(
                "ANALYZER_INVALID_OUTPUT",
                "Analyzer output did not match the required JSON schema.",
            ) from error
