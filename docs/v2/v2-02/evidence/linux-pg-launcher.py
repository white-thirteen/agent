"""Run checks through the V2 02 SSH tunnel to the new labelled Linux container.

The historical test markers are retained to satisfy the existing isolation guards;
the container and volume themselves are new and dedicated to this stage.
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
    private = json.loads((ROOT / ".git/v202-linux-pg-private.json").read_text(encoding="utf-8"))
    assert private["local_port"] == private["remote_port"] == 56431
    assert private["container"] == "codex-v202-" + private["token"]
    assert private["image"] == (
        "sha256:748b51b8d45a51bc517424a9cd78aab4c8d268fe2155cca018b66f84c361ce85"
    )

    def dsn(database, user):
        return make_conninfo(
            host="127.0.0.1",
            port=56431,
            dbname=database,
            user=user,
            password=private["password"],
        )

    targets = (
        ("AGENT_DATABASE_URL", "agent_demo", "agent_app", "codex-task131-0e62"),
        ("AGENT_TEST_DATABASE_URL", "agent_demo_test", "agent_test", "codex-task131-0e62"),
        (
            "AGENT_SPARSE_TASK112_DATABASE_URL",
            "agent_sparse_task112_test",
            "agent_sparse_task112",
            "codex-task112-7c41",
        ),
        (
            "AGENT_HYBRID_TASK121_DATABASE_URL",
            "agent_hybrid_task121_test",
            "agent_hybrid_task121",
            "codex-task121-9db5",
        ),
    )
    for key, database, user, marker in targets:
        connection = dsn(database, user)
        with psycopg.connect(
            connection,
            autocommit=True,
            connect_timeout=5,
            options="-c default_transaction_read_only=on",
        ) as conn:
            row = conn.execute(
                "SELECT current_database(),current_user,current_setting('server_version_num'), "
                "shobj_description(oid,'pg_database') FROM pg_database "
                "WHERE datname=current_database()"
            ).fetchone()
            assert row == (database, user, "170012", marker), "Linux isolated database guard failed"
        os.environ[key] = connection
    # Archive component tests keep using their separately guarded local scratch DB.
    local = json.loads((ROOT / ".git/v202-local-pg-private.json").read_text(encoding="utf-8"))
    assert local["host"] == "127.0.0.1" and local["port"] == 56422
    os.environ.update(
        CONTEXT_ARCHIVE_TEST_DSN=make_conninfo(
            host=local["host"],
            port=local["port"],
            dbname=local["database"],
            user=local["user"],
            password=local["password"],
        ),
        AGENT_DATABASE_ADMIN_URL=dsn("postgres", "postgres"),
        AGENT_HYBRID_TASK131_DATABASE_URL=os.environ["AGENT_TEST_DATABASE_URL"],
        AGENT_APP_ENV="test",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )


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
                inserted = await seed_orders.seed_orders(url, target=target, settings=settings)
                print({"isolated_target": target, "migrations": applied, "fixture_rows": inserted})

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
