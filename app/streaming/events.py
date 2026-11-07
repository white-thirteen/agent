"""Public SSE event envelope; individual payload schemas will evolve with the graph."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

EventType = Literal[
    "token", "status", "tool_start", "tool_end", "approval_required", "done", "error"
]


class StreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: EventType
    data: dict[str, Any]
