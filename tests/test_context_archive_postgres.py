"""Opt-in real PostgreSQL probe: a dedicated DB and a uniquely owned schema only."""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import AsyncConnectionPool

from app.context.archive_store import ArchiveStore
from app.context.manager import ContextManager
from app.context.models import PublicInteraction, PublicMessage, SessionIdentity
from app.context.repository import ArchiveRepository


@pytest.mark.asyncio
async def test_real_postgres_archive_publication(tmp_path):
    dsn = os.environ.get("CONTEXT_ARCHIVE_TEST_DSN")
    if not dsn:
        pytest.skip("dedicated PostgreSQL probe not configured")
    if conninfo_to_dict(dsn).get("host") != "127.0.0.1":
        raise RuntimeError("Dedicated database host guard failed")
    schema = "ctx212_" + uuid4().hex
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as admin:
        row = await (
            await admin.execute(
                "SELECT current_database(),current_user,current_setting('server_version_num'),"
                "shobj_description(oid,'pg_database') FROM pg_database "
                "WHERE datname=current_database()"
            )
        ).fetchone()
        if row != ("agent_context_test", "agent_test", "170012", "codex-v202-local-20261119"):
            raise RuntimeError("Dedicated database guard failed")
        await admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            await admin.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            migration = Path("migrations/008_context_archive.sql").read_text(encoding="utf-8")
            await admin.execute(migration)
            pool = AsyncConnectionPool(
                dsn,
                kwargs={"options": f"-csearch_path={schema}"},
                open=False,
                min_size=1,
                max_size=2,
            )
            async with pool:
                repository = ArchiveRepository(pool)
                manager = ContextManager(repository, ArchiveStore(tmp_path))
                identity = SessionIdentity(user_id="用户:a", conversation_id="c:../b")
                messages = (
                    PublicMessage(
                        message_id="u1", role="user", content="原文\n# 伪造", task_id="t"
                    ),
                    PublicMessage(message_id="a1", role="assistant", content="完整", task_id="t"),
                )
                interaction = PublicInteraction(
                    task_id="t", task_status="COMPLETED", messages=messages
                )

                async def publish():
                    return await manager.publish(
                        identity,
                        "cp",
                        [interaction],
                        retain_recent=0,
                        max_messages=2,
                        session_status="COMPLETED",
                    )

                original_ready = repository.ready

                async def fail_ready(*args):
                    raise RuntimeError("simulated ready commit failure")

                repository.ready = fail_ready
                with pytest.raises(RuntimeError):
                    await publish()
                repository.ready = original_ready
                archive = await publish()
                assert await publish() == archive
                assert await asyncio.gather(publish(), publish()) == [archive, archive]
                assert (
                    await repository.get(
                        SessionIdentity(user_id="other", conversation_id="c:../b"),
                        archive.archive_ref,
                    )
                    is None
                )
                candidates = await repository.candidates(
                    identity, limit=2, task_id="t", message_id="u1"
                )
                assert candidates == [archive]
                assert (
                    await manager.recover(
                        identity,
                        refs=[archive.archive_ref],
                        candidate_limit=1,
                        max_bytes=10000,
                        max_tokens=100,
                        token_counter=lambda _: 1,
                    )
                    == messages
                )
        finally:
            await admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            row = await (
                await admin.execute("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (schema,))
            ).fetchone()
            assert row == (0,)
