"""Bounded PostgreSQL pool initialization and read-only schema checks."""

import asyncio
import logging

from psycopg import OperationalError
from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import UndefinedTable
from psycopg_pool import AsyncConnectionPool, PoolTimeout
from pydantic import SecretStr

from app.core.config import Settings

EXPECTED_SCHEMA_VERSION = 2
MIGRATION_LOCK_ID = 1701001


class DatabaseUnavailableError(RuntimeError):
    """Safe resource failure without connection details."""


def connection_kwargs(url: SecretStr, timeout: float = 5) -> dict:
    return {
        **conninfo_to_dict(url.get_secret_value()),
        "connect_timeout": max(1, int(timeout)),
    }


def validate_test_target(url: SecretStr, development_url: SecretStr | None = None) -> None:
    info = conninfo_to_dict(url.get_secret_value())
    if info.get("dbname") != "agent_demo_test":
        raise DatabaseUnavailableError("Explicit agent_demo_test database is required")
    if development_url:
        development = conninfo_to_dict(development_url.get_secret_value())
        # Fixed dual-database layout also rejects host aliases pointing at the test database.
        if development.get("dbname") == info["dbname"]:
            raise DatabaseUnavailableError("Test and development databases must differ")


async def check_schema_version(pool: AsyncConnectionPool) -> None:
    try:
        async with pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
            versions = [row[0] for row in await cursor.fetchall()]
            if versions != list(range(1, EXPECTED_SCHEMA_VERSION + 1)):
                raise DatabaseUnavailableError("Application schema version mismatch")
    except (OperationalError, PoolTimeout, UndefinedTable):
        raise DatabaseUnavailableError("Database schema is unavailable") from None


async def open_pool(settings: Settings) -> AsyncConnectionPool:
    """Return a connected, schema-checked pool. Close every failed initialization."""
    if settings.database_url is None:
        raise DatabaseUnavailableError("Database is not configured")
    pool = AsyncConnectionPool(
        open=False,
        kwargs=connection_kwargs(settings.database_url, settings.database_connect_timeout_seconds),
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        timeout=settings.database_connect_timeout_seconds,
        reconnect_timeout=settings.database_startup_timeout_seconds,
    )
    try:
        async with asyncio.timeout(settings.database_startup_timeout_seconds):
            await pool.open()
            await pool.wait(timeout=settings.database_startup_timeout_seconds)
            await check_schema_version(pool)
    except (OperationalError, PoolTimeout, TimeoutError, DatabaseUnavailableError):
        await pool.close()
        raise DatabaseUnavailableError("Database initialization failed") from None
    except BaseException:
        # Cleanup also runs on cancellation and programming errors, which propagate unchanged.
        await pool.close()
        raise
    return pool


def selector_event_loop() -> asyncio.AbstractEventLoop:
    """Uvicorn custom loop entry point, compatible with psycopg on Windows."""
    return asyncio.SelectorEventLoop()


class SafePoolLogFilter(logging.Filter):
    """Pool workers emit driver errors outside the caller's safe boundary."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = "PostgreSQL pool resource event"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True
