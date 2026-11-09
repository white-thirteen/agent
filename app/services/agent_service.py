"""Create immutable per-run context and adapt runtime events for SSE."""

from collections.abc import AsyncIterator
from typing import Literal
from uuid import UUID, uuid4

from app.core.errors import AgentNotReadyError
from app.infrastructure.sessions import SessionRepository
from app.runtime.agent_runtime import AgentContext, AgentRuntime
from app.runtime.context import DemoContext, DemoIdentity, SubmitOptions
from app.streaming.formatter import format_events


class AgentService:
    def __init__(self, runtime: AgentRuntime, sessions: SessionRepository | None = None) -> None:
        self._runtime = runtime
        self._sessions = sessions

    @property
    def is_ready(self) -> bool:
        return self._runtime.is_ready and self._sessions is not None

    async def prepare_chat(
        self,
        *,
        identity: DemoIdentity,
        conversation_id: str,
        message: str,
        input_mode: Literal["auto", "new_task"] = "auto",
        request_id: UUID | None = None,
    ) -> tuple[DemoContext, SubmitOptions]:
        """Bind the owner's persistent session before preparing candidate Run metadata.

        No formal Task, Graph invocation or admission happens at this boundary.
        """
        if not self.is_ready:
            raise AgentNotReadyError()
        binding = await self._sessions.get_or_create(
            user_id=identity.user_id,
            conversation_id=conversation_id,
        )
        return DemoContext(
            user_id=identity.user_id,
            conversation_id=conversation_id,
            thread_id=str(binding.thread_id),
            run_id=str(uuid4()),
            message=message,
            permission_scopes=identity.permission_scopes,
        ), SubmitOptions(input_mode=input_mode, request_id=request_id)

    def stream_chat(
        self, *, user_id: str, conversation_id: str, workflow_id: str, message: str
    ) -> AsyncIterator[dict[str, str]]:
        """Legacy execution adapter, retained for 02 migration and disconnected from HTTP."""
        context = AgentContext(
            user_id=user_id,
            conversation_id=conversation_id,
            workflow_id=workflow_id,
            run_id=str(uuid4()),
            message=message,
        )
        return format_events(self._runtime.stream(context))
