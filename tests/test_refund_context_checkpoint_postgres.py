"""Original context dependency integrity at a real Saver approval interrupt."""

import os
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from runtime_support import ControlledModel, compiled, context, run_to_end
from test_refund_full_controlled import (
    ControlledApprovals,
    ControlledOrders,
    ControlledRefunds,
    Provider,
)

from app.agents.types import AgentType
from app.context.archive_store import ArchiveStore
from app.context.manager import ContextManager
from app.context.models import (
    ContextRevision,
    PublicInteraction,
    PublicMessage,
    SessionIdentity,
    Summary,
)
from app.context.repository import ContextRepository
from app.core.errors import RuntimeRequestError
from app.graph.builder import build_supervisor_graph
from app.graph.contracts import SupervisorOutput
from app.graph.specialists.knowledge.builder import build_knowledge_graph
from app.graph.specialists.order.builder import build_order_graph
from app.graph.specialists.refund.builder import build_refund_graph
from app.infrastructure.checkpoint import checkpoint_serializer
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from app.tools.executor import ToolExecutor
from app.tools.implementations.orders import order_tools
from app.tools.implementations.refunds import refund_node_tools, refund_order_tool
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from app.workflows.approvals import ApprovalReference, LocalDemoApprovalActor
from scripts import run_async


