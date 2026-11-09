"""Verify the HTTP/service boundary without external model or database access."""

import json
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sse_starlette.sse import EventSourceResponse

from app.core.config import Settings
from app.main import create_app
from app.runtime.agent_runtime import AgentContext, AgentRuntime
from app.services.agent_service import AgentService
from app.streaming.events import StreamEvent


@pytest.fixture
def application():
    return create_app(Settings(_env_file=None, app_env="test"))


def chat_body():
    return {
        "user_id": "dev-user",
        "conversation_id": "conversation-1",
        "message": "hello",
    }


def test_health_and_openapi_work_without_external_services(application):
    with TestClient(application) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["agent_ready"] is False
        schema = client.get("/openapi.json").json()
        assert (
            "text/event-stream"
            in schema["paths"]["/agent/chat"]["post"]["responses"]["200"]["content"]
        )


def test_chat_reports_unavailable_before_starting_stream(application):
    with TestClient(application) as client:
        response = client.post("/agent/chat", json=chat_body())
        assert response.status_code == 503
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["error"]["code"] == "agent_not_ready"


@pytest.mark.parametrize("message", ["", "   ", "x" * 32001])
def test_invalid_message_is_rejected(application, message):
    body = chat_body()
    body["message"] = message
    with TestClient(application) as client:
        assert client.post("/agent/chat", json=body).status_code == 422


def test_unexpected_request_fields_are_rejected(application):
    with TestClient(application) as client:
        assert (
            client.post("/agent/chat", json={**chat_body(), "api_key": "unused"}).status_code == 422
        )


def test_sse_transport_preserves_payload_and_isolates_run_context(application):
    contexts: list[AgentContext] = []

    class TestRuntime(AgentRuntime):
        @property
        def is_ready(self) -> bool:
            return True

        def stream(self, context: AgentContext) -> AsyncIterator[StreamEvent]:
            contexts.append(context)

            async def events():
                yield StreamEvent(event="token", data={"content": "你好\n第二行"})
                yield StreamEvent(event="done", data={"run_id": context.run_id})

            return events()

    service = AgentService(TestRuntime())
    # Exercise the retained formatter/transport independently while 01 HTTP stops at preparation.
    transport_app = FastAPI()

    @transport_app.get("/transport/{user_id}")
    def transport(user_id: str):
        return EventSourceResponse(
            service.stream_chat(
                user_id=user_id,
                conversation_id="conversation-1",
                workflow_id="legacy-workflow",
                message="hello",
            )
        )

    with TestClient(transport_app) as client:
        for user_id in ("user-1", "user-2"):
            response = client.get(f"/transport/{user_id}")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            frames = response.text.replace("\r\n", "\n").strip().split("\n\n")
            assert frames[0].startswith("event: token\n")
            payload = json.loads(frames[0].split("data: ", 1)[1])
            assert payload == {"content": "你好\n第二行"}
            final_payload = json.loads(frames[-1].split("data: ", 1)[1])
            assert final_payload["run_id"] == contexts[-1].run_id
    assert [context.user_id for context in contexts] == ["user-1", "user-2"]
    assert contexts[0].run_id != contexts[1].run_id
