"""Real PG Store/Saver, exact owned fixtures, new-process persistence and cancellation."""

import asyncio
import json
import os
import sys
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp
from pydantic import SecretStr
from runtime_support import ControlledModel, context, route, run_to_end
from test_memory_reader import profile

from app.agents.types import AgentType, TaskType
from app.core.config import Settings
from app.graph.builder import build_supervisor_graph
from app.graph.specialists.order.builder import build_order_graph
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.postgres import open_pool, validate_test_target
from app.infrastructure.store import store_resources
from app.memory.manager import MemoryManager, preference_namespace
from app.memory.reader import MemoryReader
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from app.runtime.models import RunLimits
from app.tools.executor import ToolExecutor
from app.tools.implementations.memory import read_preferences_tool
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from scripts import run_async
from scripts.migrate import MIGRATIONS_DIR, migration_files
from scripts.setup_store import setup_store


async def database_snapshot(pool):
    """Full existing public row sets, identity, migration checksums and column definitions."""
    async with pool.connection() as conn:
        assert await (await conn.execute("SELECT current_database(),current_user")).fetchone() == (
            "agent_demo_test",
            "agent_test",
        )
        applied = dict(
            await (
                await conn.execute(
                    "SELECT version,checksum FROM schema_migrations ORDER BY version"
                )
            ).fetchall()
        )
        assert applied == {v: item[0] for v, item in migration_files(MIGRATIONS_DIR).items()}
        tables = [
            row[0]
            for row in await (
                await conn.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
                )
            ).fetchall()
        ]
        result = {}
        for table in tables:
            rows = await (
                await conn.execute(
                    psycopg.sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY 1").format(
                        psycopg.sql.Identifier(table)
                    )
                )
            ).fetchall()
            columns = await (
                await conn.execute(
                    "SELECT column_name,data_type,is_nullable,column_default "
                    "FROM information_schema.columns WHERE table_schema='public' AND table_name=%s "
                    "ORDER BY ordinal_position",
                    (table,),
                )
            ).fetchall()
            result[table] = (rows, columns)
        return result


