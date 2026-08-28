import pytest

from knowledgemap.errors import KnowledgeMapError
from knowledgemap.session_intelligence.models import (
    EvidencePointer,
    StateField,
    TaskStateDelta,
    TaskStateSnapshot,
)
from knowledgemap.session_intelligence.state import merge_state


def delta(operation, value, previous_value=None, field=StateField.OBJECTIVE):
    return TaskStateDelta(
        episode_id="e1",
        field=field,
        operation=operation,
        value=value,
        previous_value=previous_value,
        evidence=[EvidencePointer(message_id="m1", excerpt="evidence")],
    )


def test_merge_add_replace_remove_without_mutating_previous():
    previous = TaskStateSnapshot(episode_id="e1", objective=["Old goal"])
    result = merge_state(
        previous,
        [
            delta("replace", "New goal", previous_value="Old goal"),
            delta("add", "Ship safely", field=StateField.CONSTRAINTS),
        ],
    )
    assert previous.objective == ["Old goal"]
    assert result.objective == ["New goal"]
    assert result.constraints == ["Ship safely"]


def test_replace_unknown_value_is_rejected():
    with pytest.raises(KnowledgeMapError, match="STATE_CONFLICT"):
        merge_state(
            TaskStateSnapshot(episode_id="e1", objective=["Known"]),
            [delta("replace", "New", previous_value="Unknown")],
        )


def test_new_episode_starts_empty_snapshot():
    previous = TaskStateSnapshot(episode_id="old", objective=["Old task"])
    result = merge_state(previous, [delta("add", "New task")])
    assert result.episode_id == "e1"
    assert result.objective == ["New task"]

