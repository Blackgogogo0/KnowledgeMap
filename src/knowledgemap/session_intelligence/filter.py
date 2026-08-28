import re

from knowledgemap.session_intelligence.models import AnalysisEvent
from knowledgemap.sessions.base import SessionMessage


_CONFIRMATIONS = {"ok", "okay", "确认", "同意", "继续", "批准", "好的"}
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)\S+"),
    re.compile(r"(?i)(password\s*=\s*)[^\s]+"),
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.S),
)


def redact_excerpt(text: str, max_chars: int = 500) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS:
        if "PRIVATE KEY" in pattern.pattern:
            redacted = pattern.sub("[REDACTED]", redacted)
        else:
            redacted = pattern.sub(lambda match: match.group(1) + "[REDACTED]", redacted)
    return redacted[:max_chars]


def normalize_events(
    messages: list[SessionMessage], after_message_id: str | None = None
) -> list[AnalysisEvent]:
    start = 0
    if after_message_id and after_message_id.startswith("m"):
        try:
            start = int(after_message_id[1:])
        except ValueError:
            start = 0
    events: list[AnalysisEvent] = []
    previous_was_confirmation = False
    for index, message in enumerate(messages, start=1):
        if index <= start:
            continue
        text = message.text.strip()
        if not text:
            continue
        is_confirmation = text.casefold() in _CONFIRMATIONS
        if is_confirmation and previous_was_confirmation:
            continue
        events.append(
            AnalysisEvent(
                message_id=f"m{index}",
                role=message.role,
                text=redact_excerpt(text),
            )
        )
        previous_was_confirmation = is_confirmation
    return events

