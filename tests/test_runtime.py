"""Task continuity, admission, budget and independent execution regressions."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import BaseModel
from runtime_support import ControlledModel, clarify, compiled, context, route, run_to_end

from app.agents.types import TaskType
from app.core.errors import RuntimeRequestError
from app.graph.contracts import SupervisorOutput
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from app.runtime.context import SubmitOptions
from app.streaming.subscription import SubscriptionOwner


async def test_generic_clarification_continues_task_budget_and_new_task_resets_scope():
    model = ControlledModel([clarify(), route(), clarify(TaskType.REFUND_APPLY)])
    runtime = AgentRuntime(compiled(model), run_limits=RunLimits(10, 12))
    first, view, _ = await run_to_end(runtime, context())
    await asyncio.sleep(0.03)
    second, view2, events = await run_to_end(runtime, context(message="find my order"))
    assert first.task_id == second.task_id and first.run_id != second.run_id
    assert view2.model_call_usage.model_attempts == 2
    assert view2.run_usage.active_elapsed_ms >= view.run_usage.active_elapsed_ms
    assert view2.error["code"] == "capability_unavailable"
    assert not any(event.kind == "token" for event in events)
    with pytest.raises(RuntimeRequestError) as retry:
        await runtime.submit(context(), options=SubmitOptions())
    assert retry.value.code == "explicit_new_task_required"
    third, view3, _ = await run_to_end(runtime, context(), SubmitOptions("new_task"))
    assert third.task_id != first.task_id and view3.model_call_usage.model_attempts == 1
    assert all("find my order" not in str(message.content) for message in model.messages[-1])
    await runtime.shutdown()


async def test_specific_pending_preserved_on_unsupported_and_switch_requires_new_task():
    model = ControlledModel(
        [
            clarify(TaskType.ORDER_QUERY),
            SupervisorOutput(kind="unsupported"),
            route(TaskType.REFUND_APPLY),
            clarify(),
        ]
    )
    runtime = AgentRuntime(compiled(model), run_limits=RunLimits(10, 12))
    first, _, _ = await run_to_end(runtime, context())
    for message in ("cancel my order", "refund instead"):
        current, view, _ = await run_to_end(runtime, context(message=message))
        assert current.task_id == first.task_id and view.task_status == "needs_input"
    new, view, _ = await run_to_end(runtime, context(), SubmitOptions("new_task"))
    assert new.task_id != first.task_id and view.model_call_usage.model_attempts == 1
    await runtime.shutdown()


async def test_unsupported_and_structure_correction_have_bounded_attempts():
    class Invalid(BaseModel):
        value: str = "bad"

    model = ControlledModel([Invalid(), SupervisorOutput(kind="unsupported"), Invalid(), Invalid()])
    runtime = AgentRuntime(compiled(model), run_limits=RunLimits(10, 12))
    _, view, events = await run_to_end(runtime, context())
    assert view.task_status == "rejected" and view.model_call_usage.model_attempts == 2
    assert sum(event.kind == "token" for event in events) == 1
    _, view, events = await run_to_end(runtime, context())
    assert (
        view.error["code"] == "model_output_invalid" and view.model_call_usage.model_attempts == 2
    )
    assert sum(event.kind == "error" for event in events) == 1
    await runtime.shutdown()


async def test_continued_model_budget_exhaustion_has_no_new_attempt():
    model = ControlledModel([clarify()])
    runtime = AgentRuntime(compiled(model, attempts=1), run_limits=RunLimits(10, 12))
    first, _, _ = await run_to_end(runtime, context())
    second, view, _ = await run_to_end(runtime, context())
    assert first.task_id == second.task_id and view.error["code"] == "model_limit_exceeded"
    assert view.model_call_usage.model_attempts == 1 and model.calls == 1 and view.usage_complete
    await runtime.shutdown()


async def test_gate_capacity_dedup_and_old_owner_cleanup():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked(messages):
        entered.set()
        await release.wait()
        return clarify()

    model = ControlledModel([blocked] * 8)
    runtime = AgentRuntime(compiled(model), run_limits=RunLimits(10, 12))
    ctx = context()
    request_id = uuid4()
    owner = SubscriptionOwner()
    handle = await runtime.submit(
        ctx, options=SubmitOptions(request_id=request_id), subscription_owner=owner
    )
    await entered.wait()
    with pytest.raises(RuntimeRequestError) as conflict:
        await runtime.submit(replace(ctx, run_id=str(uuid4())), options=SubmitOptions())
    assert conflict.value.code == "thread_busy"
    with pytest.raises(RuntimeRequestError) as conflict:
        await runtime.submit(
            replace(ctx, run_id=str(uuid4())),
            options=SubmitOptions(request_id=request_id),
            subscription_owner=SubscriptionOwner(),
        )
    assert conflict.value.code == "subscription_exists"
    owner.close()
    reused = await runtime.submit(
        replace(ctx, run_id=str(uuid4())),
        options=SubmitOptions(request_id=request_id),
        subscription_owner=SubscriptionOwner(),
    )
    assert reused.run_id == handle.run_id
    owner.close()
    assert not reused.subscription.closed
    with pytest.raises(RuntimeRequestError) as conflict:
        await runtime.submit(
            replace(ctx, message="changed"), options=SubmitOptions(request_id=request_id)
        )
    assert conflict.value.code == "request_id_conflict"
    for index in range(7):
        await runtime.submit(
            context(thread=f"other-{index}", conversation=f"other-{index}"), options=SubmitOptions()
        )
    with pytest.raises(RuntimeRequestError) as full:
        await runtime.submit(context(thread="full"), options=SubmitOptions())
    assert full.value.code == "runtime_busy" and len(runtime._claims) == 8
    release.set()
    events = [event async for event in reused.subscription]
    assert events[0].data["snapshot"] is True
    assert sum(event.kind == "done" for event in events) == 1
    await runtime.shutdown()
    assert not runtime._claims and model.calls == 8


async def test_pre_admission_cancel_and_shutdown_during_state_read_release_claim():
    entered = asyncio.Event()
    release = asyncio.Event()

    class DelayedState:
        async def aget_state(self, *args):
            entered.set()
            await release.wait()
            return SimpleNamespace(values={}, next=())

    runtime = AgentRuntime(DelayedState(), run_limits=RunLimits(10, 12))
    submit = asyncio.create_task(runtime.submit(context(), options=SubmitOptions()))
    await entered.wait()
    submit.cancel()
    with pytest.raises(asyncio.CancelledError):
        await submit
    assert not runtime._claims and not runtime._records
    submit = asyncio.create_task(runtime.submit(context(), options=SubmitOptions()))
    await asyncio.sleep(0)
    await runtime.shutdown()
    release.set()
    with pytest.raises(RuntimeRequestError) as stopping:
        await submit
    assert (
        stopping.value.code == "runtime_stopping" and not runtime._claims and not runtime._records
    )


async def test_slow_subscription_releases_execution_and_terminal_snapshot_has_no_replay():
    model = ControlledModel([clarify()])
    runtime = AgentRuntime(compiled(model), run_limits=RunLimits(10, 12), queue_capacity=2)
    ctx = context()
    handle = await runtime.submit(
        ctx, options=SubmitOptions(), subscription_owner=SubscriptionOwner()
    )
    await runtime._records[handle.run_id].task
    assert handle.subscription.closed and handle.subscription.slow and not runtime._claims
    subscription = await runtime.subscribe(
        user_id=ctx.user_id,
        conversation_id=ctx.conversation_id,
        run_id=handle.run_id,
        subscription_owner=SubscriptionOwner(),
    )
    events = [event async for event in subscription]
    assert [event.kind for event in events] == ["status", "done"]
    assert events[0].data["view"]["final_answer"] == "What do you need?" and model.calls == 1
    await runtime.shutdown()


async def test_timeout_uncertain_survives_retention_and_shutdown_is_bounded():
    started = asyncio.Event()

    async def slow(messages):
        started.set()
        await asyncio.Event().wait()

    runtime = AgentRuntime(
        compiled(ControlledModel([slow])), run_limits=RunLimits(0.03, 12), result_ttl_seconds=0.01
    )
    ctx = context()
    handle, view, _ = await run_to_end(runtime, ctx)
    assert view.error["code"] == "budget_exceeded" and not view.usage_complete
    await asyncio.sleep(0.02)
    with pytest.raises(RuntimeRequestError) as missing:
        await runtime.get_run(
            user_id=ctx.user_id, conversation_id=ctx.conversation_id, run_id=handle.run_id
        )
    assert missing.value.code == "run_not_found"
    with pytest.raises(RuntimeRequestError) as uncertain:
        await runtime.submit(context(), options=SubmitOptions("new_task"))
    assert uncertain.value.code == "execution_uncertain"
    await runtime.shutdown()
    started.clear()
    runtime = AgentRuntime(
        compiled(ControlledModel([slow])), run_limits=RunLimits(10, 12), shutdown_grace_seconds=0.01
    )
    handle = await runtime.submit(context(), options=SubmitOptions())
    await started.wait()
    await asyncio.wait_for(runtime.shutdown(), 1)
    record = runtime._records[handle.run_id]
    assert record.task.done() and record.error["code"] == "run_interrupted" and not runtime._claims


async def test_commit_failure_blocks_without_replay_and_wrong_owner_not_found(monkeypatch):
    graph = compiled(ControlledModel([clarify()]))
    runtime = AgentRuntime(graph, run_limits=RunLimits(10, 12))
    original = type(graph).ainvoke

    async def failed_commit(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        raise OSError("private storage failure")

    monkeypatch.setattr(type(graph), "ainvoke", failed_commit)
    ctx = context()
    handle, view, events = await run_to_end(runtime, ctx)
    assert not view.usage_complete and view.error["code"] == "agent_execution_failed"
    assert not any(event.kind == "token" for event in events)
    with pytest.raises(RuntimeRequestError) as owner:
        await runtime.get_run(
            user_id="demo-user-b", conversation_id=ctx.conversation_id, run_id=handle.run_id
        )
    assert owner.value.code == "run_not_found"
    with pytest.raises(RuntimeRequestError) as unknown:
        await runtime.submit(context(), options=SubmitOptions("new_task"))
    assert unknown.value.code == "execution_uncertain"
    await runtime.shutdown()


async def test_seeded_tool_budget_and_active_time_do_not_reset_across_runs():
    model = ControlledModel([clarify()])
    graph = compiled(model)
    runtime = AgentRuntime(graph, run_limits=RunLimits(10, 12))
    ctx = context()
    first, _, _ = await run_to_end(runtime, ctx)
    config = {"configurable": {"thread_id": ctx.thread_id}}
    await graph.aupdate_state(config, {"run_usage": {"tool_calls": 12, "active_elapsed_ms": 999}})
    second, view, _ = await run_to_end(runtime, context())
    assert first.task_id == second.task_id and view.error["code"] == "budget_exceeded"
    assert view.run_usage.tool_calls == 12 and view.run_usage.active_elapsed_ms >= 999
    assert model.calls == 1
    await runtime.shutdown()


async def test_frozen_clock_excludes_final_checkpoint_latency():
    from langgraph.checkpoint.memory import InMemorySaver

    class SlowFinalSaver(InMemorySaver):
        delayed = 0

        async def aput(self, config, checkpoint, metadata, new_versions):
            if "run_finish" in checkpoint["versions_seen"]:
                self.delayed += 1
                await asyncio.sleep(0.3)
            return await super().aput(config, checkpoint, metadata, new_versions)

    saver = SlowFinalSaver()
    runtime = AgentRuntime(
        compiled(ControlledModel([clarify()]), saver=saver), run_limits=RunLimits(0.2, 12)
    )
    _, view, _ = await run_to_end(runtime, context())
    assert view.task_status == "needs_input" and view.usage_complete
    assert view.run_usage.active_elapsed_ms < 200 and saver.delayed > 0
    await runtime.shutdown()


async def test_run_finish_failure_converges_without_retrying_settlement(monkeypatch):
    from app.runtime.run_scope import RunScope

    def failed_finish(self):
        raise RuntimeError("controlled settlement failure")

    monkeypatch.setattr(RunScope, "finish_active_period", failed_finish)
    runtime = AgentRuntime(compiled(ControlledModel([clarify()])), run_limits=RunLimits(10, 12))
    _, view, events = await run_to_end(runtime, context())
    assert not view.usage_complete and view.error["code"] == "agent_execution_failed"
    assert sum(event.kind == "done" for event in events) == 1
    assert not any(event.kind == "token" for event in events) and not runtime._claims
    await runtime.shutdown()


async def test_state_read_failures_unfinished_snapshot_and_retention_are_explicit():
    class FailedRead:
        async def aget_state(self, *args):
            raise OSError("private snapshot error")

    runtime = AgentRuntime(FailedRead(), run_limits=RunLimits(10, 12))
    with pytest.raises(RuntimeRequestError) as failure:
        await runtime.submit(context(), options=SubmitOptions())
    assert (
        failure.value.code == "state_unavailable" and not runtime._records and not runtime._claims
    )

    class Unfinished:
        async def aget_state(self, *args):
            return SimpleNamespace(values={}, next=("supervisor",))

    runtime = AgentRuntime(Unfinished(), run_limits=RunLimits(10, 12))
    with pytest.raises(RuntimeRequestError) as failure:
        await runtime.submit(context(), options=SubmitOptions())
    assert failure.value.code == "execution_uncertain"
    model = ControlledModel([SupervisorOutput(kind="unsupported")] * 4)
    runtime = AgentRuntime(compiled(model), run_limits=RunLimits(10, 12), retained_runs=2)
    request_id = uuid4()
    first, view, _ = await run_to_end(runtime, context(), SubmitOptions(request_id=request_id))
    await run_to_end(runtime, context())
    await run_to_end(runtime, context())
    assert len(runtime._records) == 2
    assert view.task_id == first.task_id
    replay, _, _ = await run_to_end(runtime, context(), SubmitOptions(request_id=request_id))
    assert replay.run_id != first.run_id and model.calls == 4
    await runtime.shutdown()


async def test_specific_clarification_fills_entities_without_changing_task_goal():
    model = ControlledModel(
        [
            clarify(TaskType.ORDER_QUERY),
            route(
                TaskType.ORDER_QUERY,
                task_goal="Changed model suggestion",
                entities={"order_id": "order-1", "user_id": "injected"},
            ),
        ]
    )
    runtime = AgentRuntime(compiled(model), run_limits=RunLimits(10, 12))
    ctx = context()
    first, _, _ = await run_to_end(runtime, ctx)
    second, view, _ = await run_to_end(runtime, context(message="order-1"))
    snapshot = await runtime._graph.aget_state({"configurable": {"thread_id": ctx.thread_id}})
    assert first.task_id == second.task_id
    assert snapshot.values["task_goal"] == "Find requested facts"
    assert snapshot.values["route_decision"].entities == {"order_id": "order-1"}
    assert (
        view.model_call_usage.model_attempts == 2 and view.error["code"] == "capability_unavailable"
    )
    await runtime.shutdown()
