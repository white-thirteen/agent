"""Request dependencies backed by application-scoped services."""

from fastapi import Request

from app.core.config import Settings
from app.core.errors import DemoIdentityDisabledError, DemoUserNotAllowedError
from app.runtime.context import DemoIdentity
from app.services.agent_service import AgentService

DEMO_PERMISSION_SCOPES = frozenset(
    {
        "orders:read",
        "refunds:request",
        "knowledge:read",
        "memory:read",
        "memory:write",
    }
)


def resolve_demo_identity(*, user_id: str, settings: Settings) -> DemoIdentity:
    """Resolve only Route-validated identities. Ordinary scopes grant no approval rights."""
    if settings.app_env not in ("development", "test"):
        raise DemoIdentityDisabledError()
    if user_id not in settings.demo_user_ids:
        raise DemoUserNotAllowedError()
    return DemoIdentity(user_id, DEMO_PERMISSION_SCOPES)


def get_agent_service(request: Request) -> AgentService:
    return request.app.state.agent_service
