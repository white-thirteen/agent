"""Chat transport; execution is delegated to the service and runtime."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.api.dependencies import get_agent_service
from app.api.schemas.chat import ChatRequest
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
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> EventSourceResponse:
    # Resolve readiness before sending HTTP response headers.
    events = service.stream_chat(
        user_id=body.user_id,
        conversation_id=body.conversation_id,
        workflow_id=body.workflow_id,
        message=body.message,
    )
    return EventSourceResponse(events, ping=15, headers={"Cache-Control": "no-cache"})
