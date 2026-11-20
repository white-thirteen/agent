"""Durable preference commands with conservative recovery across Store/PG."""

import asyncio
from uuid import uuid4

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from app.core.errors import RuntimeRequestError
from app.domain.refunds import canonical_digest
from app.tools.models import ParsedToolCall, PreferenceControlContext, ToolNotStartedError


class PreferenceService:
    def __init__(self, pool, executor, *, user_ids):
        self.pool = pool
        self.executor = executor
        self.locks = {user_id: asyncio.Lock() for user_id in user_ids}

    @staticmethod
    def _scope(identity, scope):
        if scope not in identity.permission_scopes:
            raise RuntimeRequestError("preference_scope_denied")

    async def read(self, identity):
        self._scope(identity, "memory:read")
        context = PreferenceControlContext(
            identity.user_id, str(uuid4()), "", "", 0, identity.permission_scopes
        )
        return await self.executor.execute_preference_control(
            ParsedToolCall(context.command_id, "read_preferences", {}), context=context
        )

    async def mutate(self, identity, operation_id, expected_revision, command):
        self._scope(identity, "memory:write")
        if command.operation == "read":
            raise RuntimeRequestError("preference_conflict")
        values = command.model_dump(mode="json")
        digest = canonical_digest(values)
        async with self.locks[identity.user_id]:
            row = await self._get(identity.user_id, operation_id)
            if row is None:
                command_id = str(uuid4())
                try:
                    async with self.pool.connection() as conn:
                        await conn.execute(
                            "INSERT INTO preference_command_receipt "
                            "(user_id,operation_id,command_id,command_digest,command,"
                            "expected_revision,status) VALUES (%s,%s,%s,%s,%s,%s,'PREPARED')",
                            (
                                identity.user_id,
                                operation_id,
                                command_id,
                                digest,
                                Jsonb(values),
                                expected_revision,
                            ),
                        )
                except UniqueViolation:
                    raise RuntimeRequestError("preference_unresolved") from None
                row = (command_id, digest, values, expected_revision, "PREPARED", None)
            if row[1] != digest or row[2] != values or row[3] != expected_revision:
                raise RuntimeRequestError("preference_conflict")
            if row[4] in ("APPLIED", "CONFLICT"):
                return row[5]
            return await self._execute(identity, operation_id, row)

    async def status(self, identity, operation_id):
        self._scope(identity, "memory:write")
        async with self.locks[identity.user_id]:
            row = await self._get(identity.user_id, operation_id)
            if row is None:
                raise RuntimeRequestError("preference_not_found")
            if row[4] in ("EXECUTING", "UNKNOWN"):
                return await self._execute(identity, operation_id, row)
            return {"status": row[4].lower(), "operation_id": operation_id, "result": row[5]}

    async def _get(self, user_id, operation_id):
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT command_id,command_digest,command,expected_revision,status,result "
                "FROM preference_command_receipt WHERE user_id=%s AND operation_id=%s",
                (user_id, operation_id),
            )
            return await cur.fetchone()

    async def _execute(self, identity, operation_id, row):
        command_id, digest, values, revision, status, _ = row
        replay = status != "PREPARED"
        if not replay:
            await self._save(identity.user_id, operation_id, "EXECUTING", None)
        context = PreferenceControlContext(
            identity.user_id,
            command_id,
            operation_id,
            digest,
            revision,
            identity.permission_scopes,
            replay,
        )
        try:
            result = await self.executor.execute_preference_control(
                ParsedToolCall(command_id, "write_preferences", values), context=context
            )
        except ToolNotStartedError:
            # Only a freshly started command can return to PREPARED. A replay
            # must retain the old uncertainty, even when this check did not run.
            if not replay:
                await self._save(identity.user_id, operation_id, "PREPARED", None)
            raise
        state = {
            "applied": "APPLIED",
            "reused": "APPLIED",
            "conflict": "CONFLICT",
            "unknown": "UNKNOWN",
        }[result["status"]]
        await self._save(identity.user_id, operation_id, state, result)
        return result

    async def _save(self, user_id, operation_id, status, result):
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE preference_command_receipt SET status=%s,result=%s "
                "WHERE user_id=%s AND operation_id=%s",
                (status, Jsonb(result) if result is not None else None, user_id, operation_id),
            )
