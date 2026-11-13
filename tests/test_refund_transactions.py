"""Real-PG refund and approval transaction checks with disposable test records."""

import asyncio
import os
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from pydantic import SecretStr

from app.agents.types import AgentType, TaskType
from app.core.config import Settings
from app.domain.refunds import (
    MockRefundService,
    OriginalRefundCall,
    RefundBusinessContext,
    RefundRejected,
    application_subject,
)
from app.graph.contracts import ExecutionContext
from app.infrastructure.postgres import open_pool, validate_test_target
from app.runtime.model_gateway import ModelCallUsage
from app.runtime.models import RunLimits, RunUsage
from app.runtime.run_scope import RunScope
from app.tools.executor import ToolExecutor
from app.tools.implementations.refunds import refund_order_tool
from app.tools.models import (
    ParsedToolCall,
    PolicyDecision,
    PreparedToolAttempt,
    ToolExecutionContext,
)
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from app.workflows.approvals import (
    ApprovalError,
    ApprovalReference,
    ApprovalService,
    InterruptBinding,
    InterruptBindingRequest,
    LocalDemoApprovalActor,
)
from scripts import run_async


def test_refund_approval_and_concurrent_operations_real_pg(monkeypatch):
    raw = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Explicit test database required")
    url = SecretStr(raw)
    validate_test_target(url, Settings().database_url)

    async def scenario():
        pool = await open_pool(Settings(_env_file=None, app_env="test", database_url=url))
        owner = "refund-04-" + uuid4().hex
        order = owner
        contexts = []
        try:
            async with pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO demo_orders VALUES (%s,%s,42.50,'CNY','paid',false,now())",
                    (order, owner),
                )
                for i in range(8):
                    thread = str(uuid4())
                    await conn.execute(
                        "INSERT INTO sessions (user_id,conversation_id,thread_id) "
                        "VALUES (%s,%s,%s)",
                        (owner, str(i), thread),
                    )
                    call = OriginalRefundCall(
                        "call", "refund_order", "1", {"order_id": order}, {"order_id": order}
                    )
                    contexts.append(
                        (
                            RefundBusinessContext(
                                owner,
                                "task" + str(i),
                                "run",
                                str(i),
                                thread,
                                "task" + str(i),
                                str(uuid4()),
                                str(uuid4()),
                                str(uuid4()),
                                call.call_digest(),
                            ),
                            call,
                        )
                    )
            service = MockRefundService(pool)
            approvals = ApprovalService(pool)
            actor = LocalDemoApprovalActor().get_actor()
            binding = InterruptBinding("interrupt", "namespace", "checkpoint")
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE demo_orders SET payment_status='unpaid' WHERE order_id=%s", (order,)
                )
            with pytest.raises(RefundRejected):
                await service.check_eligibility(context=contexts[0][0], order_id=order)
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE demo_orders SET payment_status='paid' WHERE order_id=%s", (order,)
                )
            subjects = []
            for index, (ctx, call) in enumerate(contexts):
                await service.prepare_application(context=ctx, original_call=call)
                async with pool.connection() as conn:
                    async with conn.cursor(row_factory=dict_row) as cur:
                        await cur.execute(
                            "SELECT * FROM refund_requests WHERE application_id=%s",
                            (ctx.application_id,),
                        )
                        subject = application_subject(await cur.fetchone())
                subjects.append(subject)
                record = await approvals.register_pending(
                    approval_id=ctx.approval_id, subject=subject
                )
                with pytest.raises(ApprovalError) as not_ready:
                    await approvals.decide(
                        ctx.approval_id,
                        actor=actor,
                        decision="APPROVED",
                        expected_subject_digest=record["subject_digest"],
                    )
                assert not_ready.value.code == "approval_not_ready"
                request = InterruptBindingRequest(
                    binding.interrupt_id,
                    binding.checkpoint_ns,
                    binding.checkpoint_id,
                    record["subject_digest"],
                    "PENDING",
                )
                await approvals.bind_interrupt(ctx.approval_id, request)
                with pytest.raises(ApprovalError) as pending:
                    await approvals.prepare_resume(
                        ctx.approval_id,
                        interrupt_id=binding.interrupt_id,
                        checkpoint_ns=binding.checkpoint_ns,
                    )
                assert pending.value.code == "approval_pending"
                with pytest.raises(ApprovalError):
                    await approvals.bind_interrupt(
                        ctx.approval_id, replace(request, interrupt_id="different")
                    )
                if index == 2:
                    await approvals.decide(
                        ctx.approval_id,
                        actor=actor,
                        decision="REJECTED",
                        expected_subject_digest=record["subject_digest"],
                    )
                    with pytest.raises(RefundRejected):
                        await service.execute_original(context=ctx, order_id=order)
                    assert (
                        await service.reject_application(
                            context=ctx, reason_code="approval_rejected"
                        )
                    )["status"] == "REJECTED"
                    continue
                if index == 3:
                    async with pool.connection() as conn:
                        await conn.execute(
                            "UPDATE approvals SET created_at=now()-interval '60 minutes', "
                            "expires_at=now()-interval '30 minutes' WHERE approval_id=%s",
                            (ctx.approval_id,),
                        )
                    assert (await approvals.get(ctx.approval_id))["decision"] == "PENDING"
                    with pytest.raises(ApprovalError) as expired:
                        await approvals.decide(
                            ctx.approval_id,
                            actor=actor,
                            decision="APPROVED",
                            expected_subject_digest=record["subject_digest"],
                        )
                    assert expired.value.code == "approval_expired"
                    assert (await approvals.get(ctx.approval_id))["decision"] == "EXPIRED"
                    continue
                if index == 5:

                    async def submit(decision, current=ctx, digest=record["subject_digest"]):
                        try:
                            return await approvals.decide(
                                current.approval_id,
                                actor=actor,
                                decision=decision,
                                expected_subject_digest=digest,
                            )
                        except ApprovalError as error:
                            return error.code

                    concurrent = await asyncio.gather(submit("APPROVED"), submit("REJECTED"))
                    assert sum(isinstance(item, dict) for item in concurrent) == 1
                    assert "approval_decision_conflict" in concurrent
                    continue
                if index == 6:
                    async with pool.connection() as conn:
                        await conn.execute(
                            "UPDATE approvals SET "
                            "created_at=now()-interval '29 minutes 59.7 seconds', "
                            "expires_at=now()+interval '0.3 seconds' WHERE approval_id=%s",
                            (ctx.approval_id,),
                        )
                        waiting = asyncio.create_task(
                            approvals.decide(
                                ctx.approval_id,
                                actor=actor,
                                decision="APPROVED",
                                expected_subject_digest=record["subject_digest"],
                            )
                        )
                        await asyncio.sleep(0.4)
                        assert not waiting.done()
                    with pytest.raises(ApprovalError) as expiry_after_lock:
                        await waiting
                    assert expiry_after_lock.value.code == "approval_expired"
                    assert (await approvals.get(ctx.approval_id))["decision"] == "EXPIRED"
                    continue
                if index == 7:
                    async with pool.connection() as conn:
                        await conn.execute(
                            "UPDATE approvals SET created_at=now()-interval '60 minutes', "
                            "expires_at=now()-interval '30 minutes' WHERE approval_id=%s",
                            (ctx.approval_id,),
                        )
                    expired = await approvals.prepare_resume(
                        ctx.approval_id,
                        interrupt_id=binding.interrupt_id,
                        checkpoint_ns=binding.checkpoint_ns,
                    )
                    assert expired["decision"] == "EXPIRED"
                    assert (await approvals.get(ctx.approval_id))["decision"] == "EXPIRED"
                    continue
                decided = await approvals.decide(
                    ctx.approval_id,
                    actor=actor,
                    decision="APPROVED",
                    expected_subject_digest=record["subject_digest"],
                )
                repeated = await approvals.decide(
                    ctx.approval_id,
                    actor=actor,
                    decision="APPROVED",
                    expected_subject_digest=record["subject_digest"],
                )
                assert (decided["approver_id"], decided["decided_at"], decided["expires_at"]) == (
                    repeated["approver_id"],
                    repeated["decided_at"],
                    repeated["expires_at"],
                )
                if index == 4:
                    async with pool.connection() as conn:
                        await conn.execute(
                            "UPDATE approvals SET created_at=now()-interval '60 minutes', "
                            "expires_at=now()-interval '30 minutes' WHERE approval_id=%s",
                            (ctx.approval_id,),
                        )
                    repeated = await approvals.decide(
                        ctx.approval_id,
                        actor=actor,
                        decision="APPROVED",
                        expected_subject_digest=record["subject_digest"],
                    )
                    assert repeated["decided_at"] == decided["decided_at"]
                    assert repeated["approver_id"] == decided["approver_id"]
                    with pytest.raises(RefundRejected):
                        await service.execute_original(context=ctx, order_id=order)
                    assert (await approvals.get(ctx.approval_id))["decision"] == "APPROVED"
                    continue
                verified = await approvals.verify_for_call(
                    ApprovalReference(ctx.approval_id),
                    original_call=call,
                    context=ctx,
                    interrupt_binding=binding,
                )
                assert verified.subject == subject

            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE demo_orders SET payment_status='unpaid' WHERE order_id=%s", (order,)
                )
            with pytest.raises(RefundRejected):
                await service.execute_original(context=contexts[0][0], order_id=order)
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE demo_orders SET payment_status='paid' WHERE order_id=%s", (order,)
                )
            original_execute = psycopg.AsyncCursor.execute

            async def fail_after_order_update(cursor, query, *args, **kwargs):
                if isinstance(query, str) and query.startswith(
                    "UPDATE refund_requests SET status='SUCCEEDED'"
                ):
                    raise psycopg.OperationalError("controlled test fault")
                return await original_execute(cursor, query, *args, **kwargs)

            async with pool.connection() as locked:
                await locked.execute(
                    "SELECT order_id FROM demo_orders WHERE order_id=%s FOR UPDATE", (order,)
                )
                lookup = asyncio.create_task(
                    service.get_operation(user_id=owner, operation_id=contexts[0][0].operation_id)
                )
                await asyncio.sleep(0.05)
                assert not lookup.done()
            assert (await lookup)["status"] == "PENDING"

            with monkeypatch.context() as patch:
                patch.setattr(psycopg.AsyncCursor, "execute", fail_after_order_update)
                with pytest.raises(psycopg.OperationalError):
                    await service.execute_original(context=contexts[0][0], order_id=order)
            async with pool.connection() as conn:
                assert await (
                    await conn.execute(
                        "SELECT is_refunded FROM demo_orders WHERE order_id=%s", (order,)
                    )
                ).fetchone() == (False,)
                assert await (
                    await conn.execute(
                        "SELECT status FROM refund_requests WHERE application_id=%s",
                        (contexts[0][0].application_id,),
                    )
                ).fetchone() == ("PENDING",)

            registry = ToolRegistry()
            registry.register(refund_order_tool(service, timeout_seconds=5))
            registry.freeze()
            executor = ToolExecutor(registry, ToolPolicy(), approval_service=approvals)
            prepared = []
            for ctx, call in contexts[:2]:
                execution = ExecutionContext(
                    user_id=ctx.user_id,
                    conversation_id=ctx.conversation_id,
                    task_id=ctx.task_id,
                    workflow_id=ctx.workflow_id,
                    run_id=ctx.run_id,
                )
                limits = RunLimits(30, 4)
                scope = RunScope(limits=limits, model_usage=ModelCallUsage(), run_usage=RunUsage())
                scope.start_active_period()
                tool_context = ToolExecutionContext(
                    execution,
                    AgentType.REFUND,
                    TaskType.REFUND_APPLY,
                    None,
                    frozenset({"refunds:request"}),
                    "model",
                    frozenset({("refund_order", "1")}),
                    {"refund_order": {"order_id": order}},
                    limits,
                    scope,
                    ctx,
                    binding,
                )
                original_call = ParsedToolCall(call.call_id, call.tool_name, call.raw_args)
                assert (
                    await executor.assess(original_call, context=tool_context)
                ).decision is PolicyDecision.REQUIRE_APPROVAL
                attempt = await executor.prepare_attempt(original_call, context=tool_context)
                assert (
                    isinstance(attempt, PreparedToolAttempt) and scope.run_usage().tool_calls == 0
                )
                denied = await executor.execute_prepared(
                    attempt, context=replace(tool_context, permission_scopes=frozenset())
                )
                assert denied.status == "policy_denied" and scope.run_usage().tool_calls == 0
                prepared.append((attempt, tool_context))
            current_approval = await approvals.get(contexts[0][0].approval_id)
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE approvals SET created_at=now()-interval '60 minutes', "
                    "expires_at=now()-interval '30 minutes' WHERE approval_id=%s",
                    (contexts[0][0].approval_id,),
                )
            revoked = await executor.execute_prepared(prepared[0][0], context=prepared[0][1])
            assert revoked.status == "policy_denied"
            assert prepared[0][1].scope.run_usage().tool_calls == 0
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE approvals SET created_at=%s,expires_at=%s WHERE approval_id=%s",
                    (
                        current_approval["created_at"],
                        current_approval["expires_at"],
                        contexts[0][0].approval_id,
                    ),
                )
            first, second = await asyncio.gather(
                *(executor.execute_prepared(a, context=c) for a, c in prepared)
            )
            assert sorted((first.status, second.status)) == ["business_rejected", "success"]
            assert all(c.scope.run_usage().tool_calls == 1 for _, c in prepared)
            winner = contexts[0][0] if first.status == "success" else contexts[1][0]
            original = first.data if first.status == "success" else second.data
            same = await asyncio.gather(
                *(service.execute_original(context=winner, order_id=order) for _ in range(3))
            )
            assert all(result == original for result in same)
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE approvals SET created_at=now()-interval '60 minutes', "
                    "expires_at=now()-interval '30 minutes' WHERE approval_id=%s",
                    (winner.approval_id,),
                )
            assert await service.execute_original(context=winner, order_id=order) == original
            with pytest.raises(RefundRejected):
                await service.execute_original(
                    context=replace(winner, approval_id=str(uuid4())), order_id=order
                )
            with pytest.raises(RefundRejected):
                await service.execute_original(
                    context=replace(winner, approval_id=None), order_id=order
                )
            assert (await service.check_eligibility(context=winner, order_id=order)) == {
                "status": "SUCCEEDED",
                "execution_result": original,
            }
            winner_call = contexts[0][1] if winner == contexts[0][0] else contexts[1][1]
            assert (await service.prepare_application(context=winner, original_call=winner_call))[
                "status"
            ] == "SUCCEEDED"
            async with pool.connection() as conn:
                row = await (
                    await conn.execute(
                        "SELECT count(*) FROM refund_requests "
                        "WHERE user_id=%s AND status='SUCCEEDED'",
                        (owner,),
                    )
                ).fetchone()
                assert row == (1,)
                assert await (
                    await conn.execute(
                        "SELECT is_refunded FROM demo_orders WHERE order_id=%s", (order,)
                    )
                ).fetchone() == (True,)
        finally:
            async with pool.connection() as conn:
                await conn.execute(
                    "DELETE FROM approvals WHERE application_id IN "
                    "(SELECT application_id FROM refund_requests WHERE user_id=%s)",
                    (owner,),
                )
                await conn.execute("DELETE FROM refund_requests WHERE user_id=%s", (owner,))
                await conn.execute(
                    "DELETE FROM demo_orders WHERE owner_id=%s AND order_id=%s", (owner, order)
                )
                await conn.execute("DELETE FROM sessions WHERE user_id=%s", (owner,))
            await pool.close()

    run_async(scenario())