def test_refund_resume_checks_original_archive_before_effect(tmp_path):
    dsn = os.getenv("AGENT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated database not configured")
    info = conninfo_to_dict(dsn)
    assert (info.get("host"), info.get("port"), info.get("dbname"), info.get("user")) == (
        "127.0.0.1",
        "56431",
        "agent_demo_test",
        "agent_test",
    )

    async def probe():
        async with await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, options="-c default_transaction_read_only=on"
        ) as guard:
            row = await (
                await guard.execute(
                    "SELECT current_database(),current_user,current_setting('server_version_num'),"
                    "shobj_description(oid,'pg_database') FROM pg_database "
                    "WHERE datname=current_database()"
                )
            ).fetchone()
            assert row == ("agent_demo_test", "agent_test", "170012", "codex-task131-0e62")
        token = uuid4().hex
        identity = SessionIdentity(user_id="refundctx-" + token, conversation_id="conv-" + token)
        thread = "refundctx-" + token
        async with AsyncConnectionPool(dsn, open=False) as pool:
            async with AsyncConnectionPool(
                dsn,
                open=False,
                kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
            ) as saver_pool:
                saver = AsyncPostgresSaver(saver_pool, serde=checkpoint_serializer())
                repo = ContextRepository(pool)
                manager = ContextManager(repo, ArchiveStore(tmp_path))
                first_runtime = AgentRuntime(
                    compiled(ControlledModel([SupervisorOutput(kind="unsupported")]), saver=saver),
                    run_limits=RunLimits(30, 12),
                    context_manager=manager,
                )
                runtime = None
                try:
                    first, _, _ = await run_to_end(
                        first_runtime,
                        context(
                            user=identity.user_id,
                            conversation=identity.conversation_id,
                            thread=thread,
                            message="历史订单 order-older",
                        ),
                    )
                    await first_runtime._records[first.run_id].task
                    snapshot = await first_runtime._graph.aget_state(
                        {"configurable": {"thread_id": thread}}
                    )
                    checkpoint = snapshot.config["configurable"]["checkpoint_id"]
                    metadata = snapshot.values["public_message_metadata"]
                    messages = tuple(
                        PublicMessage(
                            message_id=m.id,
                            role="user" if m.type == "human" else "assistant",
                            content=m.content,
                            task_id=metadata[m.id]["task_id"],
                            run_id=metadata[m.id]["run_id"],
                        )
                        for m in snapshot.values["messages"]
                    )
                    archive = await manager.publish(
                        identity,
                        checkpoint,
                        [
                            PublicInteraction(
                                task_id=first.task_id, task_status="REJECTED", messages=messages
                            )
                        ],
                        retain_recent=0,
                        max_messages=2,
                        session_status="REJECTED",
                    )
                    summary = Summary(
                        identity=identity,
                        summary_id="summary-1",
                        version=1,
                        text="Earlier order: order-older.",
                        archive_refs=(archive.archive_ref,),
                        message_ids=archive.message_ids,
                        parent_summary_id=None,
                        input_hash="controlled",
                        status="READY",
                    )
                    await repo.save_summary(
                        summary,
                        source_checkpoint_id=checkpoint,
                        policy_version="p",
                        model_version="m",
                        prompt_version="v",
                    )
                    revision = ContextRevision(
                        identity=identity,
                        revision=1,
                        base_revision=None,
                        source_checkpoint_id=checkpoint,
                        message_ids=archive.message_ids,
                        content_hash=archive.content_hash,
                        archive_refs=(archive.archive_ref,),
                        summary_id=summary.summary_id,
                        policy_version="p",
                        model_version="m",
                        prompt_version="v",
                        status="PREPARING",
                    )
                    await manager.publish_revision(revision, max_bytes=100000)
                    await first_runtime.shutdown()
                    provider, refunds = Provider(), ControlledRefunds(None)
                    gateway = ModelGateway(
                        provider, ModelCallLimits(8, 5, 0), context_window=8192, output_reserve=128
                    )
                    approvals = ControlledApprovals(refunds)
                    registry = ToolRegistry()
                    for definition in (
                        *order_tools(ControlledOrders(), timeout_seconds=1, max_retries=0),
                        *refund_node_tools(refunds, approvals, timeout_seconds=1),
                        refund_order_tool(refunds, timeout_seconds=1),
                    ):
                        registry.register(definition)
                    registry.freeze()
                    executor = ToolExecutor(registry, ToolPolicy(), approval_service=approvals)
                    graph = build_supervisor_graph(
                        gateway=gateway,
                        checkpointer=saver,
                        specialists={
                            AgentType.ORDER: build_order_graph(
                                gateway=gateway, registry=registry, executor=executor
                            ),
                            AgentType.REFUND: build_refund_graph(
                                gateway=gateway,
                                registry=registry,
                                executor=executor,
                                approval_service=approvals,
                                refund_service=refunds,
                            ),
                            AgentType.KNOWLEDGE: build_knowledge_graph(),
                        },
                    )
                    runtime = AgentRuntime(
                        graph,
                        run_limits=RunLimits(30, 12),
                        context_manager=manager,
                        approval_service=approvals,
                        refund_service=refunds,
                        scope_resolver=lambda user: frozenset({"orders:read", "refunds:request"}),
                    )
                    ctx = replace(
                        context(
                            user=identity.user_id,
                            conversation=identity.conversation_id,
                            thread=thread,
                            message="申请订单 order-1 退款",
                        ),
                        permission_scopes=frozenset({"orders:read", "refunds:request"}),
                    )
                    handle, view, _ = await run_to_end(runtime, ctx)
                    await runtime._records[handle.run_id].task
                    assert view.task_status == "waiting_approval"
                    paused = await graph.aget_state(
                        {"configurable": {"thread_id": thread}}, subgraphs=True
                    )
                    child = paused.tasks[0].state
                    assert child.values["context_view"]["history_ids"] == ["summary:summary-1"]
                    saved = await saver.aget_tuple(child.config)
                    assert saved.checkpoint["channel_values"]["context_view"]["input_hash"]
                    actor = LocalDemoApprovalActor().get_actor()
                    await approvals.decide(
                        approvals.row["approval_id"],
                        actor=actor,
                        decision="APPROVED",
                        expected_subject_digest=approvals.row["subject_digest"],
                    )
                    reference = ApprovalReference(approvals.row["approval_id"])
                    path = manager.store._path(archive.relative_path)
                    original = path.read_bytes()
                    try:
                        path.write_bytes(original + b"tamper")
                        with pytest.raises(RuntimeRequestError) as denied:
                            await runtime.resume_approval(reference, actor=actor)
                        assert denied.value.code == "state_unavailable"
                        assert refunds.effect_count == 0
                    finally:
                        path.write_bytes(original)
                    accepted = await runtime.resume_approval(reference, actor=actor)
                    await runtime._records[accepted.run_id].task
                    assert refunds.effect_count == 1
                    assert runtime._records[accepted.run_id].task_status == "completed"
                finally:
                    if runtime:
                        await runtime.shutdown()
                    await first_runtime.shutdown()
                    await saver.adelete_thread(thread)
                    async with pool.connection() as conn, conn.transaction():
                        for table in ("context_revision", "context_summary", "context_archive"):
                            await conn.execute(
                                f"DELETE FROM {table} WHERE user_id=%s AND conversation_id=%s",
                                (identity.user_id, identity.conversation_id),
                            )
                            assert (
                                await (
                                    await conn.execute(
                                        f"SELECT count(*) FROM {table} "
                                        "WHERE user_id=%s AND conversation_id=%s",
                                        (identity.user_id, identity.conversation_id),
                                    )
                                ).fetchone()
                            )[0] == 0
                    assert (await saver.aget_tuple({"configurable": {"thread_id": thread}})) is None

    run_async(probe())