def test_real_store_cross_threads_process_persistence_and_exact_cleanup():
    raw = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Explicit test database required")
    secret = SecretStr(raw)
    validate_test_target(secret, Settings().database_url)
    identifier = "store-reader-" + uuid4().hex
    users = (identifier + "-a", identifier + "-b")
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=secret,
        test_database_url=secret,
        demo_user_ids=users,
    )

    async def scenario():
        pool = await open_pool(settings)
        before_setup = await database_snapshot(pool)
        # Only public framework setup, with online target/checksum verification.
        await setup_store(
            target="test",
            settings=settings.model_copy(update={"database_url": Settings().database_url}),
        )
        after_setup = await database_snapshot(pool)
        assert all(after_setup[table] == data for table, data in before_setup.items())
        before = after_setup
        checkpoint_pool = await open_checkpoint_pool(settings)
        saver = AsyncPostgresSaver(checkpoint_pool, serde=checkpoint_serializer())
        threads = [identifier + f"-thread-{i}" for i in range(3)]
        runtime = None
        try:
            async with store_resources(settings) as resource:
                manager = MemoryManager(resource, user_ids=users)
                assert (await manager.snapshot(user_id=users[0])).status == "empty"
                # Fixture only; no user-facing save or MemoryManager.apply exists.
                await resource.abatch(
                    [
                        PutOp(
                            preference_namespace(users[0]),
                            "profile",
                            profile(answer_language="en", answer_style="concise"),
                        )
                    ]
                )
                registry = ToolRegistry()
                registry.register(read_preferences_tool(MemoryReader(manager), enabled=True))
                registry.freeze()
                executor = ToolExecutor(registry, ToolPolicy())
                supervisor = ModelGateway(
                    ControlledModel(
                        [
                            route(TaskType.ORDER_QUERY, entities={"query_kind": "get"})
                            for _ in range(4)
                        ]
                    ),
                    ModelCallLimits(8, 5, 0),
                )
                child = build_order_graph(gateway=None, registry=registry, executor=executor)
                graph = build_supervisor_graph(
                    gateway=supervisor,
                    checkpointer=saver,
                    specialists={
                        AgentType.ORDER: child,
                        AgentType.REFUND: child,
                        AgentType.KNOWLEDGE: child,
                    },
                )
                runtime = AgentRuntime(graph, run_limits=RunLimits(30, 12))
                snapshots = []
                contexts = []
                for index, user in enumerate((users[0], users[0], users[1])):
                    ctx = replace(
                        context(
                            user=user,
                            conversation=identifier + f"-conv-{index}",
                            thread=threads[index],
                            message="查询订单",
                        ),
                        permission_scopes=frozenset({"orders:read", "memory:read"}),
                    )
                    contexts.append(ctx)
                    _, view, _ = await run_to_end(runtime, ctx)
                    assert view.task_status == "needs_input" and view.run_usage.tool_calls == 1
                    saved = await graph.aget_state({"configurable": {"thread_id": ctx.thread_id}})
                    record = saved.values["memory_read_record"]
                    snapshots.append(record)
                    assert record["result"]["attempts"] == 1
                    assert not any(
                        getattr(message, "tool_calls", None) for message in saved.values["messages"]
                    )
                assert snapshots[0]["result"]["data"]["preferences"] == {
                    "answer_language": "en",
                    "answer_style": "concise",
                }
                assert snapshots[1]["result"]["data"] == snapshots[0]["result"]["data"]
                assert snapshots[2]["result"]["data"]["status"] == "empty"
                assert snapshots[2]["result"]["data"]["preferences"] == {}
                # Real Saver reload and same Task clarification reuse the read record/usage.
                _, continued, _ = await run_to_end(
                    runtime, replace(contexts[0], run_id=str(uuid4()))
                )
                assert (
                    continued.task_status == "needs_input" and continued.run_usage.tool_calls == 1
                )
                persisted = await graph.aget_state({"configurable": {"thread_id": threads[0]}})
                assert persisted.values["memory_read_record"] == snapshots[0]
                await runtime.shutdown()
                runtime = None
            # A fresh Store pool and a complete new interpreter see the committed profile.
            code = """import json,os
from app.core.config import Settings
from app.infrastructure.store import store_resources
from app.memory.manager import MemoryManager
from scripts import run_async
async def main():
 s=Settings().model_copy(update={"database_url":Settings().test_database_url})
 async with store_resources(s) as r:
  user=os.environ["STORE_PROBE_USER"]
  result=await MemoryManager(r,user_ids=(user,)).snapshot(user_id=user)
  print(result.model_dump_json())
run_async(main())"""
            env = {**os.environ, "STORE_PROBE_USER": users[0]}
            import subprocess

            process = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-c", code],
                env=env,
                capture_output=True,
                timeout=30,
            )
            assert process.returncode == 0, (
                "New-process Store probe failed (private stderr withheld)"
            )
            result = json.loads(process.stdout)
            assert result == snapshots[0]["result"]["data"]
            assert not process.stderr
            # Caller cancellation propagates; subsequent exact read remains valid.
            async with store_resources(settings) as resource:
                task = asyncio.create_task(resource.aget(preference_namespace(users[0]), "profile"))
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert (
                    await MemoryManager(resource, user_ids=users).snapshot(user_id=users[0])
                ).preferences["answer_language"] == "en"
            # Observe real connection ownership on normal, exceptional and cancelled exits.
            from psycopg.conninfo import make_conninfo

            identified = settings.model_copy(
                update={
                    "database_url": SecretStr(
                        make_conninfo(secret.get_secret_value(), application_name=identifier)
                    )
                }
            )

            async def active_connections():
                async with pool.connection() as conn:
                    row = await (
                        await conn.execute(
                            "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s",
                            (identifier,),
                        )
                    ).fetchone()
                    return row[0]

            class DeliberateExit(Exception):
                pass

            for exceptional in (False, True):
                try:
                    async with store_resources(identified) as resource:
                        await resource.aget(preference_namespace(users[0]), "profile")
                        assert await active_connections() >= 1
                        if exceptional:
                            raise DeliberateExit()
                except DeliberateExit:
                    assert exceptional
                assert await active_connections() == 0
            entered = asyncio.Event()

            async def cancelled_owner():
                async with store_resources(identified) as resource:
                    await resource.aget(preference_namespace(users[0]), "profile")
                    entered.set()
                    await asyncio.Event().wait()

            owner = asyncio.create_task(cancelled_owner())
            await entered.wait()
            owner.cancel()
            with pytest.raises(asyncio.CancelledError):
                await owner
            assert await active_connections() == 0
        finally:
            if runtime is not None:
                await runtime.shutdown()
            for thread in threads:
                await saver.adelete_thread(thread)
            async with store_resources(settings) as resource:
                await resource.abatch([PutOp(preference_namespace(users[0]), "profile", None)])
            assert await database_snapshot(pool) == before
            await checkpoint_pool.close()
            await pool.close()

    run_async(scenario())


