import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg_pool import AsyncConnectionPool

from app.context.models import SessionIdentity
from app.context.repository import ContextRepository
from app.runtime.model_gateway import UsageReport
from scripts import run_async


async def main():
    dsn = os.environ["CONTEXT_ARCHIVE_TEST_DSN"]
    schema = "ctx221qa_" + uuid4().hex
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as admin:
        row = await (
            await admin.execute(
                "SELECT current_database(), current_user, current_setting('server_version_num'), "
                "shobj_description(oid,'pg_database') FROM pg_database "
                "WHERE datname=current_database()"
            )
        ).fetchone()
        assert row == ("agent_context_test", "agent_test", "170012", "codex-v202-local-20261119")
        await admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            await admin.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            for name in ("008_context_archive.sql", "009_context_compaction.sql"):
                await admin.execute(Path("migrations", name).read_text(encoding="utf-8"))
            pool = AsyncConnectionPool(
                dsn, kwargs={"options": f"-csearch_path={schema}"}, open=False
            )
            async with pool:
                repo = ContextRepository(pool)
                identity = SessionIdentity(user_id="qa", conversation_id="qa")
                await repo.register_maintenance(
                    identity,
                    maintenance_id="m",
                    source_task_id="t",
                    source_run_id="r",
                    source_checkpoint_id="cp",
                    message_ids=("1", "2"),
                    content_hash="hash",
                    policy_version="p",
                    budget_version="b",
                    max_input_tokens=100,
                    max_output_tokens=10,
                    archive_refs=("ref",),
                )
                old = await repo.claim_maintenance("m")
                attempt = await repo.reserve_attempt("m", old)
                try:
                    await repo.claim_maintenance("m")
                    raise AssertionError("active claim displaced")
                except ValueError:
                    pass
                await repo.interrupt_maintenance("m")
                new = await repo.claim_maintenance("m")
                second = await repo.reserve_attempt("m", new)
                try:
                    await repo.record_attempt("m", old, attempt, UsageReport(1, 1, 2, "known"))
                    raise AssertionError("old receipt accepted")
                except ValueError:
                    pass
                await repo.record_attempt("m", new, second, UsageReport(2, 1, 3, "known"))
                rows = await repo.attempts("m")
                assert {x["status"] for x in rows} == {"INTERRUPTED", "RECORDED"}
                assert (await repo.maintenance("m"))["reserved_attempts"] == 2
                print(
                    "PASS active claim guarded; interrupted old receipt rejected; "
                    "new receipt retained; attempts=2"
                )
        finally:
            await admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            assert (
                await (
                    await admin.execute(
                        "SELECT count(*) FROM pg_namespace WHERE nspname=%s", (schema,)
                    )
                ).fetchone()
            ) == (0,)
            print("PASS isolated schema cleanup")


run_async(main())
