"""Classifier refuses unknown and mismatched refund checkpoint shapes."""

from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

from langchain_core.messages import AIMessage
from langgraph.types import Interrupt, PregelTask, StateSnapshot

from app.agents.types import AgentType, TaskType
from app.domain.refunds import canonical_digest
from app.graph.contracts import ExecutionContext, SpecialistInput, SpecialistResult
from app.runtime.refund_checkpoint import classify_refund_checkpoint


def snapshot(values, next_nodes, config, tasks=(), interrupts=()):
    return StateSnapshot(
        values, next_nodes, {"configurable": config}, None, None, None, tasks, interrupts
    )


def examples():
    appid, opid, approval_id, thread = (str(uuid4()) for _ in range(4))
    raw = {"order_id": "order"}
    subject = {
        "application_id": appid,
        "operation_id": opid,
        "user_id": "user",
        "conversation_id": "conv",
        "thread_id": thread,
        "task_id": "task",
        "workflow_id": "task",
        "call_id": "call",
        "tool_name": "refund_order",
        "tool_version": "1",
        "canonical_args": raw,
        "args_digest": canonical_digest(raw),
        "amount": "12.50",
        "currency": "CNY",
    }
    approval = {
        "decision": "PENDING",
        "approval_id": approval_id,
        "subject_snapshot": subject,
        "subject_digest": canonical_digest(subject),
        "interrupt_id": "intr",
        "checkpoint_ns": "refund:abc",
        "checkpoint_id": "previous",
    }
    app = {
        "application_id": appid,
        "operation_id": opid,
        "tool_name": "refund_order",
        "tool_version": "1",
        "call_id": "call",
        "canonical_args": raw,
        "raw_args": raw,
        "args_digest": canonical_digest(raw),
        "user_id": "user",
        "conversation_id": "conv",
        "thread_id": thread,
        "task_id": "task",
        "workflow_id": "task",
        "amount": Decimal("12.50"),
        "currency": "CNY",
    }
    context = ExecutionContext(
        user_id="user", conversation_id="conv", task_id="task", workflow_id="task", run_id="run"
    )
    request = SpecialistInput(
        context=context,
        task_id="task",
        agent_type=AgentType.REFUND,
        task_type=TaskType.REFUND_APPLY,
        task_goal="refund",
    )
    child_values = {
        "request": request,
        "original_ai_message": AIMessage(
            content="", tool_calls=[{"id": "call", "name": "refund_order", "args": raw}]
        ),
        "pending_refund_call": {"call_id": "call", "name": "refund_order", "raw_args": raw},
        "canonical_args": raw,
        "tool_version": "1",
        "application_id": appid,
        "operation_id": opid,
        "approval_id": approval_id,
        "subject_digest": approval["subject_digest"],
    }
    payload = {
        "kind": "refund_approval",
        "approval_id": approval_id,
        "application_id": appid,
        "operation_id": opid,
        "subject_digest": approval["subject_digest"],
    }
    child = snapshot(
        child_values,
        ("approval_gate",),
        {"thread_id": thread, "checkpoint_ns": "refund:abc", "checkpoint_id": "current"},
        interrupts=(Interrupt(value=payload, id="intr"),),
    )
    parent = snapshot(
        context.model_dump(),
        ("refund",),
        {"thread_id": thread, "checkpoint_ns": "", "checkpoint_id": "root"},
        tasks=(PregelTask("scheduler", "refund", (), state=child),),
    )
    return parent, child, approval, app


def test_pending_binding_and_safe_post_gate_classification():
    root, child, approval, app = examples()
    pending = classify_refund_checkpoint(root, approval, app)
    assert pending.kind == "pending" and pending.bound and pending.interrupt_id == "intr"
    unbound = {**approval, "interrupt_id": None, "checkpoint_ns": None, "checkpoint_id": None}
    assert not classify_refund_checkpoint(root, unbound, app).bound
    child = child._replace(next=("execute_refund",), interrupts=())
    root = root._replace(tasks=(PregelTask("scheduler", "refund", (), state=child),))
    assert classify_refund_checkpoint(root, approval, app).kind == "post_gate"
    child = child._replace(next=("plan_refund_call",))
    root = root._replace(tasks=(PregelTask("scheduler", "refund", (), state=child),))
    assert classify_refund_checkpoint(root, approval, app).kind == "unknown"


