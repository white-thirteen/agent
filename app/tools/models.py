"""Tool contracts shared by discovery, policy and the sole execution entry."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, JsonValue

from app.agents.types import AgentType, TaskType
from app.graph.contracts import ExecutionContext
from app.runtime.models import RunLimits, RunUsage
from app.runtime.run_scope import RunScope

if TYPE_CHECKING:
    from app.domain.refunds import RefundBusinessContext
    from app.workflows.approvals import InterruptBinding


@dataclass(frozen=True, slots=True)
class ToolMetadata:
    name: str
    version: str
    description: str
    enabled: bool
    allowed_agents: frozenset[AgentType]
    required_scopes: frozenset[str]
    risk_level: Literal["low", "medium", "high"]
    approval_required: bool
    read_only: bool
    has_business_side_effects: bool
    idempotency: Literal["not_applicable", "operation_id_required"]
    timeout_seconds: float
    max_retries: int
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class BusinessExecutionContext:
    user_id: str
    task_id: str
    run_id: str


@dataclass(frozen=True, slots=True)
class MemoryBusinessContext(BusinessExecutionContext):
    operation_id: str
    command_digest: str
    expected_revision: int
    replay_check_only: bool


@dataclass(frozen=True, slots=True)
class BusinessRejection:
    code: str
    message: str
    data: BaseModel | None = None


@dataclass(frozen=True, slots=True)
class HandlerResult:
    data: BaseModel | None = None
    rejection: BusinessRejection | None = None

    def __post_init__(self):
        if (self.data is None) == (self.rejection is None):
            raise ValueError("Handler result requires exactly one outcome")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    metadata: ToolMetadata
    args_schema: type[BaseModel]
    result_schema: type[BaseModel]
    handler: Callable[[BaseModel, BusinessExecutionContext], Awaitable[HandlerResult]]


@dataclass(frozen=True, slots=True)
class ToolView:
    metadata: ToolMetadata
    model_schema: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ParsedToolCall:
    call_id: str
    name: str
    raw_args: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    execution: ExecutionContext
    agent_type: AgentType
    task_type: TaskType
    node_name: str | None
    permission_scopes: frozenset[str]
    origin: Literal["model", "node"]
    allowed_tools: frozenset[tuple[str, str]]
    argument_constraints: Mapping[str, Mapping[str, JsonValue]]
    run_limits: RunLimits
    scope: RunScope
    refund_context: "RefundBusinessContext | None" = None
    approval_binding: "InterruptBinding | None" = None
    thread_id: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedToolAttempt:
    """Serializable write intent; possession never bypasses the current policy."""

    attempt_id: str
    run_id: str
    task_id: str
    call: ParsedToolCall
    tool_version: str
    normalized_args: dict[str, JsonValue]
    args_digest: str
    operation_id: str
    baseline_tool_calls: int
    attempted_tool_calls: int
    timeout_seconds: float
    business_snapshot: dict
    binding_snapshot: dict
    origin: Literal["model", "node"] = "model"
    prepared_by_node_name: str | None = None
    execution_node_name: str | None = None


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True, slots=True)
class ApprovalRequirement:
    call_id: str
    tool_name: str
    version: str
    parameters: dict
    user_id: str
    task_id: str
    workflow_id: str


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    decision: PolicyDecision
    code: str
    message: str
    validated_args: BaseModel | None = None
    approval_requirement: ApprovalRequirement | None = None


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    call_id: str
    tool_name: str
    execution_id: str
    status: Literal[
        "success",
        "business_rejected",
        "policy_denied",
        "approval_required",
        "failed",
        "not_executed",
    ]
    code: str
    message: str
    data: dict[str, JsonValue] | None
    attempts: int
    run_usage: RunUsage
    effect_status: Literal["not_applicable", "not_started", "completed", "unknown"]
    normalized_args: dict[str, JsonValue] | None = None


class ToolTransientError(RuntimeError):
    """Explicit transient read-only failure eligible for bounded retries."""


class ToolUnavailableError(RuntimeError):
    """Known technical failure whose details are private."""

    def __init__(self, message, *, code="order_query_unavailable"):
        super().__init__(message)
        self.code = code


class ToolNotStartedError(ToolUnavailableError):
    """A handler proved no business write was started."""


class ToolEffectUnknownError(RuntimeError):
    """An associated business operation has an unconfirmed durable outcome."""

    def __init__(self, data):
        super().__init__("Memory result unknown")
        self.data = data
