"""Real isolated Saver/PG/files with a controlled maintenance model."""

import asyncio
import os
from uuid import uuid4

import psycopg
import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from runtime_support import ControlledModel, compiled, context, run_to_end

from app.context.archive_store import ArchiveStore
from app.context.manager import ContextManager
from app.context.models import SessionIdentity
from app.context.repository import ContextRepository
from app.core.config import Settings
from app.core.errors import RuntimeRequestError
from app.graph.contracts import SupervisorOutput
from app.infrastructure.checkpoint import checkpoint_serializer
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from app.runtime.context import SubmitOptions
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from scripts import run_async


class SummaryModel:
    def __init__(self, *, fail_first=False):
        self.calls = 0
        self.fail_first = fail_first
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    def bind(self, **kwargs):
        assert kwargs == {"max_tokens": 128, "temperature": 0}
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        self.started.set()
        await self.release.wait()
        if self.fail_first:
            self.fail_first = False
            raise TimeoutError()
        return AIMessage(
            content="Earlier request was unsupported.",
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 8,
                "total_tokens": 18,
            },
        )


@pytest.mark.parametrize("fail_first", [False, True])
def test_completed_run_registers_and_publishes_without_rewriting_checkpoint(tmp_path, fail_first):
    dsn = os.environ.get("AGENT_TEST_DATABASE_URL")
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
        identity = SessionIdentity(user_id="ctx231-" + token, conversation_id="conv-" + token)
        thread = str(uuid4())
        settings = Settings(
            _env_file=None,
            model_name="controlled",
            context_model_window_tokens=10000,
            context_model_output_tokens=1024,
            context_summary_output_tokens=128,
            context_archive_read_tokens=4096,
            context_archive_retain_interactions=0,
        )
        async with AsyncConnectionPool(dsn, open=False) as pool:
            async with AsyncConnectionPool(
                dsn,
                open=False,
                kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
            ) as saver_pool:
                saver = AsyncPostgresSaver(saver_pool, serde=checkpoint_serializer())
                repo = ContextRepository(pool)
                manager = ContextManager(repo, ArchiveStore(tmp_path))
                graph = compiled(
                    ControlledModel([SupervisorOutput(kind="unsupported")] * 2), saver=saver
                )
                model = SummaryModel(fail_first=fail_first)
                gateway = ModelGateway(model, ModelCallLimits(8, 5, 0))
                runtime = AgentRuntime(
                    graph,
                    run_limits=RunLimits(10, 12),
                    context_manager=manager,
                    context_settings=settings,
                    context_gateway=gateway,
                )
                original_register = repo.register_maintenance
                registered = []

                async def register_under_claim(*args, **kwargs):
                    if not registered:
                        assert thread in runtime._claims
                        record = runtime._records[kwargs["source_run_id"]]
                        assert record.ended_at is not None and record.run_status == "completed"
                    result = await original_register(*args, **kwargs)
                    if not registered:
                        registered.append(result["status"])
                    return result

                repo.register_maintenance = register_under_claim
                try:
                    handle, view, _ = await run_to_end(
                        runtime,
                        context(
                            user=identity.user_id,
                            conversation=identity.conversation_id,
                            thread=thread,
                        ),
                    )
                    await runtime._records[handle.run_id].task
                    assert registered == ["PENDING"]
                    await asyncio.wait_for(model.started.wait(), timeout=5)
                    assert view.task_status == "rejected"
                    with pytest.raises(RuntimeRequestError) as busy:
                        await runtime.submit(
                            context(
                                user=identity.user_id,
                                conversation=identity.conversation_id,
                                thread=thread,
                            ),
                            options=SubmitOptions(),
                        )
                    assert busy.value.code == "thread_busy"
                    model.release.set()
                    await asyncio.gather(*tuple(runtime._maintenance.tasks))
                    if fail_first:
                        async with pool.connection() as conn:
                            work = await (
                                await conn.execute(
                                    "SELECT maintenance_id,status,reserved_attempts "
                                    "FROM context_maintenance "
                                    "WHERE user_id=%s",
                                    (identity.user_id,),
                                )
                            ).fetchone()
                        assert work[1:] == ("FAILED", 1)
                        async with await psycopg.AsyncConnection.connect(
                            dsn, autocommit=True
                        ) as old:
                            await old.execute(
                                "SELECT pg_advisory_lock(hashtextextended(%s,231))", (work[0],)
                            )
                            await repo.claim_maintenance(work[0])
                            runtime._maintenance.schedule(work[0], thread)
                            await asyncio.gather(*tuple(runtime._maintenance.tasks))
                            assert (await repo.maintenance(work[0]))["status"] == "RUNNING"
                            await old.execute(
                                "SELECT pg_advisory_unlock(hashtextextended(%s,231))", (work[0],)
                            )
                        runtime._maintenance.schedule(work[0], thread)
                        await asyncio.gather(*tuple(runtime._maintenance.tasks))
                    assert view.task_status == "rejected" and model.calls == (
                        2 if fail_first else 1
                    )
                    revision = await repo.get_revision(identity, 1)
                    assert revision is not None and revision.status == "PUBLISHED"
                    ref = {"revision": 1, "summary_id": revision.summary_id}
                    await runtime._verify_bound_history(
                        identity.user_id, identity.conversation_id, ref, []
                    )
                    archive = await repo.get(identity, revision.archive_refs[0])
                    path = manager.store._path(archive.relative_path)
                    original = path.read_bytes()
                    try:
                        path.write_bytes(original + b"tamper")
                        with pytest.raises(ValueError, match="integrity"):
                            await runtime._verify_bound_history(
                                identity.user_id, identity.conversation_id, ref, []
                            )
                    finally:
                        path.write_bytes(original)
                    snapshot = await graph.aget_state({"configurable": {"thread_id": thread}})
                    assert (
                        not snapshot.values.get("context_ref")
                        and len(snapshot.values["messages"]) == 2
                    )
                    async with pool.connection() as conn:
                        work = await (
                            await conn.execute(
                                "SELECT status,reserved_attempts,revision "
                                "FROM context_maintenance WHERE user_id=%s",
                                (identity.user_id,),
                            )
                        ).fetchone()
                        assert work == ("SUCCEEDED", 2 if fail_first else 1, 1)
                    if not fail_first:
                        # Recover the association before and after real Graph adoption,
                        # including an expired maintenance budget and repeated replay.
                        async with pool.connection() as conn:
                            work_id = (
                                await (
                                    await conn.execute(
                                        "SELECT maintenance_id FROM context_maintenance "
                                        "WHERE user_id=%s",
                                        (identity.user_id,),
                                    )
                                ).fetchone()
                            )[0]
                            await conn.execute(
                                "UPDATE context_maintenance SET revision=NULL, "
                                "deadline_at=clock_timestamp()-interval '1 second' "
                                "WHERE maintenance_id=%s",
                                (work_id,),
                            )
                        source_checkpoint = snapshot.config
                        deadline = (await repo.maintenance(work_id))["deadline_at"]
                        attempts = await repo.attempts(work_id)
                        try:
                            path.write_bytes(original + b"tamper")
                            await runtime._maintenance._run(work_id, thread)
                            blocked = await repo.maintenance(work_id)
                            assert blocked["revision"] is None and blocked["reserved_attempts"] == 1
                            assert model.calls == 1
                        finally:
                            path.write_bytes(original)
                        await runtime._maintenance._run(work_id, thread)
                        repaired = await repo.maintenance(work_id)
                        assert repaired["revision"] == 1 and repaired["reserved_attempts"] == 1
                        assert repaired["deadline_at"] == deadline
                        assert (await repo.get_revision(identity, 1)).status == "PUBLISHED"
                        assert (
                            await graph.aget_state({"configurable": {"thread_id": thread}})
                        ).config == source_checkpoint
                        assert model.calls == 1

                        async with pool.connection() as conn:
                            await conn.execute(
                                "UPDATE context_maintenance SET revision=NULL "
                                "WHERE maintenance_id=%s",
                                (work_id,),
                            )
                        old_settings = runtime._maintenance.settings
                        runtime._maintenance.settings = settings.model_copy(
                            update={"context_summary_output_tokens": None}
                        )
                        second, _, _ = await run_to_end(
                            runtime,
                            context(
                                user=identity.user_id,
                                conversation=identity.conversation_id,
                                thread=thread,
                                message="next request",
                            ),
                        )
                        await runtime._records[second.run_id].task
                        runtime._maintenance.settings = old_settings
                        adopted = await graph.aget_state({"configurable": {"thread_id": thread}})
                        assert adopted.values["context_ref"] == ref
                        assert (await repo.get_revision(identity, 1)).status == "APPLIED"
                        async with pool.connection() as conn:
                            await conn.execute(
                                "UPDATE context_revision SET policy_version='mismatch' "
                                "WHERE user_id=%s AND conversation_id=%s AND revision=1",
                                (identity.user_id, identity.conversation_id),
                            )
                        try:
                            await runtime._maintenance._run(work_id, thread)
                            assert (await repo.maintenance(work_id))["revision"] is None
                            assert model.calls == 1
                        finally:
                            async with pool.connection() as conn:
                                await conn.execute(
                                    "UPDATE context_revision SET policy_version='context-v2-231' "
                                    "WHERE user_id=%s AND conversation_id=%s AND revision=1",
                                    (identity.user_id, identity.conversation_id),
                                )
                        await runtime._maintenance._run(work_id, thread)
                        await runtime._maintenance._run(work_id, thread)
                        repeated = await graph.aget_state({"configurable": {"thread_id": thread}})
                        assert (
                            repeated.config == adopted.config and repeated.values == adopted.values
                        )
                        assert model.calls == 1
                        repaired = await repo.maintenance(work_id)
                        assert repaired["status"] == "SUCCEEDED" and repaired["revision"] == 1
                        assert repaired["reserved_attempts"] == 1
                        assert repaired["deadline_at"] == deadline
                        assert await repo.attempts(work_id) == attempts
                        assert (await repo.get_revision(identity, 1)).status == "APPLIED"

                        # Old exhausted rows must not occupy the bounded recovery
                        # selection ahead of live work; a ready Summary remains eligible.
                        async with pool.connection() as conn:
                            source = await (
                                await conn.execute(
                                    "SELECT maintenance_id FROM context_maintenance "
                                    "WHERE user_id=%s",
                                    (identity.user_id,),
                                )
                            ).fetchone()
                            await conn.execute(
                                "INSERT INTO sessions(user_id,conversation_id,thread_id) "
                                "VALUES (%s,%s,%s)",
                                (identity.user_id, identity.conversation_id, thread),
                            )
                            for suffix, status, interval, same_source in (
                                ("expired", "PENDING", "-10 seconds", False),
                                ("dead", "EXHAUSTED", "-9 seconds", False),
                                ("ready", "EXHAUSTED", "-8 seconds", True),
                                ("live", "PENDING", "20 seconds", False),
                            ):
                                await conn.execute(
                                    "INSERT INTO context_maintenance (maintenance_id,user_id,"
                                    "conversation_id,source_task_id,source_run_id,source_checkpoint_id,"
                                    "message_ids,content_hash,policy_version,budget_version,"
                                    "max_input_tokens,max_output_tokens,archive_refs,"
                                    "deadline_at,status) "
                                    "SELECT %s,user_id,conversation_id,source_task_id,"
                                    "source_run_id,source_checkpoint_id,"
                                    "CASE WHEN %s THEN message_ids ELSE ARRAY['other'] END,"
                                    "%s,policy_version,budget_version,max_input_tokens,max_output_tokens,"
                                    "CASE WHEN %s THEN archive_refs ELSE ARRAY['other'] END,"
                                    "clock_timestamp()+%s::interval,%s FROM context_maintenance "
                                    "WHERE maintenance_id=%s",
                                    (
                                        suffix + token,
                                        same_source,
                                        suffix + token,
                                        same_source,
                                        interval,
                                        status,
                                        source[0],
                                    ),
                                )
                        captured = []
                        runtime._maintenance.settings = settings.model_copy(
                            update={"runtime_max_active_runs": 1}
                        )
                        runtime._maintenance.schedule = lambda work_id, thread_id: captured.append(
                            work_id
                        )
                        await runtime._maintenance.resume_pending()
                        assert captured == ["ready" + token]
                        async with pool.connection() as conn:
                            await conn.execute(
                                "UPDATE context_maintenance SET revision=1 WHERE maintenance_id=%s",
                                ("ready" + token,),
                            )
                            expired = await (
                                await conn.execute(
                                    "SELECT status FROM context_maintenance "
                                    "WHERE maintenance_id=%s",
                                    ("expired" + token,),
                                )
                            ).fetchone()
                            assert expired[0] == "EXHAUSTED"
                        captured.clear()
                        await runtime._maintenance.resume_pending()
                        assert captured == ["live" + token]
                finally:
                    await runtime.shutdown()
                    await saver.adelete_thread(thread)
                    async with pool.connection() as conn, conn.transaction():
                        await conn.execute(
                            "DELETE FROM sessions WHERE user_id=%s AND conversation_id=%s",
                            (identity.user_id, identity.conversation_id),
                        )
                        await conn.execute(
                            "DELETE FROM context_maintenance_attempt WHERE maintenance_id IN "
                            "(SELECT maintenance_id FROM context_maintenance WHERE user_id=%s)",
                            (identity.user_id,),
                        )
                        for table in (
                            "context_maintenance",
                            "context_revision",
                            "context_summary",
                            "context_archive",
                        ):
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