def test_mismatched_call_binding_or_owner_never_authorizes_resume():
    root, child, approval, app = examples()
    bad = deepcopy(app)
    bad["raw_args"] = {"order_id": "different"}
    assert classify_refund_checkpoint(root, approval, bad).kind == "unknown"
    bad = {**approval, "interrupt_id": "another"}
    assert classify_refund_checkpoint(root, bad, app).kind == "unknown"
    bad = {**approval, "checkpoint_ns": "unrelated"}
    assert classify_refund_checkpoint(root, bad, app).kind == "unknown"
    assert (
        classify_refund_checkpoint(root._replace(next=("refund", "other")), approval, app).kind
        == "unknown"
    )
    assert (
        classify_refund_checkpoint(
            root._replace(interrupts=(Interrupt(value={}, id="foreign"),)), approval, app
        ).kind
        == "unknown"
    )
    root = root._replace(values={**root.values, "user_id": "other"})
    assert classify_refund_checkpoint(root, approval, app).kind == "unknown"


def test_finished_refund_returns_only_original_associated_result():
    root, _, approval, app = examples()
    subject = approval["subject_snapshot"]
    result = SpecialistResult(
        workflow_id="task",
        task_id="task",
        run_id="run",
        agent_type=AgentType.REFUND,
        task_type=TaskType.REFUND_APPLY,
        status="completed",
        summary="done",
        facts={"simulated": True},
        operation_id=subject["operation_id"],
        approval_id=str(approval["approval_id"]),
    )
    root = root._replace(
        next=(),
        tasks=(),
        values={**root.values, "specialist_result": result, "task_status": "completed"},
    )
    assert classify_refund_checkpoint(root, approval, app).kind == "ended"
    assert (
        classify_refund_checkpoint(
            root._replace(interrupts=(Interrupt(value={}, id="old"),)), approval, app
        ).kind
        == "unknown"
    )
    assert (
        classify_refund_checkpoint(root, {**approval, "approval_id": str(uuid4())}, app).kind
        == "unknown"
    )


async def test_runtime_inspection_reads_nested_thread_without_advancing():
    from app.runtime.agent_runtime import AgentRuntime, RunLimits

    root, _, approval, app = examples()

    class Graph:
        async def aget_state(self, config, *, subgraphs):
            assert subgraphs is True
            assert config["configurable"]["thread_id"] == approval["subject_snapshot"]["thread_id"]
            return root

    runtime = AgentRuntime(Graph(), run_limits=RunLimits(10, 12))
    result = await runtime._inspect_refund_checkpoint(approval, app)
    assert result.kind == "pending" and result.interrupt_id == "intr"
    assert not runtime._records and not runtime._claims
    await runtime.shutdown()


async def test_runtime_resolves_framework_child_config_before_classification():
    from app.runtime.agent_runtime import AgentRuntime, RunLimits

    root, child, approval, app = examples()
    child_config = child.config
    root = root._replace(tasks=(PregelTask("scheduler", "refund", (), state=child_config),))

    class Graph:
        async def aget_state(self, config, *, subgraphs):
            assert subgraphs
            return child if config.get("configurable", {}).get("checkpoint_ns") else root

    runtime = AgentRuntime(Graph(), run_limits=RunLimits(10, 12))
    assert (await runtime._inspect_refund_checkpoint(approval, app)).kind == "pending"
    await runtime.shutdown()


