"""Governed node-only preference tools; identity never comes from arguments."""

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.types import AgentType
from app.memory.manager import PreferenceSnapshot
from app.memory.models import MemoryCommand, MemoryMutationResult
from app.tools.models import (
    BusinessRejection,
    HandlerResult,
    ToolDefinition,
    ToolEffectUnknownError,
    ToolMetadata,
)


class ReadPreferencesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def read_preferences_tool(reader, *, enabled):
    async def read(args, context):
        return HandlerResult(data=await reader.read_preferences(user_id=context.user_id))

    return ToolDefinition(
        ToolMetadata(
            name="read_preferences",
            version="1",
            description="Read the current user's presentation preferences.",
            enabled=enabled,
            allowed_agents=frozenset({AgentType.ORDER, AgentType.REFUND, AgentType.KNOWLEDGE}),
            required_scopes=frozenset({"memory:read"}),
            risk_level="low",
            approval_required=False,
            read_only=True,
            has_business_side_effects=False,
            idempotency="not_applicable",
            timeout_seconds=3,
            max_retries=1,
            tags=frozenset({"memory", "read"}),
        ),
        ReadPreferencesArgs,
        PreferenceSnapshot,
        read,
    )


class WritePreferencesArgs(MemoryCommand):
    @model_validator(mode="after")
    def write_only(self):
        if self.operation == "read":
            raise ValueError("Read is not a mutation")
        return self


def write_preferences_tool(manager, *, enabled):
    async def write(args, context):
        result = await manager.apply(
            MemoryCommand.model_validate(args.model_dump()), context=context
        )
        if result.status == "unknown":
            raise ToolEffectUnknownError(result)
        if result.status == "conflict":
            return HandlerResult(
                rejection=BusinessRejection(
                    "memory_revision_conflict", "Preference revision conflict.", result
                )
            )
        return HandlerResult(data=result)

    return ToolDefinition(
        ToolMetadata(
            name="write_preferences",
            version="1",
            description="Apply a verified explicit preference command.",
            enabled=enabled,
            allowed_agents=frozenset({AgentType.KNOWLEDGE}),
            required_scopes=frozenset({"memory:write"}),
            risk_level="low",
            approval_required=False,
            read_only=False,
            has_business_side_effects=True,
            idempotency="operation_id_required",
            timeout_seconds=3,
            max_retries=0,
            tags=frozenset({"memory", "explicit", "write"}),
        ),
        WritePreferencesArgs,
        MemoryMutationResult,
        write,
    )
