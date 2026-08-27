import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sessions.base import SessionMessage, SessionMetadata


class CodexSessionReader:
    client: Literal["codex"] = "codex"

    def __init__(self, root: Path, max_session_bytes: int = 20_000_000):
        self.root = Path(root)
        self.max_session_bytes = max_session_bytes

    def list_metadata(
        self, project: str | None, since: datetime | None
    ) -> list[SessionMetadata]:
        rows: list[SessionMetadata] = []
        for path in sorted(self.root.glob("**/*.jsonl")):
            metadata = self._metadata(path)
            if metadata is None:
                continue
            if project and project not in (metadata.project or ""):
                continue
            if since and metadata.timestamp and metadata.timestamp < since:
                continue
            rows.append(metadata)
        return rows

    def read_messages(self, session_id: str) -> list[SessionMessage]:
        return self._parse_messages(self._find(session_id))

    def read_raw(self, session_id: str) -> bytes:
        path = self._find(session_id)
        if path.stat().st_size > self.max_session_bytes:
            raise KnowledgeMapError("SESSION_TOO_LARGE", "Session exceeds the configured limit.")
        return path.read_bytes()

    def _find(self, session_id: str) -> Path:
        if not session_id or any(char in session_id for char in ("/", "\\")):
            raise KnowledgeMapError("SESSION_NOT_FOUND", "Session was not found.")
        for metadata in self.list_metadata(project=None, since=None):
            if metadata.session_id == session_id:
                return metadata.path
        raise KnowledgeMapError("SESSION_NOT_FOUND", "Session was not found.")

    def _metadata(self, path: Path) -> SessionMetadata | None:
        first = self._first_json(path)
        if first.get("type") != "session_meta":
            return None
        payload = first.get("payload", {})
        session_id = payload.get("session_id") or payload.get("id")
        if not session_id:
            return None
        return SessionMetadata(
            client=self.client,
            session_id=str(session_id),
            project=payload.get("cwd"),
            timestamp=_datetime(first.get("timestamp") or payload.get("timestamp")),
            path=path,
        )

    @staticmethod
    def _first_json(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {}

    def _parse_messages(self, path: Path) -> list[SessionMessage]:
        messages: list[SessionMessage] = []
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "response_item":
                    continue
                payload = record.get("payload", {})
                role = payload.get("role")
                if payload.get("type") != "message" or role not in ("user", "assistant"):
                    continue
                text = _codex_text(payload.get("content"))
                if text:
                    messages.append(SessionMessage(role=role, text=text))
        return messages


def _codex_text(content: object) -> str:
    if not isinstance(content, list):
        return ""
    allowed = {"input_text", "output_text", "text"}
    parts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") in allowed
    ]
    return "\n".join(part for part in parts if part)


def _datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
