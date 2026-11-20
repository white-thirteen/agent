"""Run explicit V2 02 checks against the newly created local PostgreSQL only.

Private credentials stay under .git; this file contains no connection secrets.
No command falls back to the project's formal database configuration.
"""

import asyncio
import json
import os
import runpy
import sys
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def configure():
    private = json.loads((ROOT / ".git/v202-local-pg-private.json").read_text(encoding="utf-8"))
    assert private["host"] == "127.0.0.1" and private["port"] == 56422
    marker = "codex-v202-local-20261119"
    assert private["marker"] == marker

    def dsn(database, user):
        return make_conninfo(
            host=private["host"],
            port=private["port"],
            dbname=database,
            user=user,
            password=private["password"],
        )

    targets = {
        "AGENT_DATABASE_URL": dsn("agent_demo", "agent_app"),
        "AGENT_TEST_DATABASE_URL": dsn("agent_demo_test", "agent_test"),
        "CONTEXT_ARCHIVE_TEST_DSN": dsn("agent_context_test", "agent_test"),
    }
    for connection in targets.values():
        with psycopg.connect(
            connection,
            autocommit=True,
            connect_timeout=5,
            options="-c default_transaction_read_only=on",
        ) as conn:
            row = conn.execute(
                "SELECT current_setting('server_version_num'), "
                "shobj_description(oid,'pg_database') FROM pg_database "
                "WHERE datname=current_database()"
            ).fetchone()
            assert row == ("170012", marker), "Local database guard failed"
    os.environ.update(targets)
    os.environ.update(
        AGENT_DATABASE_ADMIN_URL=dsn("postgres", "postgres"),
        AGENT_APP_ENV="test",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    return private


def main():
    configure()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    mode = sys.argv[1]
    if mode == "init":
        from app.core.config import Settings
        from scripts import migrate, run_async, seed_orders, setup_checkpoint, setup_store

        async def initialize():
            settings = Settings()
            for target, url in (
                ("development", settings.database_url),
                ("test", settings.test_database_url),
            ):
                applied = await migrate.apply_migrations(url, target=target)
                await setup_checkpoint.setup_checkpoint(target=target, settings=settings)
                await setup_store.setup_store(target=target, settings=settings)
                # These are brand-new local databases, never the existing five orders.
                inserted = await seed_orders.seed_orders(url, target=target, settings=settings)
                print({"local_target": target, "migrations": applied, "new_fixture_rows": inserted})

        run_async(initialize())
    elif mode == "pytest":
        import pytest

        raise SystemExit(pytest.main(sys.argv[2:]))
    elif mode == "module":
        module = sys.argv[2]
        sys.argv = [module, *sys.argv[3:]]
        runpy.run_module(module, run_name="__main__")
    else:
        raise ValueError("Use init, pytest or module")


if __name__ == "__main__":
    main()
