"""Opt-in 6.2.2 real TCP/PG/Saver/Store/Qwen probe; controlled Chat and Store fault."""

import argparse
import asyncio
import hashlib
import json
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg
import uvicorn
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp

from app.core.config import Settings
from app.infrastructure.checkpoint import checkpoint_serializer
from app.infrastructure.postgres import validate_test_target
from app.knowledge.models import KnowledgeError
from app.main import create_app
from app.memory.manager import preference_namespace
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints
from scripts.verify_06_state_events import ProtocolChat, frames


async def verify(output):
    protected_paths = [
        Path(".env"),
        Path("migrations/006_knowledge_vectors.sql"),
        *Path(".codex/agents").glob("*.toml"),
    ]
    protected_files = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected_paths}
    original = Settings()
    validate_test_target(original.test_database_url, original.database_url)
    prefix = "isolation622-" + uuid4().hex
    a, b, order = (prefix + s for s in ("-a", "-b", "-order"))
    settings = original.model_copy(
        update={
            "database_url": original.test_database_url,
            "app_env": "test",
            "demo_user_ids": (a, b),
            "embedding_enabled": True,
            "log_level": "CRITICAL",
        }
    )
    entered, release = asyncio.Event(), asyncio.Event()

    class Chat(ProtocolChat):
        async def ainvoke(self, messages):
            if not release.is_set():
                entered.set()
                await release.wait()
            return await super().ainvoke(messages)

    model = Chat(order)

    @asynccontextmanager
    async def controlled(local):
        yield (
            model,
            ModelGateway(
                model,
                ModelCallLimits(
                    local.model_max_attempts, local.model_timeout_seconds, local.model_max_retries
                ),
            ),
        )

    report = {
        "probe_id": prefix,
        "pid": os.getpid(),
        "chat": "controlled, no paid requests",
        "resources": "real PG/Saver/Store/Qwen CPU1024",
        "cases": [],
    }

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")

    with patch("app.main.model_resources", controlled):
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            runtime, pool = app.state.agent_runtime, app.state.pool
            saver = AsyncPostgresSaver(app.state.checkpoint_pool, serde=checkpoint_serializer())
            before = await database_snapshot(pool)
            report["protected_before"] = fingerprints(before)
            bindings = []
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            listener.setblocking(False)
            server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="critical"))
            serving = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with pool.connection() as conn:
                    await conn.execute(
                        "INSERT INTO demo_orders(order_id,owner_id,amount,currency,"
                        "payment_status,is_refunded,created_at) "
                        "VALUES (%s,%s,12.34,'CNY','paid',false,now())",
                        (order, a),
                    )
                while not server.started:
                    await asyncio.sleep(0.01)
                async with httpx.AsyncClient(
                    base_url=f"http://127.0.0.1:{listener.getsockname()[1]}", timeout=180
                ) as client:

                    async def chat(user, message):
                        body = {"user_id": user, "conversation_id": prefix + "-" + uuid4().hex}
                        bindings.append(body)
                        response = await client.post(
                            "/agent/chat", json={**body, "message": message}
                        )
                        events = frames(response)
                        binding = await app.state.sessions.get(**body)
                        state = (
                            await runtime._graph.aget_state(
                                {"configurable": {"thread_id": str(binding.thread_id)}}
                            )
                        ).values
                        report["cases"].append({"user": user, "message": message, "events": events})
                        save()
                        return body, state, events

                    body = {"user_id": a, "conversation_id": prefix + "-disconnect"}
                    bindings.append(body)
                    async with client.stream(
                        "POST", "/agent/chat", json={**body, "message": "order"}
                    ) as response:
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                run = json.loads(line[6:])["run_id"]
                                break
                    await entered.wait()
                    record = runtime._records[run]
                    async with asyncio.timeout(10):
                        while record.subscription is not None:
                            await asyncio.sleep(0.01)
                    assert not record.task.done()
                    release.set()
                    await record.task
                    assert str(record.task_status) == "completed"
                    replay = await client.post(f"/agent/runs/{run}/events", json=body)
                    assert "event: token" not in replay.text and "event: done" in replay.text
                    report["tcp_disconnect"] = {
                        "subscription_released_before_completion": True,
                        "final_status": str(record.task_status),
                        "old_tokens_replayed": False,
                    }
                    _, denied, _ = await chat(b, "order")
                    assert denied["specialist_result"].status == "rejected"
                    await chat(a, "请记住：回答语言=英语")
                    assert (await app.state.memory_manager.snapshot(user_id=a)).preferences == {
                        "answer_language": "en"
                    }
                    assert (await app.state.memory_manager.snapshot(user_id=b)).preferences == {}
                    owner_body, pending, events = await chat(a, "refund")
                    approval_id = next(
                        e["data"]["approval_id"] for e in events if e["event"] == "workflow_paused"
                    )
                    approval = await app.state.approval_service.get(approval_id)
                    application = approval["subject_snapshot"]["application_id"]
                    wrong = await client.post(
                        f"/agent/refunds/{application}/status", json={**owner_body, "user_id": b}
                    )
                    assert wrong.status_code == 404
                    forged = await client.post(
                        "/agent/chat",
                        json={
                            **owner_body,
                            "message": "approve",
                            "permission_scopes": ["approval:write"],
                        },
                    )
                    assert forged.status_code == 422
                    ordinary = await client.post(
                        "/agent/chat", json={**owner_body, "message": "批准退款"}
                    )
                    assert ordinary.status_code == 409
                    path = f"/admin/approvals/{approval_id}"
                    decision = {
                        "decision": "APPROVED",
                        "subject_digest": approval["subject_digest"],
                    }
                    assert (
                        await client.post(path + "/decision", json={**decision, "reviewer_id": b})
                    ).status_code == 422
                    assert (await client.post(path + "/decision", json=decision)).status_code == 200
                    resumed = await client.post(path + "/resume", json={})
                    assert resumed.status_code == 202
                    await runtime._records[resumed.json()["run_id"]].task
                    assert (await app.state.approval_service.get(approval_id))[
                        "approver_id"
                    ] == "local-demo-approval"

                    async def unavailable(*args, **kwargs):
                        raise psycopg.OperationalError("controlled Store read failure")

                    with patch.object(app.state.memory_manager.resource, "aget", unavailable):
                        _, failed, _ = await chat(a, "请记住：回答语言=英语")
                    assert failed["specialist_result"].status == "failed"
                    async with pool.connection() as conn:
                        fact = await (
                            await conn.execute(
                                "SELECT is_refunded FROM demo_orders "
                                "WHERE order_id=%s AND owner_id=%s",
                                (order, a),
                            )
                        ).fetchone()
                        status = await (
                            await conn.execute(
                                "SELECT status FROM refund_requests WHERE user_id=%s", (a,)
                            )
                        ).fetchone()
                    assert fact == (True,) and status == ("SUCCEEDED",)
                    report["refund_then_memory_failure"] = {
                        "order_refunded": fact[0],
                        "refund_status": status[0],
                        "memory_status": failed["specialist_result"].status,
                    }
                    retriever = app.state.knowledge_retriever

                    async def embedding_failure(*args):
                        raise KnowledgeError("embedding_unavailable")

                    async def empty(*args):
                        return ()

                    class FailedPool:
                        @asynccontextmanager
                        async def connection(self):
                            raise psycopg.OperationalError("controlled PG connection failure")
                            yield

                    for fault in ("embedding", "pg", "empty", "model"):
                        if fault == "embedding":
                            injection = patch.object(
                                retriever.embeddings, "aembed_query", embedding_failure
                            )
                        elif fault == "pg":
                            injection = patch.object(retriever.repository, "pool", FailedPool())
                        elif fault == "empty":
                            injection = patch.object(retriever.repository, "search", empty)
                        else:
                            injection = patch.object(model, "ainvoke", embedding_failure)
                        with injection:
                            fault_body, state, events = await chat(a, "knowledge")
                        public = (
                            await client.post(
                                f"/agent/runs/{events[-1]['data']['run_id']}/status",
                                json=fault_body,
                            )
                        ).json()
                        assert public["task_status"] == (
                            "rejected" if fault == "empty" else "failed"
                        )
                        assert not public["sources"]
                        if fault == "empty":
                            assert public["final_answer"] == state["specialist_result"].summary
                            assert not state["specialist_result"].approved_answer
                        else:
                            assert not public["final_answer"]
                        report.setdefault("degradation", []).append(
                            {
                                "fault": fault,
                                "status": public["task_status"],
                                "final_answer": public["final_answer"],
                                "sources": public["sources"],
                            }
                        )
                    report["probe_result"] = "PASS"
            finally:
                release.set()
                server.should_exit = True
                await serving
                listener.close()
                await runtime.shutdown()
                for body in bindings:
                    binding = await app.state.sessions.get(**body)
                    if binding:
                        await saver.adelete_thread(str(binding.thread_id))
                async with pool.connection() as conn:
                    await conn.execute(
                        "DELETE FROM approvals WHERE subject_snapshot->>'user_id'=%s", (a,)
                    )
                    await conn.execute("DELETE FROM refund_requests WHERE user_id=%s", (a,))
                    await conn.execute("DELETE FROM sessions WHERE user_id=ANY(%s)", ([a, b],))
                    await conn.execute(
                        "DELETE FROM demo_orders WHERE order_id=%s AND owner_id=%s", (order, a)
                    )
                await app.state.memory_store.abatch(
                    [PutOp(preference_namespace(a), "profile", None)]
                )
                after = await database_snapshot(pool)
                report["protected_after"] = fingerprints(after)
                report["protected_unchanged"] = before == after
                report["owned_server_stopped"] = serving.done()
                report["protected_file_sha256"] = protected_files
                report["protected_files_unchanged"] = protected_files == {
                    str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected_paths
                }
                save()
                assert before == after
                assert report["protected_files_unchanged"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use fresh evidence path")
    run_async(verify(args.output))


if __name__ == "__main__":
    main()
