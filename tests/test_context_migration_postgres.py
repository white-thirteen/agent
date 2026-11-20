"""Recover simulated V1 metadata from a real Saver without rewriting old snapshots."""

import os
from uuid import uuid4

import psycopg
import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from runtime_support import ControlledModel, compiled, context, run_to_end

from app.context.archive_store import ArchiveStore
from app.context.manager import ContextManager
from app.context.migration import recover_public_metadata
from app.context.repository import ContextRepository
from app.graph.contracts import SupervisorOutput
from app.infrastructure.checkpoint import checkpoint_serializer
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from scripts import run_async


def test_legacy_snapshot_recovery_keeps_checkpoint_and_is_reentrant(tmp_path):
    dsn = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated database not configured")
    info = conninfo_to_dict(dsn)
    assert (info["host"], info["port"], info["dbname"], info["user"]) == (
        "127.0.0.1",
        "56431",
        "agent_demo_test",
        "agent_test",
    )

    async def probe():
        async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as guard:
            row = await (
                await guard.execute(
                    "SELECT current_setting('server_version_num'),"
                    "shobj_description(oid,'pg_database') FROM pg_database "
                    "WHERE datname=current_database()"
                )
            ).fetchone()
            assert row == ("170012", "codex-task131-0e62")
        token = uuid4().hex
        user, conversation, thread = "ctx232-" + token, "conv-" + token, str(uuid4())
        async with AsyncConnectionPool(
            dsn,
            open=False,
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        ) as pool:
            saver = AsyncPostgresSaver(pool, serde=checkpoint_serializer())
            graph = compiled(
                ControlledModel([SupervisorOutput(kind="unsupported")] * 2), saver=saver
            )
            runtime = AgentRuntime(graph, run_limits=RunLimits(10, 12))
            config = {"configurable": {"thread_id": thread}}
            try:
                handle, _, _ = await run_to_end(
                    runtime,
                    context(
                        user=user, conversation=conversation, thread=thread, message="old message"
                    ),
                )
                await runtime._records[handle.run_id].task
                await graph.aupdate_state(
                    config, {"public_message_metadata": {}}, as_node="run_finish"
                )
                before = await graph.aget_state(config)
                assert not before.values["public_message_metadata"]
                first = await recover_public_metadata(
                    graph, thread, user, conversation, before.values
                )
                second = await recover_public_metadata(
                    graph, thread, user, conversation, before.values
                )
                assert first == second
                assert first[1] == "complete"
                assert set(first[0]) == set(before.values["task_message_ids"])
                after = await graph.aget_state(config)
                assert after.config == before.config and after.values == before.values
                unknown = HumanMessage(content="untrusted old approval", id="unknown-" + token)
                await graph.aupdate_state(config, {"messages": [unknown]}, as_node="run_finish")
                mixed = await graph.aget_state(config)
                runtime._context_manager = ContextManager(
                    ContextRepository(pool), ArchiveStore(tmp_path)
                )
                new_handle, _, _ = await run_to_end(
                    runtime,
                    context(user=user, conversation=conversation, thread=thread, message="new"),
                )
                await runtime._records[new_handle.run_id].task
                current = await graph.aget_state(config)
                assert current.values["context_migration_status"] == "incomplete"
                assert all(mid in current.values["public_message_metadata"] for mid in first[0])
                assert unknown in current.values["messages"]
                assert unknown.id not in current.values["public_message_metadata"]
                original = await graph.aget_state(mixed.config)
                assert original.values == mixed.values
            finally:
                await runtime.shutdown()
                await saver.adelete_thread(thread)
                assert await saver.aget_tuple(config) is None

    run_async(probe())
