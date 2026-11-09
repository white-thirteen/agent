"""User-scoped session bindings. The stored thread is authoritative after creation."""

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg import OperationalError
from psycopg_pool import AsyncConnectionPool, PoolClosed, PoolTimeout

from app.core.errors import SessionUnavailableError


@dataclass(frozen=True, slots=True)
class SessionBinding:
    user_id: str
    conversation_id: str
    thread_id: UUID
    created_at: datetime


class SessionRepository:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def get(self, *, user_id: str, conversation_id: str) -> SessionBinding | None:
        try:
            async with self._pool.connection() as connection:
                cursor = await connection.execute(
                    "SELECT user_id, conversation_id, thread_id, created_at FROM sessions "
                    "WHERE user_id = %s AND conversation_id = %s",
                    (user_id, conversation_id),
                )
                row = await cursor.fetchone()
                return SessionBinding(*row) if row else None
        except (OperationalError, PoolTimeout, PoolClosed):
            raise SessionUnavailableError() from None

    async def get_or_create(self, *, user_id: str, conversation_id: str) -> SessionBinding:
        candidate = uuid5(NAMESPACE_URL, json.dumps([user_id, conversation_id], ensure_ascii=False))
        try:
            async with self._pool.connection() as connection:
                async with connection.transaction():
                    # Migration 002 defers thread uniqueness to commit so the primary
                    # key alone arbitrates concurrent inserts of this same candidate.
                    await connection.execute(
                        "INSERT INTO sessions (user_id, conversation_id, thread_id) "
                        "VALUES (%s, %s, %s) ON CONFLICT (user_id, conversation_id) DO NOTHING",
                        (user_id, conversation_id, candidate),
                    )
                    # A separate statement sees inserts committed after the first snapshot.
                    cursor = await connection.execute(
                        "SELECT user_id, conversation_id, thread_id, created_at FROM sessions "
                        "WHERE user_id = %s AND conversation_id = %s",
                        (user_id, conversation_id),
                    )
                    return SessionBinding(*await cursor.fetchone())
        except (OperationalError, PoolTimeout, PoolClosed):
            raise SessionUnavailableError() from None
