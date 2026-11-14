"""Explicit setup for the framework-managed store schema."""

import argparse

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.postgres import (
    DatabaseUnavailableError,
    connection_kwargs,
    validate_test_target,
)
from app.infrastructure.store import store_resources
from scripts import run_async
from scripts.migrate import MIGRATIONS_DIR, migration_files


async def setup_store(*, target, settings):
    """Check the approved database identity and existing numbered schema before setup."""
    url = settings.test_database_url if target == "test" else settings.database_url
    if url is None or target not in ("test", "development"):
        raise DatabaseUnavailableError("Explicit store target required")
    info = conninfo_to_dict(url.get_secret_value())
    if info.get("host") not in ("localhost", "127.0.0.1", "::1", "192.168.150.101"):
        raise DatabaseUnavailableError("Store target is not the approved host")
    expected = (
        ("agent_demo_test", "agent_test") if target == "test" else ("agent_demo", "agent_app")
    )
    if target == "test":
        validate_test_target(url, settings.database_url)
    elif settings.app_env == "production":
        raise DatabaseUnavailableError("Production setup is not allowed")
    configured = settings.model_copy(update={"database_url": url})
    async with await psycopg.AsyncConnection.connect(
        **connection_kwargs(url, settings.database_connect_timeout_seconds),
        autocommit=True,
        row_factory=dict_row,
    ) as conn:
        row = await (
            await conn.execute("SELECT current_database() AS db, current_user AS owner")
        ).fetchone()
        if (row["db"], row["owner"]) != expected:
            raise DatabaseUnavailableError("Store target identity mismatch")
        rows = await (
            await conn.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
        ).fetchall()
        files = migration_files(MIGRATIONS_DIR)
        if [row["version"] for row in rows] != list(range(1, max(files) + 1)) or any(
            files[row["version"]][0] != row["checksum"] for row in rows
        ):
            raise DatabaseUnavailableError("Numbered migration version or checksum mismatch")
    async with store_resources(configured, verify_setup=False) as resource:
        await resource.setup()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("development", "test"), required=True)
    args = parser.parse_args()
    try:
        await setup_store(target=args.target, settings=Settings())
    except (psycopg.Error, DatabaseUnavailableError, ValidationError):
        print("Store setup failed; check target and schema.")
        return 1
    print("Store setup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_async(main()))
