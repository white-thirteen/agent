"""Trusted preparation contracts, separate from stage 02 Task execution contexts."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    from app.graph.contracts import ExecutionContext
    from app.runtime.run_scope import RunScope


@dataclass(frozen=True, slots=True)
class DemoIdentity:
    user_id: str
    permission_scopes: frozenset[str]


@dataclass(frozen=True, slots=True)
class DemoContext:
    user_id: str
    conversation_id: str
    thread_id: str
    run_id: str  # Candidate only. Runtime admission in 02 makes a Run effective.
    message: str
    permission_scopes: frozenset[str]


@dataclass(frozen=True, slots=True)
class SubmitOptions:
    input_mode: Literal["auto", "new_task"] = "auto"
    request_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RefundRecoveryContext:
    """This Run's trusted reconciliation result; never a client or checkpoint input."""

    thread_id: str
    task_id: str
    workflow_id: str
    application_id: str
    approval_id: str
    operation_id: str
    call_id: str
    expected_call_digest: str
    source_checkpoint_ns: str
    source_checkpoint_id: str
    prior_attempt_id: str | None
    disposition: Literal["succeeded", "not_executed", "unknown"]
    committed_result: dict | None
    allow_model: bool = True


@dataclass(frozen=True, slots=True)
class RunExecutionContext:
    """Live context propagated through LangGraph's non-checkpoint context channel."""

    context: "ExecutionContext"
    thread_id: str
    permission_scopes: frozenset[str]
    scope: "RunScope"
    execution_mode: Literal["normal", "resume", "reconcile"] = "normal"
    refund_recovery: RefundRecoveryContext | None = None

    def __post_init__(self):
        if self.refund_recovery is not None and self.execution_mode != "reconcile":
            raise ValueError("Refund reconciliation requires reconcile mode")
