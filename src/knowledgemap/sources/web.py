import ipaddress
import socket
from collections.abc import Callable
from hashlib import sha256
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sources.base import FetchedSource


Resolver = Callable[[str], list[str]]


def _resolve(host: str) -> list[str]:
    return list({item[4][0] for item in socket.getaddrinfo(host, None)})


class WebSourceAdapter:
    def __init__(
        self,
        resolver: Resolver | None = None,
        max_bytes: int = 10 * 1024 * 1024,
        max_redirects: int = 5,
        timeout: float = 20.0,
    ):
        self.resolver = resolver or _resolve
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.timeout = httpx.Timeout(timeout, connect=min(timeout, 10.0))

    async def fetch(self, uri: str) -> FetchedSource:
        current = uri
        redirects: list[str] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            for _ in range(self.max_redirects + 1):
                self._validate_url(current)
                response = await client.get(current)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location or len(redirects) >= self.max_redirects:
                        raise KnowledgeMapError(
                            "SOURCE_REDIRECT_LIMIT", "Web source exceeded redirect limit."
                        )
                    current = urljoin(current, location)
                    redirects.append(current)
                    continue
                response.raise_for_status()
                raw = response.content
                if len(raw) > self.max_bytes:
                    raise KnowledgeMapError(
                        "SOURCE_TOO_LARGE", "Source exceeds the configured byte limit."
                    )
                media_type = response.headers.get("content-type", "text/html").split(";", 1)[0]
                if media_type == "application/pdf":
                    raise KnowledgeMapError(
                        "UNSUPPORTED_VISUAL_DOCUMENT",
                        "PDF and visual document ingestion is not supported in phase 1.",
                    )
                if media_type not in {"text/html", "text/plain", "text/markdown"}:
                    raise KnowledgeMapError(
                        "UNSUPPORTED_SOURCE_FORMAT", "Web source must be HTML or UTF-8 text."
                    )
                try:
                    decoded = raw.decode(response.encoding or "utf-8")
                except UnicodeDecodeError as error:
                    raise KnowledgeMapError("SOURCE_NOT_UTF8", "Web source must be UTF-8 text.") from error
                text = trafilatura.extract(decoded) if media_type == "text/html" else decoded
                if not text:
                    raise KnowledgeMapError("SOURCE_TEXT_EMPTY", "No extractable text was found.")
                digest = sha256(raw).hexdigest()
                return FetchedSource(
                    canonical_uri=str(response.url),
                    raw=raw,
                    text=text,
                    media_type=media_type,
                    version=response.headers.get("etag") or digest,
                    retrieval={
                        "kind": "web",
                        "redirects": redirects,
                        "etag": response.headers.get("etag"),
                        "last_modified": response.headers.get("last-modified"),
                    },
                )
        raise KnowledgeMapError("SOURCE_REDIRECT_LIMIT", "Web source exceeded redirect limit.")

    def _validate_url(self, uri: str) -> None:
        parsed = urlsplit(uri)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise KnowledgeMapError("SOURCE_URL_INVALID", "Only HTTP(S) source URLs are supported.")
        try:
            addresses = self.resolver(parsed.hostname)
        except OSError as error:
            raise KnowledgeMapError("SOURCE_DNS_FAILED", "Web source hostname could not be resolved.") from error
        if not addresses:
            raise KnowledgeMapError("SOURCE_DNS_FAILED", "Web source hostname resolved to no addresses.")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise KnowledgeMapError(
                    "SOURCE_NETWORK_NOT_ALLOWED",
                    "Web sources may not resolve to private or local networks.",
                )
