"""Explicit preference control; identities are resolved by the server."""

import psycopg
from fastapi import APIRouter, Request
from psycopg_pool import PoolClosed, PoolTimeout

from app.api.dependencies import resolve_demo_identity
from app.api.schemas.chat import Identifier
from app.api.schemas.preferences import PreferenceIdentity, PreferenceMutation
from app.core.errors import AgentNotReadyError, RuntimeRequestError
from app.tools.models import ToolUnavailableError

router = APIRouter(prefix="/agent/preferences", tags=["preferences"])


def service_and_identity(request, user_id):
    identity = resolve_demo_identity(user_id=user_id, settings=request.app.state.settings)
    service = request.app.state.preference_service
    if service is None:
        raise AgentNotReadyError()
    return service, identity


async def execute(operation):
    try:
        return await operation
    except (psycopg.Error, PoolClosed, PoolTimeout, ToolUnavailableError, TimeoutError):
        raise RuntimeRequestError("preference_unavailable") from None


@router.post("/read")
async def read(body: PreferenceIdentity, request: Request):
    service, identity = service_and_identity(request, body.user_id)
    return await execute(service.read(identity))


@router.post("/mutations")
async def mutate(body: PreferenceMutation, request: Request):
    service, identity = service_and_identity(request, body.user_id)
    return await execute(
        service.mutate(identity, body.operation_id, body.expected_revision, body.command)
    )


@router.post("/operations/{operation_id}/status")
async def status(operation_id: Identifier, body: PreferenceIdentity, request: Request):
    service, identity = service_and_identity(request, body.user_id)
    return await execute(service.status(identity, operation_id))
