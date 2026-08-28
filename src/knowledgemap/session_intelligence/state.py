from knowledgemap.errors import KnowledgeMapError
from knowledgemap.session_intelligence.models import TaskStateDelta, TaskStateSnapshot


def merge_state(
    previous: TaskStateSnapshot | None, deltas: list[TaskStateDelta]
) -> TaskStateSnapshot:
    if not deltas:
        if previous is None:
            raise KnowledgeMapError("STATE_EMPTY", "No previous state or state delta exists.")
        return previous.model_copy(deep=True)

    episode_id = deltas[0].episode_id
    if any(delta.episode_id != episode_id for delta in deltas):
        raise KnowledgeMapError("STATE_CONFLICT", "A state merge may contain one episode only.")
    if previous is None or previous.episode_id != episode_id:
        state = TaskStateSnapshot(episode_id=episode_id)
    else:
        state = previous.model_copy(deep=True)

    for delta in deltas:
        values: list[str] = getattr(state, delta.field.value)
        if delta.operation == "add":
            if delta.value not in values:
                values.append(delta.value)
            continue
        target = delta.previous_value or delta.value
        if target not in values:
            raise KnowledgeMapError(
                "STATE_CONFLICT",
                f"Cannot {delta.operation} unknown {delta.field.value} value.",
            )
        index = values.index(target)
        if delta.operation == "replace":
            values[index] = delta.value
        else:
            values.pop(index)
    return state

