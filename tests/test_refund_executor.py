"""Same-executor refund preparation and current-approval checks."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel

from app.agents.types import AgentType, TaskType
from app.domain.refunds import OriginalRefundCall, RefundBusinessContext, canonical_digest
from app.graph.contracts import ExecutionContext
from app.runtime.model_gateway import ModelCallUsage
from app.runtime.models import RunLimits, RunUsage
from app.runtime.run_scope import RunScope
from app.tools.executor import ToolExecutor
from app.tools.implementations.refunds import RefundOrderArgs, refund_order_tool
from app.tools.models import (
    HandlerResult,
    ParsedToolCall,
    PolicyDecision,
    PreparedToolAttempt,
    ToolDefinition,
    ToolExecutionContext,
)
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from app.workflows.approvals import ApprovalError, InterruptBinding, VerifiedApproval


class Result(BaseModel):
    value: str


class Verifier:
    def __init__(self):
        self.calls = 0
        self.allow = True

    async def verify_for_call(self, reference, *, original_call, context, interrupt_binding):
        self.calls += 1
        if not self.allow:
            raise ApprovalError("approval_not_valid")
        subject = {
            "user_id": context.user_id,
            "conversation_id": context.conversation_id,
            "task_id": context.task_id,
            "workflow_id": context.workflow_id,
            "call_id": original_call.call_id,
            "tool_name": original_call.tool_name,
            "tool_version": original_call.tool_version,
            "canonical_args": original_call.canonical_args,
            "args_digest": canonical_digest(original_call.canonical_args),
            "thread_id": context.thread_id,
            "application_id": context.application_id,
            "operation_id": context.operation_id,
        }
        now = datetime.now(UTC)
        return VerifiedApproval(
            reference.approval_id,
            context.application_id,
            context.operation_id,
            canonical_digest(subject),
            subject,
            "local-demo-approval",
            now,
            now + timedelta(minutes=1),
        )


async def test_prepared_refund_rechecks_scope_approval_and_one_attempt():
    seen = []

    async def handler(args, context):
        seen.append(context)
        return HandlerResult(data=Result(value="ok"))

    definition = refund_order_tool(None, timeout_seconds=5)
    definition = ToolDefinition(definition.metadata, RefundOrderArgs, Result, handler)
    registry = ToolRegistry()
    registry.register(definition)
    registry.freeze()
    verifier = Verifier()
    executor = ToolExecutor(registry, ToolPolicy(), approval_service=verifier)
    limits = RunLimits(30, 3)
    scope = RunScope(limits=limits, model_usage=ModelCallUsage(), run_usage=RunUsage())
    scope.start_active_period()
    execution = ExecutionContext(
        user_id="user", conversation_id="conv", task_id="task", workflow_id="task", run_id="run"
    )
    original = OriginalRefundCall(
        "call", "refund_order", "1", {"order_id": "one"}, {"order_id": "one"}
    )
    business = RefundBusinessContext(
        "user",
        "task",
        "run",
        "conv",
        str(uuid4()),
        "task",
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
        original.call_digest(),
    )
    context = ToolExecutionContext(
        execution,
        AgentType.REFUND,
        TaskType.REFUND_APPLY,
        None,
        frozenset({"refunds:request"}),
        "model",
        frozenset({("refund_order", "1")}),
        {"refund_order": {"order_id": "one"}},
        limits,
        scope,
        business,
        InterruptBinding("id", "ns", "cp"),
    )
    call = ParsedToolCall("call", "refund_order", {"order_id": "one"})
    assert (
        await executor.assess(call, context=context)
    ).decision is PolicyDecision.REQUIRE_APPROVAL
    marker = await executor.prepare_attempt(call, context=context)
    assert isinstance(marker, PreparedToolAttempt) and scope.run_usage().tool_calls == 0
    denied = await executor.execute_prepared(
        marker, context=replace(context, permission_scopes=frozenset())
    )
    assert denied.status == "policy_denied" and scope.run_usage().tool_calls == 0 and not seen
    verifier.allow = False
    denied = await executor.execute_prepared(marker, context=context)
    assert denied.status == "policy_denied" and scope.run_usage().tool_calls == 0 and not seen
    verifier.allow = True
    result = await executor.execute_prepared(marker, context=context)
    assert result.status == "success" and scope.run_usage().tool_calls == 1 and seen == [business]
    repeated = await executor.execute_prepared(marker, context=context)
    assert (
        repeated.status == "policy_denied" and scope.run_usage().tool_calls == 1 and len(seen) == 1
    )
    assert verifier.calls >= 4


async def test_node_origin_has_fixed_node_scope_and_projects_trusted_business_context():
    from app.tools.implementations.refunds import refund_node_tools

    seen = []

    async def handler(args, context):
        seen.append(context)
        return HandlerResult(data=Result(value="ok"))

    node = refund_node_tools(None, None, timeout_seconds=5)[1]
    registry = ToolRegistry()
    registry.register(ToolDefinition(node.metadata, node.args_schema, Result, handler))
    registry.freeze()
    executor = ToolExecutor(registry, ToolPolicy())
    limits = RunLimits(30, 3)
    scope = RunScope(limits=limits, model_usage=ModelCallUsage(), run_usage=RunUsage())
    scope.start_active_period()
    execution = ExecutionContext(
        user_id="user", conversation_id="conv", task_id="task", workflow_id="task", run_id="run"
    )
    original = OriginalRefundCall(
        "call", "refund_order", "1", {"order_id": "one"}, {"order_id": "one"}
    )
    business = RefundBusinessContext(
        "user",
        "task",
        "run",
        "conv",
        str(uuid4()),
        "task",
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
        original.call_digest(),
    )
    ctx = ToolExecutionContext(
        execution,
        AgentType.REFUND,
        TaskType.REFUND_APPLY,
        "prepare_application",
        frozenset({"refunds:request"}),
        "node",
        frozenset({("prepare_refund_application", "1")}),
        {},
        limits,
        scope,
        business,
    )
    call = ParsedToolCall(
        "node",
        "prepare_refund_application",
        {
            "call_id": "call",
            "tool_name": "refund_order",
            "tool_version": "1",
            "raw_args": {"order_id": "one"},
            "canonical_args": {"order_id": "one"},
        },
    )
    assert (
        await executor.execute(call, context=replace(ctx, node_name="persist_approval"))
    ).status == "policy_denied"
    assert (
        await executor.execute(
            call, context=replace(ctx, refund_context=replace(business, user_id="other"))
        )
    ).status == "policy_denied"
    assert not seen and scope.run_usage().tool_calls == 0
    assert (await executor.execute(call, context=ctx)).status == "success"
    assert seen == [business] and scope.run_usage().tool_calls == 1


async def test_fixed_node_preparation_binds_context_and_rechecks_policy():
    from app.tools.models import MemoryBusinessContext, ToolMetadata

    class Args(BaseModel):
        operation: str
        field: str
        value: str

    seen = []

    async def handler(args, context):
        seen.append((args, context))
        return HandlerResult(data=Result(value="ok"))

    metadata = ToolMetadata(
        "write_preferences",
        "1",
        "test",
        True,
        frozenset({AgentType.KNOWLEDGE}),
        frozenset({"memory:write"}),
        "low",
        False,
        False,
        True,
        "operation_id_required",
        5,
        0,
        frozenset(),
    )
    registry = ToolRegistry()
    registry.register(ToolDefinition(metadata, Args, Result, handler))
    registry.freeze()
    executor = ToolExecutor(registry, ToolPolicy())
    limits = RunLimits(30, 3)
    scope = RunScope(limits=limits, model_usage=ModelCallUsage(), run_usage=RunUsage())
    scope.start_active_period()
    execution = ExecutionContext(
        user_id="user", conversation_id="conv", task_id="task", workflow_id="task", run_id="run"
    )
    args = {"operation": "upsert", "field": "answer_style", "value": "concise"}
    target = ToolExecutionContext(
        execution,
        AgentType.KNOWLEDGE,
        TaskType.MEMORY_MANAGE,
        "execute_memory_write",
        frozenset({"memory:write"}),
        "node",
        frozenset({("write_preferences", "1")}),
        {"write_preferences": args},
        limits,
        scope,
        thread_id="thread",
    )
    preparation = replace(target, node_name="prepare_memory_write")
    business = MemoryBusinessContext(
        "user", "task", "run", "operation", canonical_digest(args), 0, False
    )
    call = ParsedToolCall("node:write", "write_preferences", args)
    for wrong in (
        replace(target, thread_id="other"),
        replace(target, execution=execution.model_copy(update={"run_id": "other"})),
        replace(target, permission_scopes=frozenset()),
        replace(target, argument_constraints={"write_preferences": {**args, "value": "other"}}),
    ):
        denied = await executor.prepare_attempt(
            call, context=preparation, execution_context=wrong, business_context=business
        )
        assert denied.status == "policy_denied"
    denied = await executor.prepare_attempt(
        call,
        context=preparation,
        execution_context=target,
        business_context=replace(business, user_id="other"),
    )
    assert denied.status == "policy_denied" and not seen
    marker = await executor.prepare_attempt(
        call, context=preparation, execution_context=target, business_context=business
    )
    assert isinstance(marker, PreparedToolAttempt) and scope.run_usage().tool_calls == 0
    assert (await executor.execute(call, context=target)).status == "policy_denied"
    assert (await executor.execute_batch([call], context=target))[0].status == "policy_denied"
    for wrong in (
        replace(target, thread_id="other"),
        replace(target, permission_scopes=frozenset()),
        replace(target, node_name="prepare_memory_write"),
    ):
        assert (await executor.execute_prepared(marker, context=wrong)).status == "policy_denied"
    assert not seen and scope.run_usage().tool_calls == 0
    result = await executor.execute_prepared(marker, context=target)
    assert result.status == "success" and seen[0][1] == business
    assert scope.run_usage().tool_calls == 1
    assert (await executor.execute_prepared(marker, context=target)).status == "policy_denied"
    replay = replace(business, replay_check_only=True)
    marker = await executor.prepare_attempt(call, context=target, business_context=replay)
    assert isinstance(marker, PreparedToolAttempt)
    assert (await executor.execute_prepared(marker, context=target)).status == "success"
    assert seen[-1][1].replay_check_only and scope.run_usage().tool_calls == 2
