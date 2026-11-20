"""Three-layer tool filtering, trusted purpose specs, and selection records."""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.types import AgentType, TaskType
from app.tools.models import ToolBrief


def selection_digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class PurposeSpec:
    """Trusted business purpose defining model-discoverable tool bounds."""

    purpose: str
    agent_type: AgentType
    task_type: TaskType
    allowed_tools: frozenset[str]
    max_selected_tools: int = 1
    require_tool: bool = True
    rules_version: str = "v2-03-1"

    def __post_init__(self):
        if (
            not self.purpose.strip()
            or self.task_type.target_agent is not self.agent_type
            or self.max_selected_tools < 1
        ):
            raise ValueError("Invalid tool purpose specification")


PRODUCTION_PURPOSES: dict[str, PurposeSpec] = {
    "order.get": PurposeSpec(
        purpose="order.get",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order"}),
        max_selected_tools=1,
        require_tool=True,
    ),
    "order.list": PurposeSpec(
        purpose="order.list",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"list_orders"}),
        max_selected_tools=1,
        require_tool=True,
    ),
    "knowledge.search": PurposeSpec(
        purpose="knowledge.search",
        agent_type=AgentType.KNOWLEDGE,
        task_type=TaskType.KNOWLEDGE_QA,
        allowed_tools=frozenset({"search_knowledge"}),
        max_selected_tools=1,
        require_tool=True,
    ),
    "refund.plan": PurposeSpec(
        purpose="refund.plan",
        agent_type=AgentType.REFUND,
        task_type=TaskType.REFUND_APPLY,
        allowed_tools=frozenset({"refund_order"}),
        max_selected_tools=1,
        require_tool=True,
    ),
}


def get_production_purpose(purpose: str) -> PurposeSpec:
    spec = PRODUCTION_PURPOSES.get(purpose)
    if spec is None:
        raise ValueError(f"Unknown production tool purpose: {purpose}")
    return spec


def filter_discoverable_briefs(
    registry,
    *,
    purpose_spec: PurposeSpec,
    permission_scopes: frozenset[str],
    agent_type: AgentType,
    task_type: TaskType,
) -> tuple[ToolBrief, ...]:
    """Filter metadata-only briefs by AgentType, permissions, discoverability, and purpose."""
    if (
        agent_type is not purpose_spec.agent_type
        or task_type is not purpose_spec.task_type
        or task_type.target_agent is not agent_type
    ):
        raise ValueError("Trusted purpose does not match agent or task type")
    return registry.list_brief(
        agent_type=agent_type,
        permission_scopes=permission_scopes,
        discoverable_only=True,
        allowed_names=purpose_spec.allowed_tools,
    )


def scope_digest(scopes: Iterable[str]) -> str:
    return selection_digest(sorted(scopes))


def candidates_digest(briefs: Iterable[ToolBrief]) -> str:
    return selection_digest(
        [{"name": b.name, "version": b.version, "description": b.description} for b in briefs]
    )


class SelectedToolEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)
    schema_digest: str = Field(min_length=1, max_length=128)


class ToolSelectionRecord(BaseModel):
    """Serializable per-task selection record; selected_tools is derived, never authoritative."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_version: Literal[1] = 1
    user_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    agent_type: AgentType
    task_type: TaskType
    purpose: str = Field(min_length=1, max_length=128)
    need_digest: str = Field(min_length=1, max_length=64)
    scope_digest: str = Field(min_length=1, max_length=64)
    candidates_digest: str = Field(min_length=1, max_length=64)
    catalog_version: str = Field(min_length=1, max_length=64)
    rules_version: str = Field(min_length=1, max_length=64)
    selected: list[SelectedToolEntry] = Field(default_factory=list)
    method: Literal["deterministic", "singleton", "model", "none"]
    generation: int = Field(default=1, ge=1)
    rediscovery_count: int = Field(default=0, ge=0, le=1)

    @property
    def selected_tools(self) -> list[tuple[str, str]]:
        return [(item.name, item.version) for item in self.selected]
