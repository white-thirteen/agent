"""Frozen tool catalog. Discovery exposes schema and metadata, never handlers."""

import inspect
import re
from copy import deepcopy

from pydantic import BaseModel

from app.tools.models import ToolDefinition, ToolView


class ToolRegistry:
    def __init__(self):
        self._definitions: dict[str, ToolDefinition] = {}
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def register(self, definition: ToolDefinition) -> None:
        if self._frozen:
            raise RuntimeError("Tool registry is frozen")
        metadata = definition.metadata
        if metadata.name in self._definitions:
            raise ValueError("Duplicate tool name")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", metadata.name):
            raise ValueError("Invalid tool name")
        if (
            not metadata.version.strip()
            or not metadata.description.strip()
            or not metadata.allowed_agents
            or metadata.timeout_seconds <= 0
            or metadata.max_retries not in (0, 1)
        ):
            raise ValueError("Invalid tool metadata")
        if metadata.risk_level not in ("low", "medium", "high") or metadata.idempotency not in (
            "not_applicable",
            "operation_id_required",
        ):
            raise ValueError("Invalid tool risk or idempotency")
        if metadata.read_only and (
            metadata.has_business_side_effects or metadata.idempotency != "not_applicable"
        ):
            raise ValueError("Invalid read-only metadata")
        if metadata.has_business_side_effects and (metadata.read_only or metadata.max_retries):
            raise ValueError("Side effects cannot use read-only retries")
        if metadata.has_business_side_effects and metadata.idempotency != "operation_id_required":
            raise ValueError("Side effects require an operation id")
        if metadata.risk_level == "high" and not metadata.approval_required:
            raise ValueError("High-risk tools require approval")
        if not inspect.iscoroutinefunction(definition.handler):
            raise ValueError("Tool handler must be async")
        for schema in (definition.args_schema, definition.result_schema):
            if not isinstance(schema, type) or not issubclass(schema, BaseModel):
                raise ValueError("Tool schemas must be Pydantic models")
            schema.model_json_schema()
        self._definitions[metadata.name] = definition

    def freeze(self) -> None:
        self._frozen = True

    def get(self, name: str) -> ToolDefinition | None:
        if not self._frozen:
            raise RuntimeError("Tool registry must be frozen")
        return self._definitions.get(name)

    def list(self, *, agent_type, permission_scopes) -> tuple[ToolView, ...]:
        if not self._frozen:
            raise RuntimeError("Tool registry must be frozen")
        views = []
        for name, definition in sorted(self._definitions.items()):
            meta = definition.metadata
            if (
                meta.enabled
                and agent_type in meta.allowed_agents
                and meta.required_scopes <= permission_scopes
            ):
                views.append(
                    ToolView(
                        meta,
                        {
                            "type": "function",
                            "function": {
                                "name": name,
                                "description": meta.description,
                                "parameters": deepcopy(definition.args_schema.model_json_schema()),
                            },
                        },
                    )
                )
        return tuple(views)
