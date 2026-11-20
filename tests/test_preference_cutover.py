from types import SimpleNamespace

import pytest

from app.agents.types import TaskType
from app.domain.refunds import canonical_digest
from app.graph.contracts import NewSupervisorOutput
from app.main import legacy_memory_cutover_safe
from app.memory.models import MemoryCommand
from app.runtime.context import DemoIdentity
from app.runtime.models import TaskStatus
from app.services.preference_service import PreferenceService
from app.tools.models import ToolNotStartedError


class Connection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def execute(self, sql):
        return self

    async def fetchall(self):
        return [("user", "session", "thread")]


class Pool:
    def connection(self):
        return Connection()


class History:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    async def aget_state_history(self, config):
        for snapshot in self.snapshots:
            yield snapshot


def snapshot(task_id, task_type, status, *, pending=None, next_nodes=()):
    return SimpleNamespace(
        values={
            "user_id": "user",
            "conversation_id": "session",
            "task_id": task_id,
            "task_type": task_type,
            "task_status": status,
            "pending_task": pending,
        },
        next=next_nodes,
    )


@pytest.mark.asyncio
async def test_older_unknown_memory_blocks_cutover_even_after_new_task():
    history = History(
        [
            snapshot("new", TaskType.ORDER_QUERY, TaskStatus.COMPLETED),
            snapshot("old", TaskType.MEMORY_MANAGE, TaskStatus.FAILED),
        ]
    )
    assert not await legacy_memory_cutover_safe(history, Pool())
    history.snapshots[1] = snapshot("old", TaskType.MEMORY_MANAGE, TaskStatus.COMPLETED)
    assert await legacy_memory_cutover_safe(history, Pool())


@pytest.mark.asyncio
async def test_initial_input_snapshot_requires_a_later_identified_task():
    initial = SimpleNamespace(
        values={"messages": []},
        next=("supervisor",),
        metadata={"source": "input", "step": -1},
    )
    history = History([snapshot("new", TaskType.ORDER_QUERY, TaskStatus.COMPLETED), initial])
    assert await legacy_memory_cutover_safe(history, Pool())
    history.snapshots = [initial]
    assert not await legacy_memory_cutover_safe(history, Pool())
    history.snapshots = [snapshot("old", TaskType.MEMORY_MANAGE, TaskStatus.FAILED), initial]
    assert not await legacy_memory_cutover_safe(history, Pool())


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [TaskStatus.RUNNING, TaskStatus.NEEDS_INPUT, TaskStatus.FAILED])
async def test_unsettled_legacy_memory_prevents_cutover(status):
    history = History([snapshot("old", TaskType.MEMORY_MANAGE, status)])
    assert not await legacy_memory_cutover_safe(history, Pool())


def test_public_route_schema_excludes_memory():
    schema = NewSupervisorOutput.model_json_schema()
    assert "memory_manage" not in str(schema)


@pytest.mark.asyncio
async def test_proven_not_started_does_not_erase_old_uncertainty():
    class Executor:
        async def execute_preference_control(self, *args, **kwargs):
            raise ToolNotStartedError("not started")

    service = PreferenceService(None, Executor(), user_ids=["user"])
    identity = DemoIdentity("user", frozenset({"memory:write"}))
    command = MemoryCommand(operation="upsert", field="answer_language", value="en")
    values = command.model_dump(mode="json")
    state = ["PREPARED"]
    saves = []

    async def get(*args):
        return ("command", canonical_digest(values), values, 0, state[0], None)

    async def save(user, operation, status, result):
        saves.append(status)
        state[0] = status

    service._get = get
    service._save = save
    with pytest.raises(ToolNotStartedError):
        await service.mutate(identity, "operation", 0, command)
    assert saves == ["EXECUTING", "PREPARED"]
    state[0] = "UNKNOWN"
    saves.clear()
    with pytest.raises(ToolNotStartedError):
        await service.status(identity, "operation")
    assert saves == [] and state[0] == "UNKNOWN"
