"""Agent roles, task ownership and immutable provider-independent configuration."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class AgentType(StrEnum):
    """Execution roles, distinct from the business tasks they handle."""

    SUPERVISOR = "supervisor"
    ORDER = "order"
    REFUND = "refund"
    KNOWLEDGE = "knowledge"


class TaskType(StrEnum):
    """Supported tasks; unknown values must be rejected before dispatch."""

    ORDER_QUERY = "order_query"
    REFUND_APPLY = "refund_apply"
    KNOWLEDGE_QA = "knowledge_qa"
    CLARIFICATION = "clarification"
    MEMORY_MANAGE = "memory_manage"

    @property
    def target_agent(self) -> AgentType:
        """Return task ownership, not permission to execute tools or business actions."""
        return _TASK_AGENTS[self]


_TASK_AGENTS: Final[Mapping[TaskType, AgentType]] = MappingProxyType(
    {
        TaskType.ORDER_QUERY: AgentType.ORDER,
        TaskType.REFUND_APPLY: AgentType.REFUND,
        TaskType.KNOWLEDGE_QA: AgentType.KNOWLEDGE,
        TaskType.CLARIFICATION: AgentType.SUPERVISOR,
        TaskType.MEMORY_MANAGE: AgentType.KNOWLEDGE,
    }
)


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """Shareable agent definition; contains no request state or model credentials."""

    agent_type: AgentType
    system_prompt: str