async def test_repair_binding_is_idempotent_and_never_starts_graph_execution():
    import pytest

    from app.core.errors import RuntimeRequestError
    from app.runtime.agent_runtime import AgentRuntime, RunLimits
    from app.workflows.approvals import ApprovalActor, ApprovalReference

    root, audit_child, stored, application = examples()
    stored.update(interrupt_id=None, checkpoint_ns=None, checkpoint_id=None)

    class Graph:
        async def aget_state(self, config, *, subgraphs):
            if config["configurable"].get("checkpoint_ns"):
                return audit_child
            return root

    class Approvals:
        def __init__(self):
            self.binds = 0

        async def get_application(self, approval_id):
            return stored.copy(), application

        async def bind_interrupt(self, approval_id, binding):
            self.binds += 1
            stored.update(
                interrupt_id=binding.interrupt_id,
                checkpoint_ns=binding.checkpoint_ns,
                checkpoint_id=binding.checkpoint_id,
            )
            return stored

    service = Approvals()
    runtime = AgentRuntime(Graph(), run_limits=RunLimits(10, 12), approval_service=service)
    reference = ApprovalReference(str(stored["approval_id"]))
    actor = ApprovalActor("local-demo-approval")
    first = await runtime.repair_approval_binding(reference, actor=actor)
    # A later legitimate Gate snapshot does not replace the original audit record.
    latest_child = audit_child._replace(
        config={
            "configurable": {
                **audit_child.config["configurable"],
                "checkpoint_id": "later-gate",
            }
        }
    )
    root = root._replace(tasks=(root.tasks[0]._replace(state=latest_child),))
    second = await runtime.repair_approval_binding(reference, actor=actor)
    assert first["repaired"] and not second["repaired"] and service.binds == 2
    assert not runtime._records and not runtime._claims
    runtime._claims[stored["subject_snapshot"]["thread_id"]] = object()
    with pytest.raises(RuntimeRequestError) as busy:
        await runtime.repair_approval_binding(reference, actor=actor)
    assert busy.value.code == "thread_busy"
    await runtime.shutdown()


def test_refund_control_events_only_publish_allowed_fields():
    from app.streaming.events import RuntimeEvent

    paused = RuntimeEvent(
        "workflow_paused",
        "run",
        "task",
        1,
        {
            "application_id": "app",
            "approval_id": "approval",
            "reason": "waiting_approval",
            "raw_args": {"secret": "private"},
            "checkpoint_ns": "private",
        },
    ).public_event()
    assert paused.data["application_id"] == "app" and paused.data["approval_id"] == "approval"
    assert "raw_args" not in paused.data and "checkpoint_ns" not in paused.data
    resumed = RuntimeEvent(
        "workflow_resumed", "new", "task", 2, {"previous_run_id": "old", "private": "secret"}
    ).public_event()
    assert resumed.data["previous_run_id"] == "old" and "private" not in resumed.data


