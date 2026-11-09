"""Apply numbered transaction-only SQL with checksum and advisory locking."""

import argparse
import hashlib
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import SecretStr, ValidationError

from app.core.config import PROJECT_ROOT, Settings
from app.infrastructure.postgres import (
    MIGRATION_LOCK_ID,
    DatabaseUnavailableError,
    connection_kwargs,
    validate_test_target,
)

MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def migration_files(directory: Path) -> dict[int, tuple[str, str]]:
    files = {}
    for path in sorted(directory.glob("[0-9]*_*.sql")):
        version = int(path.name.split("_", 1)[0])
        if version <= 0 or version in files:
            raise DatabaseUnavailableError("Invalid or duplicate migration version")
        content = path.read_bytes()
        files[version] = (hashlib.sha256(content).hexdigest(), content.decode("utf-8"))
    if not files:
        raise DatabaseUnavailableError("No migration files found")
    return files


async def _lock_and_validate(connection, files) -> set[int]:
    await connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,))
    await connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version integer PRIMARY KEY, checksum text NOT NULL, "
        "applied_at timestamptz NOT NULL DEFAULT now())"
    )
    cursor = await connection.execute("SELECT version, checksum FROM schema_migrations")
    applied = dict(await cursor.fetchall())
    for version, checksum in applied.items():
        if version not in files or files[version][0] != checksum:
            raise DatabaseUnavailableError("Unknown or changed applied migration")
    if applied and set(applied) != {version for version in files if version <= max(applied)}:
        raise DatabaseUnavailableError("Applied migration sequence is inconsistent")
    return set(applied)


async def apply_migrations(
    database_url: SecretStr,
    *,
    target: Literal["development", "test"],
) -> list[int]:
    if target == "test":
        validate_test_target(database_url)
    files = migration_files(MIGRATIONS_DIR)
    applied_now = []
    async with await psycopg.AsyncConnection.connect(
        **connection_kwargs(database_url),
        autocommit=True,
    ) as connection:
        if target == "test":
            cursor = await connection.execute("SELECT current_database()")
            if (await cursor.fetchone())[0] != "agent_demo_test":
                raise DatabaseUnavailableError("Unexpected test database")
        async with connection.transaction():
            await _lock_and_validate(connection, files)
        for version, (checksum, sql) in sorted(files.items()):
            async with connection.transaction():
                applied = await _lock_and_validate(connection, files)
                if version in applied:
                    continue
                await connection.execute(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations(version, checksum) VALUES (%s, %s)",
                    (version, checksum),
                )
            applied_now.append(version)
    return applied_now


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("development", "test"), required=True)
    args = parser.parse_args()
    try:
        settings = Settings()
        url = settings.test_database_url if args.target == "test" else settings.database_url
        if url is None:
            raise DatabaseUnavailableError("Explicit target database URL required")
        if args.target == "test":
            validate_test_target(url, settings.database_url)
        versions = await apply_migrations(url, target=args.target)
        print(f"Migration succeeded. Applied versions {versions}")
        return 0
    except (psycopg.Error, DatabaseUnavailableError, ValidationError) as error:
        print(f"Migration failed ({type(error).__name__}). Check local configuration/schema.")
        return 1


if __name__ == "__main__":
    from scripts import run_async

    raise SystemExit(run_async(main()))
