"""Explicit setup for the framework-managed checkpoint schema."""

import argparse

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import conninfo_to_dict
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.checkpoint import open_checkpoint_pool
from app.infrastructure.postgres import DatabaseUnavailableError, validate_test_target
from scripts import run_async
from scripts.migrate import MIGRATIONS_DIR, migration_files


async def setup_checkpoint(*, target, settings):
    """Check the approved database identity and existing numbered schema before setup."""
    url = settings.test_database_url if target == "test" else settings.database_url
    if url is None or target not in ("test", "development"):
        raise DatabaseUnavailableError("Explicit checkpoint target required")
    info = conninfo_to_dict(url.get_secret_value())
    if info.get("host") not in ("localhost", "127.0.0.1", "::1", "192.168.150.101"):
        raise DatabaseUnavailableError("Checkpoint target is not the approved host")
    expected = (
        ("agent_demo_test", "agent_test") if target == "test" else ("agent_demo", "agent_app")
    )
    if target == "test":
        validate_test_target(url, settings.database_url)
    elif settings.app_env == "production":
        raise DatabaseUnavailableError("Production setup is not allowed")
    configured = settings.model_copy(update={"database_url": url})
    pool = await open_checkpoint_pool(configured, verify_setup=False)
    try:
        async with pool.connection() as conn:
            row = await (
                await conn.execute("SELECT current_database() AS db, current_user AS owner")
            ).fetchone()
            if (row["db"], row["owner"]) != expected:
                raise DatabaseUnavailableError("Checkpoint target identity mismatch")
            rows = await (
                await conn.execute(
                    "SELECT version, checksum FROM schema_migrations ORDER BY version"
                )
            ).fetchall()
            files = migration_files(MIGRATIONS_DIR)
            if [row["version"] for row in rows] != list(range(1, max(files) + 1)) or any(
                files[row["version"]][0] != row["checksum"] for row in rows
            ):
                raise DatabaseUnavailableError("Numbered migration version or checksum mismatch")
        await AsyncPostgresSaver(pool).setup()
    finally:
        await pool.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("development", "test"), required=True)
    args = parser.parse_args()
    try:
        await setup_checkpoint(target=args.target, settings=Settings())
    except (psycopg.Error, DatabaseUnavailableError, ValidationError):
        print("Checkpoint setup failed; check target and schema.")
        return 1
    print("Checkpoint setup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_async(main()))
