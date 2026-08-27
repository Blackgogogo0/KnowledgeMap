import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from knowledgemap.analyzer.base import (
    ClaimDraft,
    ExtractableDocument,
    SessionAnalysisDraft,
    _ClaimDraftList,
)
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sessions.base import SessionMessage


OutputModel = TypeVar("OutputModel", bound=BaseModel)


class OpenAICompatibleAnalyzer:
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
        self.endpoint = f"{normalized}/v1/chat/completions"
        self.model = model
        self.api_key = api_key or "local"
        self.timeout = httpx.Timeout(timeout, connect=min(timeout, 10.0))
        self.max_attempts = max(1, max_attempts)

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
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
            content = envelope["choices"][0]["message"]["content"]
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
