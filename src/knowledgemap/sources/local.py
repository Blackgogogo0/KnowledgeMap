from hashlib import sha256
from pathlib import Path

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sources.base import FetchedSource


class LocalSourceAdapter:
    def __init__(self, allowed_root: Path, max_bytes: int = 10 * 1024 * 1024):
        self.allowed_root = Path(allowed_root).resolve()
        self.max_bytes = max_bytes

    def fetch(self, path: str | Path) -> FetchedSource:
        requested = Path(path)
        try:
            resolved = requested.resolve(strict=True)
        except FileNotFoundError as error:
            raise KnowledgeMapError("SOURCE_NOT_FOUND", "Local source was not found.") from error
        if not resolved.is_relative_to(self.allowed_root):
            raise KnowledgeMapError(
                "SOURCE_PATH_NOT_ALLOWED", "Local source is outside the allowed root."
            )
        if resolved.suffix.lower() == ".pdf":
            raise KnowledgeMapError(
                "UNSUPPORTED_VISUAL_DOCUMENT",
                "PDF and visual document ingestion is not supported in phase 1.",
            )
        media_types = {
            ".md": "text/markdown",
            ".markdown": "text/markdown",
            ".txt": "text/plain",
        }
        try:
            media_type = media_types[resolved.suffix.lower()]
        except KeyError as error:
            raise KnowledgeMapError(
                "UNSUPPORTED_SOURCE_FORMAT", "Only UTF-8 Markdown and plain text are supported."
            ) from error
        if resolved.stat().st_size > self.max_bytes:
            raise KnowledgeMapError("SOURCE_TOO_LARGE", "Source exceeds the configured byte limit.")
        raw = resolved.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise KnowledgeMapError("SOURCE_NOT_UTF8", "Local source must be UTF-8 text.") from error
        digest = sha256(raw).hexdigest()
        return FetchedSource(
            canonical_uri=resolved.as_uri(),
            raw=raw,
            text=text,
            media_type=media_type,
            version=digest,
            retrieval={"kind": "local", "path": str(resolved)},
        )
