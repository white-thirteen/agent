"""Task budgets and safe immutable views, distinct from live Run records."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from app.runtime.model_gateway import ModelCallUsage

if TYPE_CHECKING:
    import asyncio

    from app.runtime.context import DemoContext, RunExecutionContext
    from app.streaming.subscription import EventSubscription


@dataclass(frozen=True, slots=True)
class RunLimits:
    active_timeout_seconds: float
    max_tool_calls: int


@dataclass(frozen=True, slots=True)
class RunUsage:
    tool_calls: int = 0
    active_elapsed_ms: int = 0


class TaskStatus(StrEnum):
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    WAITING_INPUT = "waiting_input"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class RunView:
    run_id: str
    task_id: str
    workflow_id: str
    run_status: RunStatus
    task_status: TaskStatus
    final_answer: str | None
    sources: list[dict]
    error: dict | None
    model_call_usage: ModelCallUsage
    run_usage: RunUsage
    usage_complete: bool
    started_at: datetime
    ended_at: datetime | None


@dataclass(frozen=True, slots=True)
class TaskView:
    task_id: str
    workflow_id: str
    task_status: TaskStatus
    run_id: str
    model_call_usage: ModelCallUsage
    run_usage: RunUsage
    blocking_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RunHandle:
    run_id: str
    task_id: str
    workflow_id: str
    subscription: "EventSubscription | None"


@dataclass(frozen=True, slots=True)
class ResumeAcceptance:
    accepted: bool
    run_id: str | None
    task_id: str
    operation_id: str
    status: str
    result: object | None = None


@dataclass(slots=True)
class RunRecord:
    """Owned by Runtime. Never serialize this object or put it in a checkpoint."""

    context: "DemoContext"
    execution: "RunExecutionContext"
    request_id: UUID | None
    fingerprint: tuple[str, str]
    started_at: datetime
    run_status: RunStatus = RunStatus.RUNNING
    task_status: TaskStatus = TaskStatus.RUNNING
    ended_at: datetime | None = None
    finished_at: float | None = None
    final_answer: str | None = None
    sources: list[dict] = field(default_factory=list)
    error: dict | None = None
    usage_complete: bool = True
    sequence: int = 0
    task: "asyncio.Task | None" = None
    subscription: "EventSubscription | None" = None
