"""Single-parse submit, read-only status and owned no-replay event subscription."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.api.dependencies import get_agent_service, resolve_demo_identity
from app.api.schemas.chat import ChatRequest, RunRequest
from app.core.errors import RuntimeRequestError
from app.services.agent_service import AgentService
from app.streaming.formatter import format_events
from app.streaming.response import SubscriptionRoute

router = APIRouter(prefix="/agent", tags=["agent"], route_class=SubscriptionRoute)
Service = Annotated[AgentService, Depends(get_agent_service)]


def reject_replay(request: Request):
    if request.headers.get("last-event-id"):
        raise RuntimeRequestError("event_replay_not_supported")


@router.post(
    "/chat",
    response_class=EventSourceResponse,
    responses={200: {"description": "Agent event stream", "content": {"text/event-stream": {}}}},
)
async def chat(body: ChatRequest, request: Request, service: Service) -> EventSourceResponse:
    reject_replay(request)
    identity = resolve_demo_identity(user_id=body.user_id, settings=request.app.state.settings)
    context, options = await service.prepare_chat(
        identity=identity,
        conversation_id=body.conversation_id,
        message=body.message,
        input_mode=body.input_mode,
        request_id=body.request_id,
    )
    handle = await service.submit_chat(
        context, options=options, subscription_owner=request.state.subscription_owner
    )
    return EventSourceResponse(
        service.stream_chat(handle), ping=15, headers={"Cache-Control": "no-cache"}
    )


@router.post("/runs/{run_id}/status")
async def run_status(run_id: str, body: RunRequest, request: Request, service: Service):
    identity = resolve_demo_identity(user_id=body.user_id, settings=request.app.state.settings)
    return await service.get_run(
        identity=identity, conversation_id=body.conversation_id, run_id=run_id
    )


@router.post("/tasks/current")
async def current_task(body: RunRequest, request: Request, service: Service):
    identity = resolve_demo_identity(user_id=body.user_id, settings=request.app.state.settings)
    return {
        "current_task": await service.current_task(
            identity=identity, conversation_id=body.conversation_id
        )
    }


@router.post("/refunds/{application_id}/status")
async def refund_status(application_id: UUID, body: RunRequest, request: Request, service: Service):
    identity = resolve_demo_identity(user_id=body.user_id, settings=request.app.state.settings)
    return await service.refund_status(
        identity=identity, conversation_id=body.conversation_id, application_id=str(application_id)
    )


@router.post(
    "/runs/{run_id}/events",
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": "Current snapshot and future events",
            "content": {"text/event-stream": {}},
        }
    },
)
async def run_events(
    run_id: str, body: RunRequest, request: Request, service: Service
) -> EventSourceResponse:
    reject_replay(request)
    identity = resolve_demo_identity(user_id=body.user_id, settings=request.app.state.settings)
    subscription = await service.subscribe(
        identity=identity,
        conversation_id=body.conversation_id,
        run_id=run_id,
        subscription_owner=request.state.subscription_owner,
    )
    return EventSourceResponse(
        format_events(subscription), ping=15, headers={"Cache-Control": "no-cache"}
    )
