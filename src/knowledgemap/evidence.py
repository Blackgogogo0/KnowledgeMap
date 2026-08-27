from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from knowledgemap.errors import KnowledgeMapError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StoredBlob:
    content_hash: str
    relative_path: str
    size: int


class EvidenceStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def put(self, data: bytes) -> StoredBlob:
        content_hash = sha256(data).hexdigest()
        relative_path = f"{content_hash[:2]}/{content_hash}"
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as stream:
                stream.write(data)
        except FileExistsError:
            existing = target.read_bytes()
            if sha256(existing).hexdigest() != content_hash:
                raise KnowledgeMapError(
                    "EVIDENCE_INTEGRITY_ERROR",
                    "Existing evidence blob does not match its content hash.",
                )
        return StoredBlob(content_hash, relative_path, len(data))

    def read(self, content_hash: str) -> bytes:
        if not _SHA256.fullmatch(content_hash):
            raise KnowledgeMapError(
                "INVALID_CONTENT_HASH", "Evidence hashes must be 64 lowercase hex characters."
            )
        target = self.root / content_hash[:2] / content_hash
        try:
            data = target.read_bytes()
        except FileNotFoundError as error:
            raise KnowledgeMapError(
                "EVIDENCE_NOT_FOUND", f"Evidence blob {content_hash} was not found."
            ) from error
        if sha256(data).hexdigest() != content_hash:
            raise KnowledgeMapError(
                "EVIDENCE_INTEGRITY_ERROR", "Evidence blob failed SHA-256 verification."
            )
        return data
