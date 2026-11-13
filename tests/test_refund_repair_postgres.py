"""Opt-in formal-topology repair and approval expiry gaps from 04-QA-007."""

import asyncio
import os
import socket
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg
import pytest
import uvicorn
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import SecretStr

from app.core.config import Settings
from app.domain.refunds import MockRefundService
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.postgres import open_pool, validate_test_target
from app.main import create_app
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from app.workflows.approvals import ApprovalService
from scripts import run_async
from scripts.verify_04_restart import Provider, database_snapshot


def test_real_repair_response_loss_concurrency_audit_and_expired_graph():
    raw = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Explicit test database required")
    settings = Settings()
    validate_test_target(SecretStr(raw), settings.database_url)
    owner = "fix02-" + uuid4().hex
    settings = settings.model_copy(
        update={
            "database_url": SecretStr(raw),
            "app_env": "test",
            "log_level": "CRITICAL",
            "demo_user_ids": (*settings.demo_user_ids, owner),
            "model_name": "controlled",
            "model_api_key": SecretStr("controlled"),
        }
    )

    async def scenario():
        pool = await open_pool(settings)
        before = await database_snapshot(pool)
        threads = []
        original_bind = ApprovalService.bind_interrupt

        async def forbidden(*args, **kwargs):
            raise AssertionError("Unexpected graph/write during repair or read")

        @asynccontextmanager
        async def waiting(kind, *, unbound=False):
            order = owner + "-" + kind
            async with pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO demo_orders VALUES (%s,%s,42.50,'CNY','paid',false,now())",
                    (order, owner),
                )

            @asynccontextmanager
            async def models(config):
                provider = Provider(order)
                yield provider, ModelGateway(provider, ModelCallLimits(8, 5, 0))

            fail_bind = unbound

            async def bind(service, approval_id, binding):
                if fail_bind:
                    raise psycopg.OperationalError("Controlled first binding failure")
                return await original_bind(service, approval_id, binding)

            with (
                patch("app.main.model_resources", models),
                patch.object(ApprovalService, "bind_interrupt", bind),
                patch.object(MockRefundService, "execute_original", forbidden),
            ):
                app = create_app(settings)
                async with app.router.lifespan_context(app):
                    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
                    async with httpx.AsyncClient(
                        transport=transport, base_url="http://test"
                    ) as client:
                        response = await client.post(
                            "/agent/chat",
                            json={
                                "user_id": owner,
                                "conversation_id": kind,
                                "message": "申请模拟退款",
                            },
                        )
                        assert response.status_code == 200
                        assert (
                            "pause_binding_unavailable" if unbound else "workflow_paused"
                        ) in response.text
                        fail_bind = False
                        async with pool.connection() as conn:
                            row = await (
                                await conn.execute(
                                    "SELECT a.approval_id,r.thread_id FROM approvals a "
                                    "JOIN refund_requests r USING(application_id) "
                                    "WHERE r.order_id=%s",
                                    (order,),
                                )
                            ).fetchone()
                        approval_id, thread = str(row[0]), str(row[1])
                        threads.append(thread)
                        yield app, client, transport, approval_id, order

        async def approval_row(approval_id):
            async with pool.connection() as conn:
                return await (
                    await conn.execute(
                        "SELECT decision,approver_id,decided_at,expires_at,interrupt_id,"
                        "checkpoint_ns,checkpoint_id FROM approvals WHERE approval_id=%s",
                        (approval_id,),
                    )
                ).fetchone()

        @asynccontextmanager
        async def tcp_clients(app):
            # The fixture already owns the formal lifespan; expose that same app on
            # a temporary loopback socket for two independent real HTTP clients.
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                address = "http://127.0.0.1:" + str(listener.getsockname()[1])
                server = uvicorn.Server(
                    uvicorn.Config(
                        app,
                        lifespan="off",
                        log_config=None,
                        log_level="critical",
                    )
                )
                task = asyncio.create_task(server.serve(sockets=[listener]))
                try:
                    async with asyncio.timeout(settings.database_startup_timeout_seconds):
                        while not server.started:
                            if task.done():
                                await task
                                raise AssertionError("Loopback server did not start")
                            await asyncio.sleep(0.01)
                    async with (
                        httpx.AsyncClient(base_url=address) as first,
                        httpx.AsyncClient(base_url=address) as second,
                    ):
                        yield first, second
                finally:
                    server.should_exit = True
                    await task

        try:
            # The response is lost after the actual HTTP handler has committed the CAS.
            async with waiting("response-loss", unbound=True) as (app, client, transport, aid, _):
                runtime = app.state.agent_runtime
                runs = set(runtime._records)
                path = "/admin/approvals/" + aid + "/repair-binding"

                class LoseResponse(httpx.AsyncBaseTransport):
                    async def handle_async_request(self, request):
                        response = await transport.handle_async_request(request)
                        assert response.status_code == 200
                        await response.aclose()
                        raise httpx.ReadError("Controlled response loss", request=request)

                with patch.object(runtime._graph, "ainvoke", forbidden):
                    async with httpx.AsyncClient(
                        transport=LoseResponse(), base_url="http://test"
                    ) as lost:
                        with pytest.raises(httpx.ReadError):
                            await lost.post(path, json={})
                    stored = await approval_row(aid)
                    repeated = await client.post(path, json={})
                    assert repeated.status_code == 200 and not repeated.json()["repaired"]
                    assert await approval_row(aid) == stored
                    assert set(runtime._records) == runs

                    # A real historical child checkpoint in the same namespace is not
                    # interchangeable with the original Gate audit checkpoint.
                    history_config = {
                        "configurable": {
                            "thread_id": threads[-1],
                            "checkpoint_ns": stored[5],
                        }
                    }
                    historical = None
                    async for snapshot in runtime._graph.aget_state_history(history_config):
                        if snapshot.next and snapshot.next != ("approval_gate",):
                            historical = snapshot.config["configurable"]["checkpoint_id"]
                            break
                    assert historical and historical != stored[6]
                    async with pool.connection() as conn:
                        await conn.execute(
                            "UPDATE approvals SET checkpoint_id=%s WHERE approval_id=%s",
                            (historical, aid),
                        )
                    frozen = await database_snapshot(pool)
                    assert (await client.post(path, json={})).status_code == 409
                    assert await database_snapshot(pool) == frozen
                    async with pool.connection() as conn:
                        await conn.execute(
                            "UPDATE approvals SET checkpoint_id=%s,subject_digest=%s "
                            "WHERE approval_id=%s",
                            (stored[6], "f" * 64, aid),
                        )
                    frozen = await database_snapshot(pool)
                    assert (await client.post(path, json={})).status_code == 409
                    assert await database_snapshot(pool) == frozen
                    assert set(runtime._records) == runs

            # Pending approval may be bound after expiry; repair never decides or renews it.
            async with waiting("concurrent-repair", unbound=True) as (
                app,
                client,
                transport,
                aid,
                _,
            ):
                async with pool.connection() as conn:
                    await conn.execute(
                        "UPDATE approvals SET created_at=now()-interval '60 minutes',"
                        "expires_at=now()-interval '30 minutes' WHERE approval_id=%s",
                        (aid,),
                    )
                original = await approval_row(aid)
                runs = set(app.state.agent_runtime._records)
                path = "/admin/approvals/" + aid + "/repair-binding"
                with patch.object(app.state.agent_runtime._graph, "ainvoke", forbidden):
                    async with tcp_clients(app) as (first, other):
                        responses = await asyncio.gather(
                            first.post(path, json={}), other.post(path, json={})
                        )
                    assert all(r.status_code in (200, 409) for r in responses)
                    assert (
                        sum(r.status_code == 200 and r.json()["repaired"] for r in responses) == 1
                    )
                    assert (await client.post(path, json={})).json()["repaired"] is False
                assert (await approval_row(aid))[:4] == original[:4]
                assert set(app.state.agent_runtime._records) == runs

            async with waiting("decision-cas", unbound=True) as (app, client, _, aid, _order):
                runs = set(app.state.agent_runtime._records)

                async def changed_before_cas(service, approval_id, binding):
                    async with pool.connection() as conn:
                        await conn.execute(
                            "UPDATE approvals SET decision='APPROVED',"
                            "approver_id='local-demo-approval',decided_at=clock_timestamp() "
                            "WHERE approval_id=%s",
                            (approval_id,),
                        )
                    return await original_bind(service, approval_id, binding)

                with (
                    patch.object(ApprovalService, "bind_interrupt", changed_before_cas),
                    patch.object(app.state.agent_runtime._graph, "ainvoke", forbidden),
                ):
                    response = await client.post(
                        "/admin/approvals/" + aid + "/repair-binding", json={}
                    )
                assert response.status_code == 409
                assert (await approval_row(aid))[4:] == (None, None, None)
                assert set(app.state.agent_runtime._records) == runs

            async with waiting("expiry") as (app, client, transport, aid, order):
                runtime = app.state.agent_runtime
                path = "/admin/approvals/" + aid
                detail = (await client.get(path)).json()
                body = {"decision": "APPROVED", "subject_digest": detail["subject_digest"]}
                runs = set(runtime._records)
                async with tcp_clients(app) as (first, other):
                    responses = await asyncio.gather(
                        first.post(path + "/decision", json=body),
                        other.post(path + "/decision", json=body),
                    )
                assert all(r.status_code == 200 for r in responses)
                assert responses[0].json() == responses[1].json()
                assert set(runtime._records) == runs
                async with pool.connection() as conn:
                    await conn.execute(
                        "UPDATE approvals SET created_at=now()-interval '60 minutes',"
                        "expires_at=now()-interval '30 minutes' WHERE approval_id=%s",
                        (aid,),
                    )
                stored = await approval_row(aid)
                frozen = await database_snapshot(pool)
                original_sql = psycopg.AsyncCursor.execute

                async def read_only(cursor, query, *args, **kwargs):
                    assert isinstance(query, str) and query.lstrip().upper().startswith("SELECT"), (
                        "GET attempted SQL mutation"
                    )
                    return await original_sql(cursor, query, *args, **kwargs)

                with (
                    patch.object(psycopg.AsyncCursor, "execute", read_only),
                    patch.object(AsyncPostgresSaver, "aput", forbidden),
                    patch.object(runtime._graph, "ainvoke", forbidden),
                ):
                    view = (await client.get(path)).json()
                    listing = await client.get("/admin/approvals", params={"decision": "APPROVED"})
                    assert listing.status_code == 200
                    item = next(row for row in listing.json() if row["approval_id"] == aid)
                    expected_keys = {
                        "approval_id",
                        "subject_digest",
                        "decision",
                        "expires_at",
                        "binding_status",
                        "approval_validity",
                        "can_decide",
                        "can_resume",
                    }
                    assert set(view) == set(item) == expected_keys and view == item
                    assert view["decision"] == "APPROVED" and view["approval_validity"] == "expired"
                    assert view["binding_status"] == "bound" and view["can_decide"] is False
                    assert view["can_resume"] is True
                assert await database_snapshot(pool) == frozen
                response = await client.post(path + "/resume", json={})
                assert response.status_code == 202
                await runtime._records[response.json()["run_id"]].task
                record = runtime._records[response.json()["run_id"]]
                assert record.task_status == "rejected"
                assert await approval_row(aid) == stored  # APPROVED audit and expiry retained.
                approval, application = await app.state.approval_service.get_application(aid)
                assert application["status"] == "REJECTED"
                async with pool.connection() as conn:
                    assert await (
                        await conn.execute(
                            "SELECT is_refunded FROM demo_orders WHERE order_id=%s", (order,)
                        )
                    ).fetchone() == (False,)
                child = await runtime._graph.aget_state(
                    {
                        "configurable": {
                            "thread_id": threads[-1],
                            "checkpoint_ns": approval["checkpoint_ns"],
                        }
                    }
                )
                messages = [
                    m
                    for m in child.values["messages"]
                    if isinstance(m, ToolMessage) and m.tool_call_id == application["call_id"]
                ]
                assert len(messages) == 1 and messages[0].status == "error"
        finally:
            async with pool.connection() as conn:
                # Discover owned threads even when an assertion failed during initial wait.
                owned = await (
                    await conn.execute(
                        "SELECT thread_id FROM sessions WHERE user_id=%s",
                        (owner,),
                    )
                ).fetchall()
                threads = list({*threads, *(str(row[0]) for row in owned)})
                await conn.execute(
                    "DELETE FROM approvals WHERE application_id IN "
                    "(SELECT application_id FROM refund_requests WHERE user_id=%s)",
                    (owner,),
                )
                await conn.execute("DELETE FROM refund_requests WHERE user_id=%s", (owner,))
                await conn.execute("DELETE FROM sessions WHERE user_id=%s", (owner,))
                await conn.execute("DELETE FROM demo_orders WHERE owner_id=%s", (owner,))
            checkpoint_pool = await open_checkpoint_pool(settings)
            try:
                saver = AsyncPostgresSaver(checkpoint_pool, serde=checkpoint_serializer())
                for thread in threads:
                    await saver.adelete_thread(thread)
                    async with pool.connection() as conn:
                        for table in ("checkpoints", "checkpoint_writes", "checkpoint_blobs"):
                            assert await (
                                await conn.execute(
                                    f"SELECT count(*) FROM {table} WHERE thread_id=%s", (thread,)
                                )
                            ).fetchone() == (0,)
            finally:
                await checkpoint_pool.close()
            assert await database_snapshot(pool) == before
            await pool.close()

    run_async(scenario())