async def test_runtime_resume_pending_ended_post_gate_and_unknown():
    from dataclasses import asdict
    from datetime import UTC, datetime, timedelta

    import pytest
    from langgraph.types import Command

    from app.core.errors import RuntimeRequestError
    from app.runtime.agent_runtime import AgentRuntime, RunLimits
    from app.workflows.approvals import ApprovalActor, ApprovalReference

    root, child, approval, app = examples()
    approval.update(
        decision="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        db_now=datetime.now(UTC),
    )
    child = child._replace(
        values={
            **child.values,
            "model_call_usage": {"model_attempts": 2},
            "run_usage": {"tool_calls": 3, "active_elapsed_ms": 10},
        }
    )
    root = root._replace(tasks=(PregelTask("scheduler", "refund", (), state=child),))

    class Graph:
        def __init__(self):
            self.current = root
            self.inputs = []

        async def aget_state(self, config, *, subgraphs):
            return self.current

        async def ainvoke(self, value, config, *, context, durability):
            self.inputs.append((value, context, durability))
            context.scope.finish_active_period()
            return {
                **context.context.model_dump(),
                "model_call_usage": asdict(context.scope.model_usage()),
                "run_usage": asdict(context.scope.run_usage()),
                "task_status": "failed",
                "final_answer": None,
                "sources": [],
                "error": {"code": "controlled", "message": "controlled"},
            }

    class Approvals:
        async def get_application(self, approval_id):
            return approval, app

        async def prepare_resume(self, approval_id, *, interrupt_id, checkpoint_ns):
            assert (interrupt_id, checkpoint_ns) == ("intr", "refund:abc")
            return approval

    class Refunds:
        status = "SUCCEEDED"

        async def get_operation(self, *, user_id, operation_id):
            return {
                "application_id": app["application_id"],
                "status": self.status,
                "execution_result": {"simulated": True},
            }

    graph = Graph()
    runtime = AgentRuntime(
        graph,
        run_limits=RunLimits(10, 12),
        approval_service=Approvals(),
        refund_service=Refunds(),
        scope_resolver=lambda user: frozenset({"refunds:request"}),
    )
    reference = ApprovalReference(str(approval["approval_id"]))
    actor = ApprovalActor("local-demo-approval")
    assert await runtime.can_resume_approval(reference)
    accepted = await runtime.resume_approval(reference, actor=actor)
    await runtime._records[accepted.run_id].task
    assert accepted.accepted and len(graph.inputs) == 1
    command, execution, durability = graph.inputs[-1]
    assert isinstance(command, Command) and command.resume == {
        "intr": {"approval_id": reference.approval_id}
    }
    assert execution.context.task_id == "task" and execution.context.run_id == accepted.run_id
    assert execution.execution_mode == "resume" and durability == "sync"
    post = child._replace(
        next=("execute_refund",), interrupts=(), values={**child.values, "prepared_attempt": None}
    )
    graph.current = root._replace(tasks=(PregelTask("scheduler", "refund", (), state=post),))
    assert await runtime.can_resume_approval(reference)
    accepted = await runtime.resume_approval(reference, actor=actor)
    await runtime._records[accepted.run_id].task
    assert graph.inputs[-1][0] is None
    assert graph.inputs[-1][1].refund_recovery.disposition == "succeeded"
    runtime._refund_service.status = "PENDING"
    assert not await runtime.can_resume_approval(reference)
    with pytest.raises(RuntimeRequestError) as uncertain:
        await runtime.resume_approval(reference, actor=actor)
    assert uncertain.value.code == "execution_uncertain"
    from app.tools.models import ParsedToolCall, PreparedToolAttempt

    subject = approval["subject_snapshot"]
    marker = PreparedToolAttempt(
        "attempt",
        "old-run",
        "task",
        ParsedToolCall("call", "refund_order", app["raw_args"]),
        "1",
        subject["canonical_args"],
        subject["args_digest"],
        subject["operation_id"],
        3,
        4,
        5,
        {
            "user_id": subject["user_id"],
            "conversation_id": subject["conversation_id"],
            "thread_id": subject["thread_id"],
            "task_id": "task",
            "workflow_id": "task",
            "run_id": "old-run",
            "operation_id": subject["operation_id"],
            "application_id": subject["application_id"],
            "approval_id": reference.approval_id,
            "expected_call_digest": canonical_digest(
                {
                    "call_id": subject["call_id"],
                    "name": subject["tool_name"],
                    "version": subject["tool_version"],
                    "args": subject["canonical_args"],
                }
            ),
        },
        {
            "interrupt_id": approval["interrupt_id"],
            "checkpoint_ns": approval["checkpoint_ns"],
            "checkpoint_id": approval["checkpoint_id"],
        },
    )
    post = post._replace(values={**post.values, "prepared_attempt": marker})
    graph.current = root._replace(tasks=(PregelTask("scheduler", "refund", (), state=post),))
    assert await runtime.can_resume_approval(reference)
    continued = await runtime.resume_approval(reference, actor=actor)
    await runtime._records[continued.run_id].task
    conservative = graph.inputs[-1][1]
    assert conservative.refund_recovery.disposition == "not_executed"
    assert conservative.scope.run_usage().tool_calls == 4
    assert conservative.scope.run_usage().active_elapsed_ms >= 5010
    assert not runtime._records[continued.run_id].usage_complete
    subject = approval["subject_snapshot"]
    result = SpecialistResult(
        workflow_id="task",
        task_id="task",
        run_id="run",
        agent_type=AgentType.REFUND,
        task_type=TaskType.REFUND_APPLY,
        status="completed",
        summary="done",
        facts={"simulated": True},
        operation_id=subject["operation_id"],
        approval_id=reference.approval_id,
    )
    graph.current = root._replace(
        next=(),
        tasks=(),
        values={**root.values, "specialist_result": result, "task_status": "completed"},
    )
    count = len(runtime._records)
    ended = await runtime.resume_approval(reference, actor=actor)
    assert not ended.accepted and ended.run_id is None and len(runtime._records) == count
    await runtime.shutdown()


