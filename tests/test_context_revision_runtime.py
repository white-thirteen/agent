"""Normal admission cannot publish or switch context while a Task needs input."""

from types import SimpleNamespace

import pytest
from runtime_support import ControlledModel, clarify, compiled, context, run_to_end

from app.core.errors import RuntimeRequestError
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from app.runtime.context import SubmitOptions
from app.runtime.models import TaskStatus


async def test_input_wait_and_new_task_do_not_select_candidate():
    class Repository:
        async def candidate_revision(self, *args):
            raise AssertionError("input-waiting history cannot be adopted")

    runtime = AgentRuntime(
        compiled(ControlledModel([clarify(), clarify(), clarify()])),
        run_limits=RunLimits(10, 12),
        context_manager=SimpleNamespace(repository=Repository()),
    )
    try:
        first, _, _ = await run_to_end(runtime, context())
        await runtime._records[first.run_id].task
        second, _, _ = await run_to_end(runtime, context())
        await runtime._records[second.run_id].task
        third, _, _ = await run_to_end(runtime, context(), SubmitOptions("new_task"))
        await runtime._records[third.run_id].task
        assert first.task_id == second.task_id and third.task_id != first.task_id
    finally:
        await runtime.shutdown()


async def test_uncertain_blocked_and_shutdown_do_not_prepare_candidates():
    class Repository:
        async def candidate_revision(self, *args):
            raise AssertionError("blocked sessions cannot select a candidate")

    runtime = AgentRuntime(
        compiled(ControlledModel([])),
        run_limits=RunLimits(10, 12),
        context_manager=SimpleNamespace(repository=Repository()),
    )
    for status in (TaskStatus.WAITING_APPROVAL, TaskStatus.PAUSED):
        with pytest.raises(RuntimeRequestError) as error:
            runtime._input_mode({"task_status": status}, SubmitOptions("new_task"))
        assert error.value.code == "task_blocked"
    runtime._uncertain.add("thread")
    with pytest.raises(RuntimeRequestError) as error:
        await runtime.submit(context(), options=SubmitOptions())
    assert error.value.code == "execution_uncertain"
    await runtime.shutdown()
    with pytest.raises(RuntimeRequestError) as error:
        await runtime.submit(context(), options=SubmitOptions())
    assert error.value.code == "runtime_stopping"


async def test_unconfigured_model_limits_keep_v1_input_without_history():
    from app.core.config import Settings
    from app.graph.contracts import SupervisorOutput

    provider = ControlledModel([SupervisorOutput(kind="unsupported")] * 2)
    runtime = AgentRuntime(
        compiled(provider),
        run_limits=RunLimits(10, 12),
        context_settings=Settings(
            _env_file=None, context_model_window_tokens=None, context_model_output_tokens=None
        ),
    )
    try:
        first, _, _ = await run_to_end(runtime, context(message="older request"))
        await runtime._records[first.run_id].task
        second, view, _ = await run_to_end(runtime, context(message="current request"))
        await runtime._records[second.run_id].task
        assert view.task_status == "rejected"
        assert [m.content for m in provider.messages[1][1:]] == ["current request"]
    finally:
        await runtime.shutdown()
