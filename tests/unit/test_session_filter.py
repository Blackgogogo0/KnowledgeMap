from knowledgemap.session_intelligence.filter import normalize_events, redact_excerpt
from knowledgemap.sessions.base import SessionMessage


def test_normalize_collapses_repeated_confirmations_but_keeps_failures():
    messages = [
        SessionMessage(role="user", text="确认"),
        SessionMessage(role="user", text="ok"),
        SessionMessage(role="assistant", text="Dependency install failed: permission denied"),
        SessionMessage(role="user", text="Use official SDK documentation for the decision"),
    ]
    events = normalize_events(messages)
    assert [event.message_id for event in events] == ["m1", "m3", "m4"]
    assert "permission denied" in events[1].text


def test_normalize_can_start_after_stable_message_id():
    messages = [
        SessionMessage(role="user", text="first task"),
        SessionMessage(role="assistant", text="decision made"),
        SessionMessage(role="user", text="new evidence"),
    ]
    assert [e.message_id for e in normalize_events(messages, after_message_id="m2")] == ["m3"]


def test_redact_excerpt_masks_secrets_and_bounds_length():
    text = "Authorization: Bearer secret-token password=hunter2 " + "x" * 600
    result = redact_excerpt(text)
    assert "secret-token" not in result
    assert "hunter2" not in result
    assert result.count("[REDACTED]") == 2
    assert len(result) == 500