def test_real_nonobject_profile_is_safe_optional_order_failure(caplog):
    """05-QA-001: Store 3.2.0 decodes JSONB before Manager can inspect Item.value."""
    from test_memory_reader import setup

    from app.graph.transfers import create_specialist_state

    raw = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Explicit test database required")
    secret = SecretStr(raw)
    validate_test_target(secret, Settings().database_url)
    user = "store-corrupt-regression-" + uuid4().hex
    settings = Settings(_env_file=None, app_env="test", database_url=secret, demo_user_ids=(user,))

    async def scenario():
        pool = await open_pool(settings)
        before = await database_snapshot(pool)
        namespace = preference_namespace(user)
        try:
            async with store_resources(settings) as resource:
                await resource.abatch([PutOp(namespace, "profile", profile())])
                # Corrupt only this owned fixture, using the actual psycopg JSONB path.
                async with pool.connection() as conn:
                    cursor = await conn.execute(
                        "UPDATE store SET value='[]'::jsonb WHERE prefix=%s AND key=%s",
                        (".".join(namespace), "profile"),
                    )
                    assert cursor.rowcount == 1
                registry = ToolRegistry()
                registry.register(
                    read_preferences_tool(
                        MemoryReader(MemoryManager(resource, user_ids=(user,))), enabled=True
                    )
                )
                registry.freeze()
                graph = build_order_graph(
                    gateway=None, registry=registry, executor=ToolExecutor(registry, ToolPolicy())
                )
                _, _, _, live, state = setup(resource)
                ctx = live.context.context.model_copy(update={"user_id": user})
                live.context = replace(live.context, context=ctx)
                request = state["request"].model_copy(update={"context": ctx, "messages": []})
                result = await graph.ainvoke(
                    create_specialist_state(request, scope=live.context.scope),
                    context=live.context,
                )
                assert result["result"].status == "needs_input"
                assert result["memory_read_status"] == "unavailable"
                assert result["memory_context"] == {} and not result["messages"]
                read = result["memory_read_record"]["result"]
                assert read["status"] == "failed" and read["code"] == "memory_profile_invalid"
                assert read["attempts"] == 1 and read["data"] is None
                assert read["message"] == "Tool execution unavailable."
                assert live.context.scope.run_usage().tool_calls == 1
                assert live.context.scope.model_usage().model_attempts == 0
                assert "JSONDecodeError" not in caplog.text and "Input must be" not in caplog.text
        finally:
            async with store_resources(settings) as resource:
                await resource.abatch([PutOp(namespace, "profile", None)])
            assert await database_snapshot(pool) == before
            await pool.close()

    run_async(scenario())
