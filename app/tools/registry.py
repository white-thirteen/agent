"""Frozen tool catalog. Discovery exposes schema and metadata, never handlers."""

import inspect
import json
import re
from collections.abc import Sequence
from copy import deepcopy
from hashlib import sha256

from pydantic import BaseModel

from app.tools.models import ToolBindingRecord, ToolBrief, ToolDefinition, ToolView


class ToolRegistry:
    def __init__(self):
        self._definitions: dict[str, ToolDefinition] = {}
        self._briefs: dict[str, ToolBrief] = {}
        self._schemas: dict[str, dict] = {}
        self._schema_digests: dict[str, str] = {}
        self._catalog_version: str | None = None
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def catalog_version(self) -> str:
        if not self._frozen or self._catalog_version is None:
            raise RuntimeError("Tool registry must be frozen")
        return self._catalog_version

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
            or type(metadata.model_discoverable) is not bool
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
        if self._frozen:
            return
        briefs: dict[str, ToolBrief] = {}
        schemas: dict[str, dict] = {}
        digests: dict[str, str] = {}
        catalog_entries = []
        for name, definition in sorted(self._definitions.items()):
            meta = definition.metadata
            briefs[name] = ToolBrief(name=name, version=meta.version, description=meta.description)
            schema = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": meta.description,
                    "parameters": definition.args_schema.model_json_schema(),
                },
            }
            schemas[name] = schema
            encoded_schema = json.dumps(
                schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            schema_digest = sha256(encoded_schema.encode("utf-8")).hexdigest()
            digests[name] = schema_digest
            catalog_entries.append(
                {
                    "name": name,
                    "version": meta.version,
                    "description": meta.description,
                    "enabled": meta.enabled,
                    "allowed_agents": sorted(agent.value for agent in meta.allowed_agents),
                    "required_scopes": sorted(meta.required_scopes),
                    "model_discoverable": meta.model_discoverable,
                    "schema_digest": schema_digest,
                }
            )
        self._briefs = briefs
        self._schemas = schemas
        self._schema_digests = digests
        self._catalog_version = sha256(
            json.dumps(
                catalog_entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()[:16]
        self._frozen = True

    def get(self, name: str) -> ToolDefinition | None:
        if not self._frozen:
            raise RuntimeError("Tool registry must be frozen")
        return self._definitions.get(name)

    def schema_digest(self, name: str) -> str | None:
        if not self._frozen:
            raise RuntimeError("Tool registry must be frozen")
        return self._schema_digests.get(name)

    def list_brief(
        self,
        *,
        agent_type,
        permission_scopes,
        discoverable_only: bool = True,
        allowed_names: frozenset[str] | None = None,
    ) -> tuple[ToolBrief, ...]:
        """Return metadata-only briefs without reading or copying full parameter schemas."""
        if not self._frozen:
            raise RuntimeError("Tool registry must be frozen")
        briefs = []
        for name, definition in sorted(self._definitions.items()):
            meta = definition.metadata
            if (
                meta.enabled
                and agent_type in meta.allowed_agents
                and meta.required_scopes <= permission_scopes
                and (not discoverable_only or meta.model_discoverable)
                and (allowed_names is None or name in allowed_names)
            ):
                briefs.append(self._briefs[name])
        return tuple(briefs)

    def resolve_binding(
        self,
        *,
        selected: Sequence[tuple[str, str]] | Sequence[str],
        agent_type,
        permission_scopes,
        discoverable_only: bool = True,
        allowed_names: frozenset[str] | None = None,
        expected_catalog_version: str | None = None,
    ) -> ToolBindingRecord:
        """Validate selected tools against current permissions/versions and resolve full schemas."""
        if not self._frozen:
            raise RuntimeError("Tool registry must be frozen")
        if (
            expected_catalog_version is not None
            and self._catalog_version != expected_catalog_version
        ):
            raise ValueError("Tool catalog version mismatch")
        allowed_pairs: list[tuple[str, str]] = []
        schemas: list[dict] = []
        digests: dict[str, str] = {}
        seen: set[str] = set()
        for item in selected:
            if isinstance(item, tuple):
                name, expected_version = item
            else:
                name, expected_version = item, None
            if name in seen:
                raise ValueError("Duplicate selected tool")
            seen.add(name)
            definition = self._definitions.get(name)
            if definition is None:
                raise ValueError("Selected tool does not exist")
            meta = definition.metadata
            if (
                not meta.enabled
                or agent_type not in meta.allowed_agents
                or not meta.required_scopes <= permission_scopes
                or (discoverable_only and not meta.model_discoverable)
                or (allowed_names is not None and name not in allowed_names)
            ):
                raise ValueError("Selected tool is not allowed")
            if expected_version is not None and meta.version != expected_version:
                raise ValueError("Selected tool version mismatch")
            allowed_pairs.append((name, meta.version))
            schemas.append(deepcopy(self._schemas[name]))
            digests[name] = self._schema_digests[name]
        return ToolBindingRecord(
            allowed_tools=frozenset(allowed_pairs),
            schemas=tuple(schemas),
            schema_digests=digests,
            catalog_version=self._catalog_version,
        )

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
                views.append(ToolView(meta, deepcopy(self._schemas[name])))
        return tuple(views)
