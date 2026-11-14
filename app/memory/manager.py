"""User-scoped snapshots and single-worker, versioned preference mutations."""

import asyncio
import json
from typing import Literal

import psycopg
from langgraph.store.base import GetOp, PutOp
from psycopg_pool import PoolClosed, PoolTimeout
from pydantic import BaseModel, ConfigDict

from app.tools.models import ToolNotStartedError, ToolUnavailableError

PREFERENCE_VALUES = {
    "answer_language": frozenset({"zh-CN", "en"}),
    "answer_style": frozenset({"concise", "detailed"}),
}


def preference_namespace(user_id: str) -> tuple[str, str, str]:
    """Only a trusted, allowlisted identity may supply this namespace label."""
    if not user_id or "." in user_id or "\x00" in user_id:
        raise ValueError("Invalid preference user identifier")
    return ("users", user_id, "preferences")


class PreferenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["available", "empty", "partial"]
    preferences: dict[str, str]
    revision: int | None
    invalid_fields: list[str]


class MemoryManager:
    def __init__(self, resource, *, user_ids):
        self.resource = resource
        self.user_ids = frozenset(user_ids)
        self._locks = {user: asyncio.Lock() for user in self.user_ids}
        for user in self.user_ids:
            preference_namespace(user)

    async def snapshot(self, *, user_id: str) -> PreferenceSnapshot:
        if user_id not in self.user_ids:
            raise ValueError("Preference identity is not allowlisted")
        if self.resource is None:
            raise ToolUnavailableError("Memory resource unavailable", code="memory_unavailable")
        try:
            item = await self.resource.aget(preference_namespace(user_id), "profile")
        except json.JSONDecodeError:
            # Store 3.2.0 decodes non-object JSONB before returning an Item; its
            # orjson decode error is a stdlib JSONDecodeError subclass.
            raise ToolUnavailableError(
                "Memory profile invalid", code="memory_profile_invalid"
            ) from None
        except (psycopg.Error, PoolClosed, PoolTimeout):
            raise ToolUnavailableError(
                "Memory read unavailable", code="memory_unavailable"
            ) from None
        return self._project(item)

    @staticmethod
    def _project(item):
        if item is None:
            return PreferenceSnapshot(
                status="empty", preferences={}, revision=None, invalid_fields=[]
            )
        value = item.value
        if (
            not isinstance(value, dict)
            or len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 2048
            or type(value.get("schema_version")) is not int
            or value["schema_version"] != 1
            or type(value.get("revision")) is not int
            or value["revision"] < 0
            or not isinstance(value.get("preferences"), dict)
            or set(value) - {"schema_version", "revision", "preferences", "last_mutation"}
        ):
            raise ToolUnavailableError("Memory profile invalid", code="memory_profile_invalid")
        preferences = {}
        invalid = []
        for field, raw in value["preferences"].items():
            if field not in PREFERENCE_VALUES:
                # Unknown names and values are private data, never diagnostic text.
                invalid.append("unknown_field")
            elif isinstance(raw, str) and raw in PREFERENCE_VALUES[field]:
                preferences[field] = raw
            else:
                invalid.append(field)
        return PreferenceSnapshot(
            status="partial" if invalid else "available" if preferences else "empty",
            preferences=preferences,
            revision=value["revision"],
            invalid_fields=sorted(set(invalid)),
        )

    async def apply(self, command, *, context):
        """Lock only actual Store work; abatch is sequential, never a Store CAS.

        Once Put has started its failure cannot establish non-commit. A replay
        only checks the original operation, even if the old revision still exists.
        """
        from app.domain.refunds import canonical_digest
        from app.memory.models import MemoryCommand, MemoryMutationResult
        from app.tools.models import MemoryBusinessContext

        command = MemoryCommand.model_validate(command)
        if (
            not isinstance(context, MemoryBusinessContext)
            or context.user_id not in self.user_ids
            or not context.task_id
            or not context.run_id
            or not context.operation_id
            or context.command_digest != canonical_digest(command.model_dump(mode="json"))
            or type(context.expected_revision) is not int
            or context.expected_revision < 0
            or type(context.replay_check_only) is not bool
            or command.operation == "read"
        ):
            raise ValueError("Invalid trusted memory mutation association")

        def result(status, snapshot=None, fields=()):
            return MemoryMutationResult(
                status=status,
                operation_id=context.operation_id,
                revision=snapshot.revision if snapshot else None,
                changed_fields=list(fields),
                preferences=snapshot.preferences if snapshot else None,
            )

        async with self._locks[context.user_id]:
            namespace = preference_namespace(context.user_id)
            try:
                if self.resource is None:
                    raise ToolUnavailableError("Memory unavailable", code="memory_unavailable")
                item = (await self.resource.abatch([GetOp(namespace, "profile")]))[0]
                snapshot = self._project(item)
                if snapshot.invalid_fields:
                    raise ToolUnavailableError("Memory invalid", code="memory_profile_invalid")
            except (
                psycopg.Error,
                PoolClosed,
                PoolTimeout,
                TimeoutError,
                json.JSONDecodeError,
                ToolUnavailableError,
            ):
                if context.replay_check_only:
                    return result("unknown")
                raise ToolNotStartedError(
                    "Memory read unavailable", code="memory_unavailable"
                ) from None
            revision = snapshot.revision or 0
            last = item.value.get("last_mutation") if item else None
            if isinstance(last, dict) and last.get("operation_id") == context.operation_id:
                if last.get("command_digest") != context.command_digest:
                    return result("conflict", snapshot)
                if (
                    last.get("task_id") == context.task_id
                    and last.get("result_revision") == revision == context.expected_revision + 1
                    and isinstance(last.get("changed_fields"), list)
                    and set(last["changed_fields"]) <= PREFERENCE_VALUES.keys()
                ):
                    return result("reused", snapshot, last["changed_fields"])
                return result("unknown")
            if context.replay_check_only:
                return result("unknown")
            if revision != context.expected_revision:
                return result("conflict", snapshot)
            preferences = dict(snapshot.preferences)
            if command.operation == "upsert":
                preferences[command.field] = command.value
            elif command.operation == "delete":
                preferences.pop(command.field, None)
            else:
                preferences.clear()
            changed = sorted(
                field
                for field in PREFERENCE_VALUES
                if snapshot.preferences.get(field) != preferences.get(field)
            )
            value = {
                "schema_version": 1,
                "revision": revision + 1,
                "preferences": preferences,
                "last_mutation": {
                    "operation_id": context.operation_id,
                    "task_id": context.task_id,
                    "command_digest": context.command_digest,
                    "result_revision": revision + 1,
                    "changed_fields": changed,
                },
            }
            if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 2048:
                raise ToolNotStartedError("Memory profile too large", code="memory_profile_invalid")
            try:
                await self.resource.abatch([PutOp(namespace, "profile", value)])
            except (psycopg.Error, PoolClosed, PoolTimeout, TimeoutError):
                return result("unknown")
            return MemoryMutationResult(
                status="applied",
                operation_id=context.operation_id,
                revision=revision + 1,
                changed_fields=changed,
                preferences=preferences,
            )
