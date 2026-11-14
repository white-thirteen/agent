"""Owned PostgreSQL Store; sole adapter for the pinned 3.2.0 task lifecycle."""

import asyncio
from contextlib import asynccontextmanager, suppress

import psycopg
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from app.infrastructure.postgres import (
    DatabaseUnavailableError,
    connection_kwargs,
    install_safe_pool_log_filter,
)


class StoreResource:
    """Borrowed operations; only the owning context closes Store and pool."""

    def __init__(self, store):
        self._store = store

    async def aget(self, namespace, key):
        return await self._store.aget(namespace, key)

    async def abatch(self, operations):
        return await self._store.abatch(operations)

    async def setup(self):
        """Explicit command only; application startup never calls setup."""
        await self._store.setup()


@asynccontextmanager
async def store_resources(settings, *, verify_setup=True):
    """Verify without DDL; close batching, Store context and owned pool in order."""
    install_safe_pool_log_filter()
    if settings.database_url is None:
        raise DatabaseUnavailableError("Store database is not configured")
    pool = AsyncConnectionPool(
        open=False,
        kwargs={
            **connection_kwargs(settings.database_url, settings.database_connect_timeout_seconds),
            "autocommit": True,
            "row_factory": dict_row,
            "prepare_threshold": 0,
        },
        min_size=1,
        max_size=3,
        timeout=settings.database_connect_timeout_seconds,
        reconnect_timeout=settings.database_startup_timeout_seconds,
    )
    try:
        try:
            async with asyncio.timeout(settings.database_startup_timeout_seconds):
                await pool.open()
                await pool.wait(timeout=settings.database_startup_timeout_seconds)
                if verify_setup:
                    async with pool.connection() as conn:
                        rows = await (
                            await conn.execute("SELECT v FROM store_migrations ORDER BY v")
                        ).fetchall()
                        if [row["v"] for row in rows] != list(
                            range(len(AsyncPostgresStore.MIGRATIONS))
                        ):
                            raise DatabaseUnavailableError("Store setup version mismatch")
                        await conn.execute(
                            "SELECT prefix,key,value,created_at,updated_at,expires_at,ttl_minutes "
                            "FROM store LIMIT 0"
                        )
        except (psycopg.Error, PoolTimeout, TimeoutError):
            raise DatabaseUnavailableError("Store resource unavailable") from None
        async with AsyncPostgresStore(conn=pool, index=None, ttl=None) as store:
            try:
                yield StoreResource(store)
            finally:
                # 3.2.0 has no public close for the base batching task. Runtime must
                # already have settled callers before this local version adaptation.
                task = store._task
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
    finally:
        await pool.close()
