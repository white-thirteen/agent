"""Runtime boundary. Graph execution is the next development milestone."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.core.errors import AgentNotReadyError
from app.streaming.events import StreamEvent


@dataclass(frozen=True, slots=True)
class AgentContext:
    user_id: str
    conversation_id: str
    workflow_id: str
    run_id: str
    message: str


class AgentRuntime:
    @property
    def is_ready(self) -> bool:
        return False

    def stream(self, context: AgentContext) -> AsyncIterator[StreamEvent]:
        raise AgentNotReadyError("Agent graph is not implemented yet.")
