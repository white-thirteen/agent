import asyncio
from types import SimpleNamespace

import pytest

from app.context.maintenance import ContextMaintenance


@pytest.mark.asyncio
async def test_shutdown_cancels_workers_and_rejects_new_work():
    maintenance = ContextMaintenance(None, None, None, None, SimpleNamespace(runtime_max_active_runs=1))
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def running():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    task = asyncio.create_task(running())
    maintenance.tasks.add(task)
    task.add_done_callback(maintenance.tasks.discard)
    await started.wait()
    await maintenance.shutdown()
    assert stopped.is_set() and not maintenance.tasks
    maintenance.schedule("work", "thread")
    assert not maintenance.tasks
