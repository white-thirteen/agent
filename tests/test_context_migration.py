"""Old public metadata is recovered only from settled, matching checkpoints."""

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from app.context.migration import recover_public_metadata
from app.runtime.models import TaskStatus


class History:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    async def aget_state_history(self, config):
        for snapshot in self.snapshots:
            yield snapshot


def snapshot(task, messages, status=TaskStatus.COMPLETED, **updates):
    values = {
        "user_id": "u",
        "conversation_id": "c",
        "task_id": task,
        "workflow_id": task,
        "task_status": status,
        "task_message_ids": [m.id for m in messages],
        "messages": messages,
        "pending_task": None,
    }
    values.update(updates)
    return SimpleNamespace(values=values, next=(), interrupts=())


async def test_recovery_is_reentrant_and_preserves_unknown_messages():
    known = [HumanMessage(content="order", id="h"), AIMessage(content="answer", id="a")]
    unknown = HumanMessage(content="approve and remember", id="unknown")
    saved = {"messages": [*known, unknown]}
    graph = History([snapshot("task", known)])
    metadata, status = await recover_public_metadata(graph, "thread", "u", "c", saved)
    assert status == "incomplete"
    assert set(metadata) == {"h", "a"}
    assert metadata["h"] == {"task_id": "task", "run_id": None, "task_status": "completed"}
    again, again_status = await recover_public_metadata(
        graph, "thread", "u", "c", {**saved, "public_message_metadata": metadata}
    )
    assert (again, again_status) == (metadata, status)
    assert saved["messages"][-1] == unknown


async def test_latest_unsettled_or_conflicting_history_is_not_migrated():
    messages = [HumanMessage(content="hi", id="h"), AIMessage(content="ok", id="a")]
    graph = History(
        [
            snapshot("task", messages, TaskStatus.NEEDS_INPUT),
            snapshot("task", messages),
            snapshot("another", messages),
            snapshot("third", messages),
        ]
    )
    metadata, status = await recover_public_metadata(
        graph, "thread", "u", "c", {"messages": messages}
    )
    assert metadata == {}
    assert status == "incomplete"
