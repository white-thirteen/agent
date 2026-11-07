"""Create immutable per-run context and adapt runtime events for SSE."""

from collections.abc import AsyncIterator
from uuid import uuid4

from app.runtime.agent_runtime import AgentContext, AgentRuntime
from app.streaming.formatter import format_events


class AgentService:
    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime

    @property
    def is_ready(self) -> bool:
        return self._runtime.is_ready

    def stream_chat(
        self, *, user_id: str, conversation_id: str, workflow_id: str, message: str
    ) -> AsyncIterator[dict[str, str]]:
        context = AgentContext(
            user_id=user_id,
            conversation_id=conversation_id,
            workflow_id=workflow_id,
            run_id=str(uuid4()),
            message=message,
        )
        return format_events(self._runtime.stream(context))
