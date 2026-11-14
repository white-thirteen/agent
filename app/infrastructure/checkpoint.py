"""Dedicated PostgreSQL checkpoint resources; schema setup is always explicit."""

import asyncio

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from app.infrastructure.postgres import (
    DatabaseUnavailableError,
    connection_kwargs,
    install_safe_pool_log_filter,
)


def checkpoint_serializer():
    """Allow only the application types actually retained by graph checkpoints."""
    allowed = (
        [("app.agents.types", name) for name in ("AgentType", "TaskType")]
        + [
            ("app.graph.contracts", name)
            for name in (
                "ExecutionContext",
                "RouteDecision",
                "SupervisorOutput",
                "PendingTask",
                "PublicCitation",
                "FailureDetails",
                "ResultStatus",
                "SpecialistInput",
                "SpecialistResult",
            )
        ]
        + [("app.runtime.models", name) for name in ("TaskStatus", "RunStatus", "RunUsage")]
        + [
            ("app.runtime.model_gateway", "ModelCallUsage"),
            ("app.tools.models", "ParsedToolCall"),
            ("app.tools.models", "PreparedToolAttempt"),
            ("app.tools.models", "ToolExecutionResult"),
        ]
    )
    return JsonPlusSerializer(allowed_msgpack_modules=allowed)


async def open_checkpoint_pool(settings, *, verify_setup=True):
    """Open a separate autocommit pool, optionally requiring the installed Saver schema."""
    install_safe_pool_log_filter()
    if settings.database_url is None:
        raise DatabaseUnavailableError("Checkpoint database is not configured")
    pool = AsyncConnectionPool(
        open=False,
        kwargs={
            **connection_kwargs(settings.database_url, settings.database_connect_timeout_seconds),
            "autocommit": True,
            "row_factory": dict_row,
            "prepare_threshold": 0,
        },
        min_size=1,
        max_size=5,
        timeout=settings.database_connect_timeout_seconds,
        reconnect_timeout=settings.database_startup_timeout_seconds,
    )
    try:
        async with asyncio.timeout(settings.database_startup_timeout_seconds):
            await pool.open()
            await pool.wait(timeout=settings.database_startup_timeout_seconds)
            if verify_setup:
                async with pool.connection() as conn:
                    cursor = await conn.execute("SELECT v FROM checkpoint_migrations ORDER BY v")
                    versions = [row["v"] for row in await cursor.fetchall()]
                    if versions != list(range(len(AsyncPostgresSaver.MIGRATIONS))):
                        raise DatabaseUnavailableError("Checkpoint setup version mismatch")
    except (psycopg.Error, PoolTimeout, TimeoutError, DatabaseUnavailableError):
        await pool.close()
        raise DatabaseUnavailableError("Checkpoint resource unavailable") from None
    except BaseException:
        await pool.close()
        raise
    return pool
