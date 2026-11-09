"""Trusted preparation contracts, separate from stage 02 Task execution contexts."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


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
