"""Verify the HTTP/service boundary without external model or database access."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sse_starlette.sse import EventSourceResponse

from app.core.config import Settings
from app.main import create_app


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
    from uuid import uuid4

    from app.streaming.events import RuntimeEvent
    from app.streaming.formatter import format_events

    runs = []
    transport_app = FastAPI()

    @transport_app.get("/transport/{user_id}")
    def transport(user_id: str):
        run_id = str(uuid4())
        runs.append((user_id, run_id))

        async def events():
            yield RuntimeEvent("token", run_id, "task", 1, {"content": "你好\n第二行"})
            yield RuntimeEvent(
                "done", run_id, "task", 2, {"run_status": "completed", "task_status": "completed"}
            )

        return EventSourceResponse(format_events(events()))

    with TestClient(transport_app) as client:
        for user in ("user-1", "user-2"):
            response = client.get(f"/transport/{user}")
            assert response.status_code == 200
            frames = response.text.replace("\r\n", "\n").strip().split("\n\n")
            payload = json.loads(frames[0].split("data: ", 1)[1])
            assert payload["content"] == "你好\n第二行"
            assert payload["run_id"] == runs[-1][1]
            assert json.loads(frames[-1].split("data: ", 1)[1])["run_id"] == runs[-1][1]
    assert runs[0][0] != runs[1][0] and runs[0][1] != runs[1][1]
