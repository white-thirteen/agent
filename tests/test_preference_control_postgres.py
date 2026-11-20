"""Isolated PG receipt and real PostgreSQL Store control path."""

import asyncio
import os
from uuid import uuid4

import httpx
import psycopg
import pytest
from langgraph.store.base import PutOp
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.context.models import mutation_source
from app.core.config import Settings
from app.core.errors import RuntimeRequestError
from app.infrastructure.store import StoreResource
from app.main import create_app
from app.memory.manager import MemoryManager, preference_namespace
from app.memory.models import MemoryCommand
from app.memory.reader import MemoryReader
from app.runtime.context import DemoIdentity
from app.services.preference_service import PreferenceService
from app.tools.executor import ToolExecutor
from app.tools.implementations.memory import read_preferences_tool, write_preferences_tool
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry


def test_preference_control_receipts_and_store():
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
        user = "pref231_" + uuid4().hex
        async with await psycopg.AsyncConnection.connect(dsn) as guard:
            row = await (
                await guard.execute(
                    "SELECT current_database(),current_user,current_setting('server_version_num'),"
                    "shobj_description(oid,'pg_database') FROM pg_database "
                    "WHERE datname=current_database()"
                )
            ).fetchone()
            assert row == ("agent_demo_test", "agent_test", "170012", "codex-task131-0e62")
        pool = AsyncConnectionPool(dsn, open=False, min_size=1, max_size=3)
        store_pool = AsyncConnectionPool(
            dsn,
            open=False,
            min_size=1,
            max_size=3,
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        )
        async with pool, store_pool, AsyncPostgresStore(conn=store_pool) as store:
            resource = StoreResource(store)
            manager = MemoryManager(resource, user_ids=[user])
            registry = ToolRegistry()
            registry.register(read_preferences_tool(MemoryReader(manager), enabled=True))
            registry.register(write_preferences_tool(manager, enabled=True))
            registry.freeze()
            service = PreferenceService(pool, ToolExecutor(registry, ToolPolicy()), user_ids=[user])
            identity = DemoIdentity(user, frozenset({"memory:read", "memory:write"}))
            command = MemoryCommand(operation="upsert", field="answer_language", value="en")
            try:
                assert (await service.read(identity))["revision"] is None
                await resource.abatch(
                    [
                        PutOp(
                            preference_namespace(user),
                            "profile",
                            {
                                "schema_version": 1,
                                "revision": 1,
                                "preferences": {},
                                "last_mutation": {
                                    "operation_id": "old-operation",
                                    "task_id": "old-task",
                                    "command_digest": "old-digest",
                                    "result_revision": 1,
                                    "changed_fields": [],
                                },
                            },
                        )
                    ]
                )
                old = await resource.aget(preference_namespace(user), "profile")
                assert mutation_source(old.value["last_mutation"]).task_id == "old-task"
                assert (await service.read(identity))["revision"] == 1
                original_save = service._save

                async def fail_after_write(user_id, operation_id, status, result):
                    if status == "APPLIED":
                        raise RuntimeError("simulated lost receipt")
                    await original_save(user_id, operation_id, status, result)

                service._save = fail_after_write
                with pytest.raises(RuntimeError):
                    await service.mutate(identity, "op1", 1, command)
                service._save = original_save
                with pytest.raises(RuntimeRequestError) as error:
                    await service.mutate(identity, "op2", 2, command)
                assert error.value.code == "preference_unresolved"
                recovered = await service.status(identity, "op1")
                assert recovered["status"] == "reused" and recovered["revision"] == 2
                assert (await service.mutate(identity, "op1", 1, command)) == recovered
                current = await resource.aget(preference_namespace(user), "profile")
                source = mutation_source(current.value["last_mutation"])
                assert source.kind == "preference_control" and source.command_id
                changed = MemoryCommand(operation="delete", field="answer_language")
                assert (await service.mutate(identity, "op2", 2, changed))["revision"] == 3
                assert (await service.read(identity))["preferences"] == {}
                with pytest.raises(RuntimeRequestError) as conflict:
                    await service.mutate(identity, "op1", 1, changed)
                assert conflict.value.code == "preference_conflict"
                read_only = DemoIdentity(user, frozenset({"memory:read"}))
                with pytest.raises(RuntimeRequestError) as denied:
                    await service.mutate(read_only, "op3", 3, command)
                assert denied.value.code == "preference_scope_denied"

                original_batch = resource.abatch

                async def uncertain_put(operations):
                    if any(isinstance(operation, PutOp) for operation in operations):
                        raise TimeoutError()
                    return await original_batch(operations)

                resource.abatch = uncertain_put
                assert (await service.mutate(identity, "op3", 3, command))["status"] == "unknown"
                resource.abatch = original_batch
                assert (await service.status(identity, "op3"))["status"] == "unknown"
                with pytest.raises(RuntimeRequestError) as blocked:
                    await service.mutate(identity, "op4", 3, command)
                assert blocked.value.code == "preference_unresolved"
            finally:
                await resource.abatch([PutOp(preference_namespace(user), "profile", None)])
                async with pool.connection() as conn:
                    await conn.execute(
                        "DELETE FROM preference_command_receipt WHERE user_id=%s", (user,)
                    )
                    assert (
                        await (
                            await conn.execute(
                                "SELECT count(*) FROM preference_command_receipt WHERE user_id=%s",
                                (user,),
                            )
                        ).fetchone()
                    )[0] == 0
                assert await resource.aget(preference_namespace(user), "profile") is None

    asyncio.run(probe())


def test_http_preferences_without_model():
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
        async with await psycopg.AsyncConnection.connect(dsn) as guard:
            row = await (
                await guard.execute(
                    "SELECT current_database(),current_user,current_setting('server_version_num'),"
                    "shobj_description(oid,'pg_database') FROM pg_database "
                    "WHERE datname=current_database()"
                )
            ).fetchone()
            assert row == ("agent_demo_test", "agent_test", "170012", "codex-task131-0e62")
        user = "prefhttp_" + uuid4().hex
        settings = Settings(
            _env_file=None,
            app_env="test",
            database_url=dsn,
            model_name=None,
            model_base_url=None,
            model_api_key=None,
            demo_user_ids=(user,),
        )
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            assert app.state.model_gateway is None
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post("/agent/preferences/read", json={"user_id": user})
                    assert response.status_code == 200 and response.json()["revision"] is None
                    payload = {
                        "user_id": user,
                        "operation_id": "http-op",
                        "expected_revision": 0,
                        "command": {
                            "operation": "upsert",
                            "field": "answer_style",
                            "value": "concise",
                        },
                    }
                    response = await client.post("/agent/preferences/mutations", json=payload)
                    assert response.status_code == 200 and response.json()["revision"] == 1
                    response = await client.post(
                        "/agent/preferences/operations/http-op/status", json={"user_id": user}
                    )
                    assert response.status_code == 200 and response.json()["status"] == "applied"
            finally:
                await app.state.memory_store.abatch(
                    [PutOp(preference_namespace(user), "profile", None)]
                )
                async with app.state.pool.connection() as conn:
                    await conn.execute(
                        "DELETE FROM preference_command_receipt WHERE user_id=%s", (user,)
                    )
                    assert (
                        await (
                            await conn.execute(
                                "SELECT count(*) FROM preference_command_receipt WHERE user_id=%s",
                                (user,),
                            )
                        ).fetchone()
                    )[0] == 0
                assert (
                    await app.state.memory_store.aget(preference_namespace(user), "profile") is None
                )

    asyncio.run(probe())
