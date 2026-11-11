"""Environment/ordinary identity boundaries and preparation-only HTTP behavior."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_agent_service, resolve_demo_identity
from app.core.config import Settings
from app.core.errors import (
    AgentNotReadyError,
    DemoIdentityDisabledError,
    DemoUserNotAllowedError,
    SessionUnavailableError,
)
from app.infrastructure.sessions import SessionBinding
from app.main import create_app
from app.runtime.context import DemoContext, SubmitOptions


def test_identity_environment_allowlist_and_ordinary_scopes():
    identity = resolve_demo_identity(user_id="dev-user", settings=Settings(_env_file=None))
    assert identity.permission_scopes == frozenset(
        {
            "orders:read",
            "refunds:request",
            "knowledge:read",
            "memory:read",
            "memory:write",
        }
    )
    with pytest.raises(DemoUserNotAllowedError):
        resolve_demo_identity(user_id="unknown", settings=Settings(_env_file=None))
    with pytest.raises(DemoIdentityDisabledError):
        resolve_demo_identity(
            user_id="dev-user", settings=Settings(_env_file=None, app_env="production")
        )


def test_route_parses_once_and_transfers_context_options():
    calls = []

    class PreparationObserver:
        async def prepare_chat(self, **kwargs):
            calls.append(kwargs)
            return DemoContext(
                kwargs["identity"].user_id,
                kwargs["conversation_id"],
                str(uuid4()),
                str(uuid4()),
                kwargs["message"],
                kwargs["identity"].permission_scopes,
            ), SubmitOptions(kwargs["input_mode"], kwargs["request_id"])

        async def submit_chat(self, context, *, options, subscription_owner):
            assert options.request_id == calls[0]["request_id"]
            assert context.message == calls[0]["message"]
            assert subscription_owner is not None
            raise AgentNotReadyError()

    app = create_app(Settings(_env_file=None, app_env="test"))
    app.dependency_overrides[get_agent_service] = lambda: PreparationObserver()
    body = {"user_id": "dev-user", "conversation_id": "session", "message": " hello "}
    request_id = uuid4()
    with TestClient(app) as client:
        response = client.post(
            "/agent/chat", json={**body, "input_mode": "new_task", "request_id": str(request_id)}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "agent_not_ready"
        assert calls[0]["message"] == "hello"
        assert calls[0]["request_id"] == request_id
        for field in ("workflow_id", "task_id", "thread_id", "permission_scopes"):
            assert client.post("/agent/chat", json={**body, field: "untrusted"}).status_code == 422
        assert len(calls) == 1
        assert client.post("/agent/chat", json={**body, "user_id": "unknown"}).status_code == 403
        parameters = (
            client.get("/openapi.json").json()["paths"]["/agent/chat"]["post"].get("parameters", [])
        )
        assert parameters == []


@pytest.mark.parametrize("field", ["user_id", "conversation_id"])
def test_nul_identifiers_are_rejected_before_preparation(field):
    service = AsyncMock()
    app = create_app(Settings(_env_file=None, app_env="test"))
    app.dependency_overrides[get_agent_service] = lambda: service
    body = {"user_id": "dev-user", "conversation_id": "session", "message": "hello"}
    body[field] = "qa\x00probe"
    with TestClient(app) as client:
        response = client.post("/agent/chat", json=body)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"][0]["loc"] == ["body", field]
    service.prepare_chat.assert_not_awaited()


def test_unicode_identifiers_are_normalized_before_preparation():
    service = AsyncMock()
    service.prepare_chat.side_effect = AgentNotReadyError()
    app = create_app(Settings(_env_file=None, app_env="test", demo_user_ids=(" 演示用户 ",)))
    app.dependency_overrides[get_agent_service] = lambda: service
    with TestClient(app) as client:
        response = client.post(
            "/agent/chat",
            json={"user_id": " 演示用户 ", "conversation_id": " 会话一 ", "message": " hello "},
        )
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "agent_not_ready"
    arguments = service.prepare_chat.await_args.kwargs
    assert arguments["identity"].user_id == "演示用户"
    assert arguments["conversation_id"] == "会话一"
    assert arguments["message"] == "hello"
    service.prepare_chat.assert_awaited_once()


def test_production_rejects_before_preparation_and_database_errors_precede_sse():
    body = {"user_id": "dev-user", "conversation_id": "session", "message": "hello"}

    class FailedSessions:
        async def prepare_chat(self, **kwargs):
            raise SessionUnavailableError()

    for environment, code in (
        ("production", "demo_identity_disabled"),
        ("test", "session_unavailable"),
    ):
        app = create_app(Settings(_env_file=None, app_env=environment))
        app.dependency_overrides[get_agent_service] = lambda: FailedSessions()
        with TestClient(app) as client:
            response = client.post("/agent/chat", json=body)
            assert response.status_code == 503
            assert response.headers["content-type"].startswith("application/json")
            assert response.json()["error"]["code"] == code
            assert not client.get("/health").json()["agent_ready"]


async def test_prepare_chat_returns_context_options_without_executing_graph():
    from app.runtime.agent_runtime import AgentRuntime, RunLimits
    from app.services.agent_service import AgentService

    class Sessions:
        async def get_or_create(self, *, user_id, conversation_id):
            return SessionBinding(user_id, conversation_id, uuid4(), datetime.now(UTC))

    service = AgentService(AgentRuntime(object(), run_limits=RunLimits(120, 12)), Sessions())
    identity = resolve_demo_identity(user_id="dev-user", settings=Settings(_env_file=None))
    request_id = uuid4()
    context, options = await service.prepare_chat(
        identity=identity,
        conversation_id="session",
        message="hello",
        input_mode="new_task",
        request_id=request_id,
    )
    assert options == SubmitOptions("new_task", request_id)
    assert context.user_id == "dev-user"
    assert not hasattr(context, "task_id")
    assert not hasattr(context, "workflow_id")
