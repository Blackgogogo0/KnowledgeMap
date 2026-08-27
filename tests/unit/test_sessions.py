from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from knowledgemap.audit import AuditLog
from knowledgemap.db import Database
from knowledgemap.errors import KnowledgeMapError
from knowledgemap.sessions.claude import ClaudeSessionReader
from knowledgemap.sessions.codex import CodexSessionReader
from knowledgemap.sessions.service import SessionService


FIXTURES = Path(__file__).parents[1] / "fixtures" / "sessions"
NOW = datetime(2026, 8, 27, 10, 0, tzinfo=UTC)


def make_service(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    readers = {
        "claude-code": ClaudeSessionReader(FIXTURES / "claude"),
        "codex": CodexSessionReader(FIXTURES / "codex"),
    }
    return SessionService(db, AuditLog(db), readers)


def test_claude_list_does_not_parse_message_body(monkeypatch):
    reader = ClaudeSessionReader(FIXTURES / "claude")
    monkeypatch.setattr(reader, "_parse_messages", Mock(side_effect=AssertionError))

    rows = reader.list_metadata(project=None, since=None)

    assert [(row.client, row.session_id, row.project) for row in rows] == [
        ("claude-code", "session-claude", "/workspace/project-a")
    ]


def test_codex_list_reads_session_metadata(tmp_path):
    reader = CodexSessionReader(FIXTURES / "codex")

    rows = reader.list_metadata(project="project-b", since=None)

    assert len(rows) == 1
    assert rows[0].session_id == "session-codex"
    assert rows[0].project == "/workspace/project-b"


def test_adapters_normalize_only_user_and_assistant_text():
    claude = ClaudeSessionReader(FIXTURES / "claude").read_messages("session-claude")
    codex = CodexSessionReader(FIXTURES / "codex").read_messages("session-codex")

    assert [(m.role, m.text) for m in claude] == [
        ("user", "Explain OAuth evidence requirements."),
        ("assistant", "Use a stable source pointer."),
    ]
    assert [(m.role, m.text) for m in codex] == [
        ("user", "Find versioned documentation."),
        ("assistant", "Use the release documentation."),
    ]


def test_read_requires_active_grant(tmp_path):
    service = make_service(tmp_path)

    with pytest.raises(KnowledgeMapError, match="SESSION_NOT_AUTHORIZED"):
        service.read("codex", "session-codex")


def test_grant_requires_explicit_confirmation_and_revoke_blocks_future_reads(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(KnowledgeMapError, match="SESSION_CONFIRMATION_REQUIRED"):
        service.grant_and_read("codex", "session-codex", confirm_read=False, now=NOW)

    granted = service.grant_and_read(
        "codex", "session-codex", confirm_read=True, now=NOW
    )
    assert granted.grant.content_hash
    assert service.read("codex", "session-codex").messages == granted.messages

    revoked = service.revoke("codex", "session-codex", now=NOW)
    assert revoked.revoked_at == NOW
    with pytest.raises(KnowledgeMapError, match="SESSION_NOT_AUTHORIZED"):
        service.read("codex", "session-codex")


def test_reader_rejects_session_id_path_traversal():
    reader = CodexSessionReader(FIXTURES / "codex")

    with pytest.raises(KnowledgeMapError, match="SESSION_NOT_FOUND"):
        reader.read_messages("../../secret")
