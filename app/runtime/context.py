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
class RunExecutionContext:
    """Live context propagated through LangGraph's non-checkpoint context channel."""

    context: "ExecutionContext"
    thread_id: str
    permission_scopes: frozenset[str]
    scope: "RunScope"