async def test_runtime_publishes_pause_only_after_matching_binding(monkeypatch):
    from dataclasses import replace

    from langgraph.types import StateSnapshot
    from runtime_support import context, run_to_end

    import app.runtime.agent_runtime as runtime_module
    from app.runtime.agent_runtime import AgentRuntime, RunLimits

    root, child, approval, app = examples()
    approval.update(interrupt_id=None, checkpoint_ns=None, checkpoint_id=None)
    empty = StateSnapshot(
        {},
        (),
        {"configurable": {"thread_id": approval["subject_snapshot"]["thread_id"]}},
        None,
        None,
        None,
        (),
        (),
    )

    class Graph:
        current = empty

        async def aget_state(self, config, *, subgraphs=False):
            return self.current

        async def ainvoke(self, value, config, *, context, durability):
            context.scope.finish_active_period()
            self.current = root
            return {"__interrupt__": child.interrupts}

    class Approvals:
        async def get_application(self, approval_id):
            return approval.copy(), app

        async def bind_interrupt(self, approval_id, binding):
            approval.update(
                interrupt_id=binding.interrupt_id,
                checkpoint_ns=binding.checkpoint_ns,
                checkpoint_id=binding.checkpoint_id,
            )

    monkeypatch.setattr(runtime_module, "uuid4", lambda: "task")
    runtime = AgentRuntime(Graph(), run_limits=RunLimits(10, 12), approval_service=Approvals())
    ctx = replace(
        context(user="user", conversation="conv", thread=approval["subject_snapshot"]["thread_id"]),
        run_id="run",
    )
    handle, view, events = await run_to_end(runtime, ctx)
    assert handle.task_id == "task" and view.task_status == "waiting_approval"
    assert approval["interrupt_id"] == "intr" and approval["checkpoint_ns"] == "refund:abc"
    assert [event.kind for event in events].count("workflow_paused") == 1
    assert events[-1].kind == "done" and view.final_answer is None
    await runtime.shutdown()


async def test_duplicate_resume_returns_active_run_without_second_task():
    import asyncio
    from datetime import UTC, datetime, timedelta

    from app.runtime.agent_runtime import AgentRuntime, RunLimits
    from app.workflows.approvals import ApprovalActor, ApprovalReference

    root, child, approval, app = examples()
    approval.update(
        decision="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        db_now=datetime.now(UTC),
    )
    child = child._replace(
        values={
            **child.values,
            "model_call_usage": {"model_attempts": 1},
            "run_usage": {"tool_calls": 1, "active_elapsed_ms": 10},
        }
    )
    root = root._replace(tasks=(PregelTask("scheduler", "refund", (), state=child),))
    entered = asyncio.Event()

    class Graph:
        async def aget_state(self, config, *, subgraphs):
            return root

        async def ainvoke(self, value, config, *, context, durability):
            entered.set()
            await asyncio.Event().wait()

    class Approvals:
        async def get_application(self, approval_id):
            return approval, app

        async def prepare_resume(self, approval_id, *, interrupt_id, checkpoint_ns):
            return approval

    runtime = AgentRuntime(
        Graph(),
        run_limits=RunLimits(10, 12),
        approval_service=Approvals(),
        scope_resolver=lambda user: frozenset({"refunds:request"}),
        shutdown_grace_seconds=0,
    )
    reference = ApprovalReference(str(approval["approval_id"]))
    actor = ApprovalActor("local-demo-approval")
    first = await runtime.resume_approval(reference, actor=actor)
    await entered.wait()
    second = await runtime.resume_approval(reference, actor=actor)
    assert first.accepted and not second.accepted and second.run_id == first.run_id
    assert len(runtime._records) == 1 and not await runtime.can_resume_approval(reference)
    await runtime.shutdown()
