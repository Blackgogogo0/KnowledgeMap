from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel


class SessionMetadata(BaseModel):
    client: Literal["claude-code", "codex"]
    session_id: str
    project: str | None
    timestamp: datetime | None
    path: Path


class SessionMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class SessionReader(Protocol):
    client: Literal["claude-code", "codex"]

    def list_metadata(
        self, project: str | None, since: datetime | None
    ) -> list[SessionMetadata]: ...

    def read_messages(self, session_id: str) -> list[SessionMessage]: ...

    def read_raw(self, session_id: str) -> bytes: ...
