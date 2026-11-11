"""Create immutable per-run context and adapt runtime events for SSE."""

from collections.abc import AsyncIterator
from typing import Literal
from uuid import UUID, uuid4

from app.core.errors import AgentNotReadyError, RuntimeRequestError
from app.infrastructure.sessions import SessionRepository
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.context import DemoContext, DemoIdentity, SubmitOptions
from app.streaming.formatter import format_events
from app.streaming.subscription import SubscriptionOwner


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

    async def submit_chat(
        self, context: DemoContext, *, options: SubmitOptions, subscription_owner: SubscriptionOwner
    ):
        return await self._runtime.submit(
            context, options=options, subscription_owner=subscription_owner
        )

    def stream_chat(self, handle) -> AsyncIterator[dict[str, str]]:
        if handle.subscription is None:
            raise RuntimeError("Streaming requires an owned subscription")
        return format_events(handle.subscription)

    async def _verify_session(self, identity, conversation_id):
        if self._sessions is None:
            raise AgentNotReadyError()
        binding = await self._sessions.get(
            user_id=identity.user_id, conversation_id=conversation_id
        )
        if binding is None:
            raise RuntimeRequestError("run_not_found")
        return binding

    async def get_run(self, *, identity, conversation_id, run_id):
        await self._verify_session(identity, conversation_id)
        return await self._runtime.get_run(
            user_id=identity.user_id, conversation_id=conversation_id, run_id=run_id
        )

    async def subscribe(self, *, identity, conversation_id, run_id, subscription_owner):
        await self._verify_session(identity, conversation_id)
        return await self._runtime.subscribe(
            user_id=identity.user_id,
            conversation_id=conversation_id,
            run_id=run_id,
            subscription_owner=subscription_owner,
        )
