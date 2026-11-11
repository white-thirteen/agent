"""Owned ASGI failure paths and actual TCP disconnect through the formal routes."""

import asyncio
import json
import socket

import httpx
import pytest
import uvicorn
from fastapi.responses import Response
from runtime_support import ControlledModel, clarify, http_application

from app.api.routes import agent
from app.streaming.subscription import SubscriptionOwner

BODY = {"user_id": "dev-user", "conversation_id": "http-session", "message": "hello"}


async def test_three_http_interfaces_status_isolation_snapshot_and_replay_rejection():
    model = ControlledModel([clarify()])
    app, runtime, sessions = http_application(model)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as client:
        response = await client.post("/agent/chat", json=BODY)
        assert response.status_code == 200
        frames = response.text.replace("\r\n", "\n").strip().split("\n\n")
        data = [json.loads(frame.split("data: ", 1)[1]) for frame in frames]
        run = data[0]["run_id"]
        assert data[-1]["task_status"] == "needs_input"
        assert sum(frame.startswith("event: done") for frame in frames) == 1
        assert "thread_id" not in response.text and "permission_scopes" not in response.text
        base = f"/agent/runs/{run}"
        status = await client.post(
            base + "/status", json={k: BODY[k] for k in ("user_id", "conversation_id")}
        )
        assert status.json()["run_status"] == "waiting_input"
        assert status.json()["workflow_id"] == status.json()["task_id"]
        replay = await client.post(
            base + "/events", json={k: BODY[k] for k in ("user_id", "conversation_id")}
        )
        assert [
            frame.splitlines()[0]
            for frame in replay.text.replace("\r\n", "\n").strip().split("\n\n")
        ] == ["event: status", "event: done"]
        bad = await client.post(
            base + "/events",
            json={k: BODY[k] for k in ("user_id", "conversation_id")},
            headers={"Last-Event-ID": "1"},
        )
        assert (
            bad.status_code == 409 and bad.json()["error"]["code"] == "event_replay_not_supported"
        )
        before = sessions.creations
        for suffix in ("status", "events"):
            wrong = await client.post(
                base + "/" + suffix, json={"user_id": "demo-user-b", "conversation_id": "unknown"}
            )
            assert wrong.status_code == 404 and wrong.json()["error"]["code"] == "run_not_found"
        assert sessions.creations == before and model.calls == 1
        assert (
            await client.post(base + "/status", json={**BODY, "thread_id": "fake"})
        ).status_code == 422
    await runtime.shutdown()


@pytest.mark.parametrize("failure", ["construct", "preiterate", "headers"])
async def test_request_guard_cleans_before_first_iteration_and_execution_continues(
    monkeypatch, failure
):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked(messages):
        entered.set()
        await release.wait()
        return clarify()

    app, runtime, _ = http_application(ControlledModel([blocked]))
    iterated = False
    original_stream = app.state.agent_service.stream_chat

    def observed_stream(handle):
        async def events():
            nonlocal iterated
            iterated = True
            async for event in original_stream(handle):
                yield event

        return events()

    app.state.agent_service.stream_chat = observed_stream
    if failure != "headers":

        class FailingResponse(Response):
            async def __call__(self, scope, receive, send):
                raise asyncio.CancelledError()

        def response_factory(*args, **kwargs):
            if failure == "construct":
                raise ValueError("response construction failed")
            return FailingResponse()

        monkeypatch.setattr(agent, "EventSourceResponse", response_factory)
    data = json.dumps(BODY).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/agent/chat",
        "raw_path": b"/agent/chat",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1),
        "server": ("local", 80),
        "state": {},
    }
    sent_body = False

    async def receive():
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": data, "more_body": False}
        await asyncio.Event().wait()

    async def send(message):
        if failure == "headers" and message["type"] == "http.response.start":
            raise OSError("response header send failed")

    with pytest.raises((ValueError, asyncio.CancelledError, OSError, ExceptionGroup)):
        await app(scope, receive, send)
    await asyncio.wait_for(entered.wait(), 1)
    record = next(iter(runtime._records.values()))
    assert scope["state"]["subscription_owner"].closed
    assert record.subscription is None and not record.task.done()
    if failure != "headers":
        assert not iterated
    subscription = await runtime.subscribe(
        user_id=BODY["user_id"],
        conversation_id=BODY["conversation_id"],
        run_id=record.context.run_id,
        subscription_owner=SubscriptionOwner(),
    )
    release.set()
    events = [event async for event in subscription]
    assert sum(event.kind == "done" for event in events) == 1
    assert record.run_status == "waiting_input"
    await runtime.shutdown()


async def test_real_tcp_disconnect_releases_subscription_and_run_finishes():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked(messages):
        entered.set()
        await release.wait()
        return clarify()

    model = ControlledModel([blocked])
    app, runtime, _ = http_application(model)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(3):
            while not server.started:
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=3) as client:
            async with client.stream("POST", "/agent/chat", json=BODY) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        run = json.loads(line[6:])["run_id"]
                        break
            # Exiting the real socket stream closes its TCP response mid-execution.
            await entered.wait()
            record = runtime._records[run]
            async with asyncio.timeout(3):
                while record.subscription is not None:
                    await asyncio.sleep(0.01)
            assert not record.task.done()
            body = {k: BODY[k] for k in ("user_id", "conversation_id")}
            status = await client.post(f"/agent/runs/{run}/status", json=body)
            assert status.json()["run_status"] == "running"
            release.set()
            await record.task
            final = await client.post(f"/agent/runs/{run}/status", json=body)
            assert final.json()["task_status"] == "needs_input"
            attached = await client.post(f"/agent/runs/{run}/events", json=body)
            assert attached.status_code == 200 and "event: done" in attached.text
            assert "event: token" not in attached.text and model.calls == 1
    finally:
        release.set()
        server.should_exit = True
        await asyncio.wait_for(serving, 5)
        listener.close()
    assert not runtime._claims and runtime._stopping
