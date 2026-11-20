"""Real isolated PostgreSQL; controlled provider, real LangMem and archive files."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import openai
import psycopg
import pytest
from langchain_core.messages import AIMessage
from langchain_core.messages.utils import count_tokens_approximately
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import AsyncConnectionPool

from app.agents.types import AgentType
from app.context.archive_store import ArchiveStore
from app.context.compaction import SUMMARY_PROMPT_VERSION, CompactionError
from app.context.manager import ContextManager
from app.context.models import PublicInteraction, PublicMessage, SessionIdentity
from app.context.repository import ContextRepository
from app.core.config import Settings
from app.runtime.model_gateway import (
    ModelCallContext,
    ModelCallError,
    ModelCallLimits,
    ModelCallUsage,
    ModelGateway,
    UsageReport,
)
from app.runtime.models import RunLimits, RunUsage
from app.runtime.run_scope import RunScope
from scripts import run_async


class ControlledModel:
    def __init__(self):
        self.calls = 0
        self.fail = True
        self.truncate = False

    def bind(self, **kwargs):
        assert kwargs == {"max_tokens": 128, "temperature": 0}
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.fail:
            raise openai.APIConnectionError(request=httpx.Request("POST", "https://test.invalid"))
        return AIMessage(
            content="A concise summary.",
            response_metadata={"finish_reason": "length" if self.truncate else "stop"},
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 3,
                "total_tokens": 13,
            },
        )


def test_compaction_postgres(tmp_path):
    dsn = os.environ.get("CONTEXT_ARCHIVE_TEST_DSN")
    if not dsn:
        pytest.skip("dedicated PostgreSQL probe not configured")
    parts = conninfo_to_dict(dsn)
    assert parts.get("host") == "127.0.0.1" and parts.get("port") == "56422"

    async def probe():
        schema = "ctx221_" + uuid4().hex
        async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as admin:
            row = await (
                await admin.execute(
                    "SELECT current_database(), current_user, "
                    "current_setting('server_version_num'), "
                    "shobj_description(oid,'pg_database') FROM pg_database "
                    "WHERE datname=current_database()"
                )
            ).fetchone()
            assert row == (
                "agent_context_test",
                "agent_test",
                "170012",
                "codex-v202-local-20261119",
            )
            await admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                await admin.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                for migration in ("008_context_archive.sql", "009_context_compaction.sql"):
                    await admin.execute(Path("migrations", migration).read_text(encoding="utf-8"))
                pool = AsyncConnectionPool(
                    dsn,
                    kwargs={"options": f"-csearch_path={schema}"},
                    open=False,
                    min_size=1,
                    max_size=4,
                )
                async with pool:
                    repo = ContextRepository(pool)
                    manager = ContextManager(repo, ArchiveStore(tmp_path))
                    ident = SessionIdentity(user_id="u:221", conversation_id="c:221")
                    interaction = PublicInteraction(
                        task_id="t",
                        task_status="COMPLETED",
                        messages=(
                            PublicMessage(
                                message_id="u1",
                                role="user",
                                content="The number is 42.",
                                task_id="t",
                            ),
                            PublicMessage(
                                message_id="a1", role="assistant", content="Noted.", task_id="t"
                            ),
                        ),
                    )
                    archive = await manager.publish(
                        ident,
                        "cp",
                        [interaction],
                        retain_recent=0,
                        max_messages=2,
                        session_status="COMPLETED",
                    )
                    model = ControlledModel()
                    kwargs = dict(
                        archive_refs=(archive.archive_ref,),
                        parent_summary_id=None,
                        source_checkpoint_id="cp",
                        version=1,
                        policy_version="p1",
                        model_version="m1",
                        prompt_version=SUMMARY_PROMPT_VERSION,
                        max_bytes=10000,
                        gateway=ModelGateway(model, ModelCallLimits(8, 5, 0)),
                        token_counter=count_tokens_approximately,
                        max_input_tokens=4096,
                        max_output_tokens=128,
                        settings=Settings(
                            model_name="m1",
                            context_model_window_tokens=8192,
                            context_model_output_tokens=128,
                        ),
                    )
                    maint = dict(
                        maintenance_id="m1",
                        source_task_id="t",
                        source_run_id="r",
                        budget_version="b1",
                    )
                    truncated = ControlledModel()
                    truncated.fail = False
                    truncated.truncate = True
                    with pytest.raises(CompactionError) as failure:
                        await manager.compact(
                            ident,
                            maintenance={**maint, "maintenance_id": "truncated"},
                            **{
                                **kwargs,
                                "policy_version": "truncated",
                                "gateway": ModelGateway(truncated, ModelCallLimits(8, 5, 0)),
                            },
                        )
                    assert failure.value.model_usage.model_attempts == 1
                    assert failure.value.reports[0].output_tokens == 3
                    assert (await repo.maintenance("truncated"))["status"] == "FAILED"
                    assert (await repo.get(ident, archive.archive_ref)).status == "READY"
                    async with pool.connection() as connection:
                        assert (
                            await (
                                await connection.execute(
                                    "SELECT count(*) FROM context_summary "
                                    "WHERE policy_version='truncated'"
                                )
                            ).fetchone()
                        )[0] == 0
                    with pytest.raises(ValueError, match="limits"):
                        await manager.compact(
                            ident,
                            maintenance=maint,
                            **{
                                **kwargs,
                                "settings": Settings(
                                    model_name="m1",
                                    context_model_window_tokens=None,
                                    context_model_output_tokens=None,
                                ),
                            },
                        )
                    with pytest.raises(ValueError, match="limits"):
                        await manager.compact(
                            ident,
                            maintenance=maint,
                            **{**kwargs, "max_output_tokens": 129},
                        )
                    with pytest.raises(ModelCallError):
                        await manager.compact(ident, maintenance=maint, **kwargs)
                    assert (await repo.get(ident, archive.archive_ref)).status == "READY"
                    first = await repo.maintenance("m1")
                    assert first["reserved_attempts"] == 1 and first["status"] == "FAILED"
                    actual, usage = await repo.maintenance_usage("m1")
                    assert actual == 1 and usage.status == "unknown" and usage.total_tokens is None
                    model.fail = False
                    summary, reports = await manager.compact(
                        ident, maintenance={**maint, "maintenance_id": "different"}, **kwargs
                    )
                    assert model.calls == 2 and len(reports) == 1
                    assert summary.message_ids == ("u1", "a1")
                    assert (await repo.maintenance("m1"))["status"] == "SUCCEEDED"
                    assert await repo.maintenance("different") is None
                    assert (await manager.compact(ident, maintenance=maint, **kwargs))[0] == summary
                    assert model.calls == 2
                    with pytest.raises(ValueError, match="coverage"):
                        await repo.save_summary(
                            summary.model_copy(update={"message_ids": ("u1",)}),
                            source_checkpoint_id="cp",
                            policy_version="p1",
                            model_version="m1",
                            prompt_version=SUMMARY_PROMPT_VERSION,
                        )
                    with pytest.raises(ValueError, match="unavailable"):
                        await manager.compact(
                            ident,
                            maintenance={**maint, "maintenance_id": "new-version"},
                            **{**kwargs, "version": 2},
                        )
                    assert await repo.maintenance("new-version") is None
                    scope = RunScope(
                        limits=RunLimits(active_timeout_seconds=10, max_tool_calls=5),
                        model_usage=ModelCallUsage(3),
                        run_usage=RunUsage(),
                    )
                    scope.start_active_period()
                    run_summary, run_reports = await manager.compact(
                        ident,
                        run_scope=scope,
                        run_context=ModelCallContext("run", "task", AgentType.SUPERVISOR),
                        execution_mode="normal",
                        **{**kwargs, "policy_version": "run-policy"},
                    )
                    assert scope.model_usage().model_attempts == 4 and len(run_reports) == 1
                    assert run_summary.message_ids == ("u1", "a1")
                    assert (await repo.maintenance("m1"))["reserved_attempts"] == 2

                    second = PublicInteraction(
                        task_id="t2",
                        task_status="COMPLETED",
                        messages=(
                            PublicMessage(
                                message_id="u2", role="user", content="Another topic", task_id="t2"
                            ),
                            PublicMessage(
                                message_id="a2", role="assistant", content="Okay", task_id="t2"
                            ),
                        ),
                    )
                    archive2 = await manager.publish(
                        ident,
                        "cp2",
                        [second],
                        retain_recent=0,
                        max_messages=2,
                        session_status="COMPLETED",
                    )
                    incremental, _ = await manager.compact(
                        ident,
                        run_scope=scope,
                        run_context=ModelCallContext("run", "task", AgentType.SUPERVISOR),
                        execution_mode="normal",
                        **{
                            **kwargs,
                            "archive_refs": (archive.archive_ref, archive2.archive_ref),
                            "parent_summary_id": summary.summary_id,
                            "version": 2,
                            "source_checkpoint_id": "cp2",
                            "policy_version": "incremental",
                        },
                    )
                    assert incremental.message_ids == ("u1", "a1", "u2", "a2")
                    assert incremental.parent_summary_id == summary.summary_id

                    failing_kwargs = {**kwargs, "policy_version": "save-failure"}
                    original_save = repo.save_summary

                    async def fail_save(*args, **save_kwargs):
                        raise RuntimeError("injected summary commit failure")

                    repo.save_summary = fail_save
                    with pytest.raises(CompactionError) as failed:
                        await manager.compact(
                            ident, maintenance={**maint, "maintenance_id": "save"}, **failing_kwargs
                        )
                    assert failed.value.usage.total_tokens == 13
                    repo.save_summary = original_save
                    await manager.compact(
                        ident, maintenance={**maint, "maintenance_id": "save"}, **failing_kwargs
                    )
                    assert (await repo.maintenance("save"))["reserved_attempts"] == 2

                    original_finish = repo.finish_maintenance

                    async def fail_finish(*args, **finish_kwargs):
                        raise RuntimeError("injected completion failure")

                    repo.finish_maintenance = fail_finish
                    reuse_kwargs = {**kwargs, "policy_version": "reuse"}
                    with pytest.raises(RuntimeError, match="completion"):
                        await manager.compact(
                            ident, maintenance={**maint, "maintenance_id": "reuse"}, **reuse_kwargs
                        )
                    repo.finish_maintenance = original_finish
                    await repo.interrupt_maintenance("reuse")
                    calls = model.calls
                    await manager.compact(
                        ident, maintenance={**maint, "maintenance_id": "reuse"}, **reuse_kwargs
                    )
                    assert model.calls == calls

                    class SlowModel(ControlledModel):
                        def __init__(self):
                            super().__init__()
                            self.fail = False
                            self.entered = asyncio.Event()
                            self.release = asyncio.Event()

                        async def ainvoke(self, messages):
                            self.entered.set()
                            await self.release.wait()
                            return await super().ainvoke(messages)

                    slow = SlowModel()
                    slow_kwargs = {
                        **kwargs,
                        "policy_version": "same-work",
                        "gateway": ModelGateway(slow, ModelCallLimits(8, 5, 0)),
                    }
                    concurrent = {**maint, "maintenance_id": "owner"}
                    active = asyncio.create_task(
                        manager.compact(ident, maintenance=concurrent, **slow_kwargs)
                    )
                    await slow.entered.wait()
                    with pytest.raises(ValueError, match="in progress"):
                        await manager.compact(
                            ident,
                            maintenance={**concurrent, "maintenance_id": "other-owner"},
                            **slow_kwargs,
                        )
                    slow.release.set()
                    completed, _ = await active
                    assert slow.calls == 1
                    assert (await manager.compact(ident, maintenance=concurrent, **slow_kwargs))[
                        0
                    ] == completed
                    assert slow.calls == 1
                    recovered = await manager.recover(
                        ident,
                        summary_id=summary.summary_id,
                        candidate_limit=1,
                        max_bytes=10000,
                        max_tokens=1000,
                        token_counter=lambda msgs: len(msgs),
                    )
                    assert recovered == interaction.messages
                    other = SessionIdentity(user_id="other", conversation_id="c:221")
                    with pytest.raises(ValueError):
                        await manager.recover(
                            other,
                            summary_id=summary.summary_id,
                            candidate_limit=1,
                            max_bytes=10000,
                            max_tokens=1000,
                            token_counter=lambda msgs: len(msgs),
                        )

                    work = await repo.register_maintenance(
                        ident,
                        maintenance_id="parallel",
                        source_task_id="t",
                        source_run_id="r",
                        source_checkpoint_id="cp",
                        message_ids=("u1", "a1"),
                        content_hash="parallel-hash",
                        policy_version="p1",
                        budget_version="b1",
                        max_input_tokens=4096,
                        max_output_tokens=128,
                        archive_refs=(archive.archive_ref,),
                    )
                    assert work["reserved_attempts"] == 0
                    claim = await repo.claim_maintenance("parallel")
                    results = await asyncio.gather(
                        *(repo.reserve_attempt("parallel", claim) for _ in range(3)),
                        return_exceptions=True,
                    )
                    ids = [value for value in results if isinstance(value, str)]
                    assert len(ids) == 2 and len(set(ids)) == 2
                    assert sum(isinstance(value, ValueError) for value in results) == 1
                    known = UsageReport(1, 2, 3, "known")
                    await repo.record_attempt("parallel", claim, ids[1], known)
                    await repo.record_attempt("parallel", claim, ids[1], known)
                    with pytest.raises(ValueError, match="receipt conflict"):
                        await repo.record_attempt(
                            "parallel", claim, ids[1], UsageReport(1, 2, 4, "known")
                        )
                    await repo.interrupt_maintenance("parallel")
                    restarted = ContextRepository(pool)
                    assert (await restarted.maintenance("parallel"))["status"] == "EXHAUSTED"
                    actual, usage = await restarted.maintenance_usage("parallel")
                    assert actual == 1 and usage.status == "unknown" and usage.total_tokens is None
                    with pytest.raises(ValueError):
                        await restarted.reserve_attempt("parallel", claim)
                    attempts = await restarted.attempts("parallel")
                    assert {row["status"] for row in attempts} == {"RECORDED", "INTERRUPTED"}
                    await repo.register_maintenance(
                        ident,
                        maintenance_id="restart",
                        source_task_id="t",
                        source_run_id="r",
                        source_checkpoint_id="cp",
                        message_ids=("u1", "a1"),
                        content_hash="restart-hash",
                        policy_version="p1",
                        budget_version="b1",
                        max_input_tokens=4096,
                        max_output_tokens=128,
                        archive_refs=(archive.archive_ref,),
                    )
                    claim = await repo.claim_maintenance("restart")
                    await repo.reserve_attempt("restart", claim)
                    env = {
                        **os.environ,
                        "CTX221_TEST_SCHEMA": schema,
                        "PYTHONPATH": str(Path.cwd()),
                    }
                    child = subprocess.run(
                        [sys.executable, "tests/context_compaction_restart_probe.py"],
                        env=env,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    assert child.stdout.strip() == "interrupted_preserved"
                    assert (await repo.maintenance("restart"))["reserved_attempts"] == 1
                    claim = await repo.claim_maintenance("restart")
                    await repo.reserve_attempt("restart", claim)
                    with pytest.raises(ValueError):
                        await repo.reserve_attempt("restart", claim)
                    await repo.register_maintenance(
                        ident,
                        maintenance_id="killed",
                        source_task_id="t",
                        source_run_id="r",
                        source_checkpoint_id="cp",
                        message_ids=("u1", "a1"),
                        content_hash="kill-hash",
                        policy_version="p1",
                        budget_version="b1",
                        max_input_tokens=4096,
                        max_output_tokens=128,
                        archive_refs=(archive.archive_ref,),
                    )
                    process = subprocess.Popen(
                        [sys.executable, "tests/context_maintenance_kill_probe.py"],
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    try:
                        line = await asyncio.wait_for(
                            asyncio.to_thread(process.stdout.readline), timeout=15
                        )
                        assert line.strip() == b"controlled-call-started"
                        assert (await repo.maintenance("killed"))["reserved_attempts"] == 1
                    finally:
                        if process.poll() is None:
                            process.kill()
                        await asyncio.to_thread(process.communicate)
                    assert process.returncode != 0
                    restarted_child = subprocess.run(
                        [sys.executable, "tests/context_compaction_restart_probe.py"],
                        env={**env, "CTX221_TEST_WORK": "killed"},
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    assert restarted_child.stdout.strip() == "interrupted_preserved"
                    restarted = ContextRepository(pool)
                    assert (await restarted.maintenance("killed"))["reserved_attempts"] == 1
                    actual, usage = await restarted.maintenance_usage("killed")
                    assert actual == 0 and usage.status == "unknown" and usage.total_tokens is None
                    claim = await restarted.claim_maintenance("killed")
                    await restarted.reserve_attempt("killed", claim)
                    with pytest.raises(ValueError):
                        await restarted.reserve_attempt("killed", claim)
                    await repo.register_maintenance(
                        ident,
                        maintenance_id="expired",
                        source_task_id="t",
                        source_run_id="r",
                        source_checkpoint_id="cp",
                        message_ids=("u1", "a1"),
                        content_hash="expired-hash",
                        policy_version="p1",
                        budget_version="b1",
                        max_input_tokens=4096,
                        max_output_tokens=128,
                        archive_refs=(archive.archive_ref,),
                    )
                    async with pool.connection() as conn:
                        await conn.execute(
                            "UPDATE context_maintenance SET deadline_at=clock_timestamp() "
                            "- interval '1 second' WHERE maintenance_id='expired'"
                        )
                    claim = await repo.claim_maintenance("expired")
                    with pytest.raises(ValueError):
                        await repo.reserve_attempt("expired", claim)
                    assert await repo.finish_maintenance("expired", claim) == "EXHAUSTED"
                    original = await repo.register_maintenance(
                        ident,
                        maintenance_id="new-expired-id",
                        source_task_id="t",
                        source_run_id="r2",
                        source_checkpoint_id="cp",
                        message_ids=("u1", "a1"),
                        content_hash="expired-hash",
                        policy_version="p1",
                        budget_version="b1",
                        max_input_tokens=4096,
                        max_output_tokens=128,
                        archive_refs=(archive.archive_ref,),
                    )
                    assert (
                        original["maintenance_id"] == "expired"
                        and original["status"] == "EXHAUSTED"
                    )
            finally:
                await admin.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
                )
                assert (
                    await (
                        await admin.execute(
                            "SELECT count(*) FROM pg_namespace WHERE nspname=%s", (schema,)
                        )
                    ).fetchone()
                ) == (0,)

    run_async(probe())
