import pytest

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.evidence import EvidenceStore


def test_same_content_reuses_blob_and_never_overwrites(tmp_path):
    store = EvidenceStore(tmp_path)

    first = store.put(b"alpha")
    second = store.put(b"alpha")

    assert first.content_hash == second.content_hash
    assert first.relative_path == second.relative_path
    assert store.read(first.content_hash) == b"alpha"


def test_read_rejects_blob_whose_content_no_longer_matches_hash(tmp_path):
    store = EvidenceStore(tmp_path)
    stored = store.put(b"alpha")
    (tmp_path / stored.relative_path).write_bytes(b"tampered")

    with pytest.raises(KnowledgeMapError, match="EVIDENCE_INTEGRITY_ERROR"):
        store.read(stored.content_hash)


def test_read_rejects_invalid_hash_path(tmp_path):
    store = EvidenceStore(tmp_path)

    with pytest.raises(KnowledgeMapError, match="INVALID_CONTENT_HASH"):
        store.read("../../secret")
