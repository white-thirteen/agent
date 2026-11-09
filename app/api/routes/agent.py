"""Chat transport; execution is delegated to the service and runtime."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.api.dependencies import get_agent_service, resolve_demo_identity
from app.api.schemas.chat import ChatRequest
from app.core.errors import AgentNotReadyError
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post(
    "/chat",
    response_class=EventSourceResponse,
    responses={
        200: {"description": "Agent event stream", "content": {"text/event-stream": {}}},
        503: {"description": "Agent graph has not been initialized"},
    },
)
async def chat(
    body: ChatRequest,
    request: Request,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> EventSourceResponse:
    identity = resolve_demo_identity(user_id=body.user_id, settings=request.app.state.settings)
    await service.prepare_chat(
        identity=identity,
        conversation_id=body.conversation_id,
        message=body.message,
        input_mode=body.input_mode,
        request_id=body.request_id,
    )
    # 02 will submit context/options under Runtime admission before starting SSE.
    raise AgentNotReadyError()
