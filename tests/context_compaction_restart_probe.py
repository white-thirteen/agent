"""Resume an interrupted synthetic work item in a fresh process, using guarded local PG."""

import os
import re

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import AsyncConnectionPool

from app.context.repository import ContextRepository
from scripts import run_async


async def main():
    dsn = os.environ["CONTEXT_ARCHIVE_TEST_DSN"]
    parts = conninfo_to_dict(dsn)
    assert parts.get("host") == "127.0.0.1" and parts.get("port") == "56422"
    schema = os.environ["CTX221_TEST_SCHEMA"]
    assert re.fullmatch(r"ctx221_[0-9a-f]{32}", schema)
    work_id = os.environ.get("CTX221_TEST_WORK", "restart")
    assert work_id in {"restart", "killed"}
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        row = await (
            await conn.execute(
                "SELECT current_database(),current_user,current_setting('server_version_num'),"
                "shobj_description(oid,'pg_database') FROM pg_database "
                "WHERE datname=current_database()"
            )
        ).fetchone()
        assert row == ("agent_context_test", "agent_test", "170012", "codex-v202-local-20261119")
    pool = AsyncConnectionPool(dsn, kwargs={"options": f"-csearch_path={schema}"}, open=False)
    async with pool:
        repo = ContextRepository(pool)
        assert (await repo.maintenance(work_id))["reserved_attempts"] == 1
        await repo.interrupt_maintenance(work_id)
        work = await repo.maintenance(work_id)
        actual, usage = await repo.maintenance_usage(work_id)
        assert work["status"] == "INTERRUPTED" and actual == 0 and usage.status == "unknown"
        print("interrupted_preserved")


if __name__ == "__main__":
    run_async(main())
