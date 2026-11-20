"""Isolated real TCP integration probe. Run only in an exclusive test-DB window.

Evidence is written to a newly acquired directory. The server subprocess uses
the configured real model; only its test database, identities and V2 settings
are overridden. No fixed-order seed and no production data are used.
"""
# ruff: noqa: E402

import argparse
import asyncio
import hashlib
import json
import pickle
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import httpx
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp
from psycopg.conninfo import conninfo_to_dict

from app.core.config import Settings
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.postgres import open_pool, validate_test_target
from app.infrastructure.store import store_resources
from app.knowledge.chunking import prepare_document
from app.knowledge.models import ManifestEntry, SearchQuery
from app.knowledge.repository import KnowledgeRepository
from app.main import create_app
from app.memory.manager import preference_namespace
from app.runtime.context import DemoIdentity
from scripts.verify_05_memory_manage import (
    compare_publication_snapshots,
    database_snapshot,
    fingerprints,
)


def settings_for(data):
    original = Settings()
    assert original.model_configured and original.test_database_url
    assert "deepseek" in (original.model_base_url or "").lower(), "Expected configured DeepSeek"
    validate_test_target(original.test_database_url, original.database_url)
    target = conninfo_to_dict(original.test_database_url.get_secret_value())
    assert tuple(target.get(key) for key in ("host", "port", "dbname", "user")) == (
        "127.0.0.1",
        "56431",
        "agent_demo_test",
        "agent_test",
    ), "Unexpected isolated database target"
    return original.model_copy(
        update={
            "database_url": original.test_database_url,
            "app_env": "test",
            "demo_user_ids": (data["user_a"], data["user_b"]),
            "embedding_enabled": True,
            "knowledge_retrieval_mode": "hybrid",
            "model_max_retries": 0,
            "context_model_window_tokens": 16384,
            "context_model_output_tokens": 512,
            "context_summary_output_tokens": 256,
            "context_archive_read_tokens": 4096,
            "context_archive_root": Path(data["archive"]),
            "log_level": "CRITICAL",
        }
    )


async def identity_guard(pool):
    async with pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT current_database(),current_user,current_setting('server_version_num'),"
                "shobj_description(oid,'pg_database') FROM pg_database "
                "WHERE datname=current_database()"
            )
        ).fetchone()
        assert row == ("agent_demo_test", "agent_test", "170012", "codex-task131-0e62"), row


def save(folder, name, data):
    (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), "utf-8")


async def setup(folder, data, report):
    settings = settings_for(data)
    pool = await open_pool(settings)
    try:
        await identity_guard(pool)
        before = await database_snapshot(pool)
        (folder / "protected.pickle").write_bytes(pickle.dumps(before))
        report["before"] = fingerprints(before)
        save(folder, "report.json", report)
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            retriever = app.state.knowledge_retriever
            assert app.state.agent_service.is_ready and app.state.embedding_status == "ready"
            assert retriever and type(retriever).__name__ == "HybridRetriever"
            async with pool.connection() as conn:
                assert not await (
                    await conn.execute(
                        "SELECT 1 FROM knowledge_documents WHERE document_id=%s",
                        (data["document"],),
                    )
                ).fetchone()
                for order in data["orders"]:
                    await conn.execute(
                        "INSERT INTO demo_orders(order_id,owner_id,amount,currency,payment_status,"
                        "is_refunded,created_at) VALUES(%s,%s,12.34,'CNY','paid',false,now())",
                        (order, data["user_a"]),
                    )
            source = folder / "guide.md"
            source.write_text(
                "# 银帆模拟服务指南\n\n普通聊天不能批准模拟退款。"
                "模拟退款必须通过独立本地审批入口；服务端记录审批操作者。\n",
                "utf-8",
            )
            entry = ManifestEntry(
                document_id=data["document"],
                filename=source.name,
                source_title="银帆模拟服务指南",
                domain="platform_help",
                public_source_key="project-integration-guide",
            )
            doc = prepare_document(folder, entry, retriever.profile)
            vectors = await retriever.candidate_retriever.embeddings.aembed_documents(
                [chunk.embedding_text for chunk in doc.chunks]
            )
            assert vectors and all(len(v) == 1024 for v in vectors)
            await retriever.repository.replace(doc, vectors)
            result = await retriever.search(
                SearchQuery(query="银帆模拟退款通过什么入口审批？", top_k=3),
                identity=DemoIdentity(data["user_a"], frozenset({"knowledge:read"})),
            )
            assert result.mode == "hybrid" and result.status == "found"
            assert any(e.document_id == data["document"] for e in result.evidence)
            assert any(c.reranker_score is not None for c in result.candidates)
            report["component_hybrid"] = result.model_dump(mode="json")
            data["document_version"] = doc.document_version
            data["chunks"] = [c.chunk_id for c in doc.chunks]
            save(folder, "manifest.json", data)
            save(folder, "report.json", report)
    finally:
        await pool.close()


async def rows(data):
    pool = await open_pool(settings_for(data))
    try:
        async with pool.connection() as conn:
            result = await (
                await conn.execute(
                    "SELECT r.application_id,r.task_id,r.thread_id,r.call_id,"
                    "r.operation_id,r.status,"
                    "r.raw_args,r.canonical_args,a.approval_id,a.subject_digest,a.decision,"
                    "a.approver_id,a.checkpoint_ns,a.interrupt_id,o.order_id,o.is_refunded "
                    "FROM refund_requests r JOIN approvals a USING(application_id) "
                    "JOIN demo_orders o USING(order_id) WHERE r.user_id=%s ORDER BY o.order_id",
                    (data["user_a"],),
                )
            ).fetchall()
            return result
    finally:
        await pool.close()


async def cleanup(folder, data, report):
    settings = settings_for(data)
    pool = await open_pool(settings)
    try:
        await identity_guard(pool)
        async with pool.connection() as conn:
            sessions = await (
                await conn.execute(
                    "SELECT thread_id FROM sessions WHERE user_id=ANY(%s)",
                    ([data["user_a"], data["user_b"]],),
                )
            ).fetchall()
        cp = await open_checkpoint_pool(settings)
        try:
            saver = AsyncPostgresSaver(cp, serde=checkpoint_serializer())
            for (thread,) in sessions:
                await saver.adelete_thread(str(thread))
                assert await saver.aget_tuple({"configurable": {"thread_id": str(thread)}}) is None
        finally:
            await cp.close()
        async with store_resources(settings) as store:
            for user in (data["user_a"], data["user_b"]):
                await store.abatch([PutOp(preference_namespace(user), "profile", None)])
                assert await store.aget(preference_namespace(user), "profile") is None
        async with pool.connection() as conn, conn.transaction():
            users = [data["user_a"], data["user_b"]]
            await conn.execute(
                "DELETE FROM preference_command_receipt WHERE user_id=ANY(%s)", (users,)
            )
            await conn.execute(
                "DELETE FROM context_maintenance_attempt WHERE maintenance_id IN "
                "(SELECT maintenance_id FROM context_maintenance WHERE user_id=ANY(%s))",
                (users,),
            )
            for table in (
                "context_maintenance",
                "context_revision",
                "context_summary",
                "context_archive",
            ):
                await conn.execute(f"DELETE FROM {table} WHERE user_id=ANY(%s)", (users,))
            await conn.execute(
                "DELETE FROM approvals WHERE subject_snapshot->>'user_id'=%s", (data["user_a"],)
            )
            await conn.execute("DELETE FROM refund_requests WHERE user_id=%s", (data["user_a"],))
            await conn.execute(
                "DELETE FROM demo_orders WHERE owner_id=%s AND order_id=ANY(%s)",
                (data["user_a"], data["orders"]),
            )
            await conn.execute("DELETE FROM sessions WHERE user_id=ANY(%s)", (users,))
            present = await (
                await conn.execute(
                    "SELECT EXISTS(SELECT 1 FROM knowledge_documents WHERE document_id=%s)",
                    (data["document"],),
                )
            ).fetchone()
        if present[0]:
            await KnowledgeRepository(pool).remove(data["document"])
        after = await database_snapshot(pool)
        before = pickle.loads((folder / "protected.pickle").read_bytes())
        report["cleanup"] = compare_publication_snapshots(
            before, after, expected_delta=2 if present[0] else 0
        )
        report["after"] = fingerprints(after)
        save(folder, "report.json", report)
        assert report["cleanup"]["protected_unchanged"], "protected snapshot mismatch"
    finally:
        await pool.close()


async def audit_context(data, *, prior=None):
    pool = await open_pool(settings_for(data))
    cp = await open_checkpoint_pool(settings_for(data))
    try:
        async with pool.connection() as conn:
            sessions = await (
                await conn.execute(
                    "SELECT user_id,conversation_id,thread_id FROM sessions WHERE user_id=ANY(%s)",
                    ([data["user_a"], data["user_b"]],),
                )
            ).fetchall()
            maintenance = await (
                await conn.execute(
                    "SELECT user_id,conversation_id,status,reserved_attempts,summary_id,revision "
                    "FROM context_maintenance WHERE user_id=ANY(%s)",
                    ([data["user_a"], data["user_b"]],),
                )
            ).fetchall()
        saver = AsyncPostgresSaver(cp, serde=checkpoint_serializer())
        snapshots = []
        for user, conversation, thread in sessions:
            item = await saver.aget_tuple({"configurable": {"thread_id": str(thread)}})
            values = item.checkpoint.get("channel_values", {}) if item else {}
            checkpoint_id = item.config["configurable"]["checkpoint_id"] if item else None
            checkpoint_hash = (
                hashlib.sha256(pickle.dumps(item.checkpoint)).hexdigest() if item else None
            )
            snapshots.append(
                {
                    "user": user,
                    "conversation": conversation,
                    "thread": str(thread),
                    "checkpoint_id": checkpoint_id,
                    "checkpoint_hash": checkpoint_hash,
                    "task_id": values.get("task_id"),
                    "context_ref": values.get("context_ref"),
                    "context_history": values.get("context_history"),
                    "model_call_usage": values.get("model_call_usage"),
                    "public_message_metadata": values.get("public_message_metadata"),
                }
            )
        prior_checks = []
        for old in prior or []:
            if not old["checkpoint_id"]:
                continue
            item = await saver.aget_tuple(
                {
                    "configurable": {
                        "thread_id": old["thread"],
                        "checkpoint_id": old["checkpoint_id"],
                    }
                }
            )
            prior_checks.append(
                {
                    "thread": old["thread"],
                    "checkpoint_id": old["checkpoint_id"],
                    "unchanged": bool(
                        item
                        and hashlib.sha256(pickle.dumps(item.checkpoint)).hexdigest()
                        == old["checkpoint_hash"]
                    ),
                }
            )
        return {"snapshots": snapshots, "maintenance": maintenance, "prior_checks": prior_checks}
    finally:
        await cp.close()
        await pool.close()


def serve(manifest, port):
    import uvicorn

    data = json.loads(manifest.read_text("utf-8"))
    config = uvicorn.Config(
        create_app(settings_for(data)),
        host="127.0.0.1",
        port=port,
        log_level="critical",
        loop="none",
    )
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
        if sys.platform == "win32"
        else asyncio.DefaultEventLoopPolicy()
    )
    asyncio.run(uvicorn.Server(config).serve())


async def main(folder):
    folder.mkdir(parents=True, exist_ok=False)
    prefix = "project-http-" + uuid4().hex
    data = {
        "user_a": prefix + "-a",
        "user_b": prefix + "-b",
        "document": prefix + "-doc",
        "orders": [prefix + "-ok", prefix + "-reject"],
        "archive": str(folder / "archive"),
    }
    save(folder, "manifest.json", data)
    report = {
        "result": "IN_PROGRESS",
        "probe_id": prefix,
        "cases": [],
        "configuration": {
            "database": "dedicated isolated test database",
            "embedding": "Qwen 1024",
            "retrieval": "hybrid with BGE",
            "context_window": 16384,
            "context_output": 512,
            "summary_output": 256,
            "model_retries": 0,
            "archive": data["archive"],
            "model": Settings().model_name,
            "host": urlsplit(Settings().model_base_url or "").hostname,
        },
        "limitations": [
            "Component hybrid search and HTTP Graph are separately evidenced",
            "No Postman/Apifox UI exercised",
            "History semantics require response review",
            "Ordinary run status exposes attempt counts, not complete provider token totals; "
            "unobserved token usage remains unknown",
        ],
    }
    save(folder, "report.json", report)
    processes = []
    client = None
    log = None
    try:
        await setup(folder, data, report)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        client = httpx.Client(base_url=base, timeout=Settings().run_timeout_seconds)
        log = (folder / "server.log").open("ab")

        def start():
            p = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--server",
                    "--manifest",
                    str(folder / "manifest.json"),
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            processes.append(p)
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                assert p.poll() is None, "server exited before readiness"
                try:
                    response = client.get("/health", timeout=3)
                    if response.status_code == 200 and response.json().get("agent_ready"):
                        return p
                except httpx.TransportError:
                    pass
                time.sleep(0.5)
            raise AssertionError("server readiness timeout")

        def stop(p):
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=30)
            assert p.poll() is not None

        serial = 0

        def request(label, path, body=None, expected=200, method="POST"):
            nonlocal serial
            serial += 1
            response = client.request(method, path, json=body if method == "POST" else None)
            (folder / f"http-{serial:02d}-{label}.bin").write_bytes(response.content)
            report["cases"].append(
                {
                    "label": label,
                    "http_status": response.status_code,
                    "raw": f"http-{serial:02d}-{label}.bin",
                }
            )
            save(folder, "report.json", report)
            assert response.status_code == expected, (label, response.status_code, response.text)
            return response

        def context(name, user=None):
            return {"user_id": user or data["user_a"], "conversation_id": prefix + "-" + name}

        def chat(label, conversation, message, *, user=None, expected="completed"):
            identity = context(conversation, user)
            response = request(
                label,
                "/agent/chat",
                {
                    **identity,
                    "message": message,
                    "input_mode": "new_task",
                    "request_id": str(uuid4()),
                },
            )
            frames = []
            for block in response.text.replace("\r\n", "\n").split("\n\n"):
                event = next((x[7:] for x in block.splitlines() if x.startswith("event: ")), None)
                payload = next((x[6:] for x in block.splitlines() if x.startswith("data: ")), None)
                if event and payload:
                    frames.append((event, json.loads(payload)))
            assert sum(event == "done" for event, _ in frames) == 1
            current = request(label + "-current", "/agent/tasks/current", identity).json()[
                "current_task"
            ]
            assert current["task_status"] == expected, (label, current)
            run_id = next((body.get("run_id") for _, body in frames if body.get("run_id")), None)
            assert run_id
            run = request(label + "-run", f"/agent/runs/{run_id}/status", identity).json()
            report["cases"][-1]["run"] = run
            save(folder, "report.json", report)
            return current, frames, run

        def mutate(label, command, revision, operation=None):
            operation = operation or str(uuid4())
            payload = {
                "user_id": data["user_a"],
                "operation_id": operation,
                "expected_revision": revision,
                "command": command,
            }
            result = request(label, "/agent/preferences/mutations", payload).json()
            assert result["status"] == "applied", result
            return result, payload

        def resume(current, decision, conversation):
            refund = current["refund"]
            prefix_url = "/admin/approvals/" + refund["approval_id"]
            view = request("approval-view", prefix_url, method="GET").json()
            body = {"decision": decision, "subject_digest": view["subject_digest"]}
            request("approval-decision", prefix_url + "/decision", body)
            accepted = request("approval-resume", prefix_url + "/resume", {}, expected=202).json()
            assert accepted["accepted"] and accepted["task_id"] == current["task_id"]
            deadline = time.monotonic() + Settings().run_timeout_seconds
            while time.monotonic() < deadline:
                status = request(
                    "resume-status",
                    "/agent/runs/" + accepted["run_id"] + "/status",
                    context(conversation),
                ).json()
                if status["run_status"] != "running":
                    break
                awaitable_sleep = 0.3
                time.sleep(awaitable_sleep)
            else:
                raise AssertionError("resume timeout")
            assert status["task_status"] == ("completed" if decision == "APPROVED" else "rejected")
            request("approval-decision-repeat", prefix_url + "/decision", body)
            repeated = request("approval-resume-repeat", prefix_url + "/resume", {}).json()
            assert repeated["accepted"] is False and repeated["run_id"] is None
            return status

        first = start()
        report["first_pid"] = first.pid
        health = request("health", "/health", method="GET").json()
        report["health"] = health
        request("preference-initial", "/agent/preferences/read", {"user_id": data["user_a"]})
        write, payload = mutate(
            "preference-upsert",
            {"operation": "upsert", "field": "answer_style", "value": "concise"},
            0,
        )
        assert request("preference-repeat", "/agent/preferences/mutations", payload).json() == write
        status = request(
            "preference-operation",
            "/agent/preferences/operations/" + payload["operation_id"] + "/status",
            {"user_id": data["user_a"]},
        ).json()
        assert status["status"] == "applied"
        other = request(
            "preference-other", "/agent/preferences/read", {"user_id": data["user_b"]}
        ).json()
        assert other["revision"] is None
        chat("order", "refund-ok", "查询订单 " + data["orders"][0])
        chat(
            "order-other",
            "foreign",
            "查询订单 " + data["orders"][0],
            user=data["user_b"],
            expected="rejected",
        )
        current, frames, _ = chat(
            "refund-wait",
            "refund-ok",
            "请为订单 " + data["orders"][0] + " 申请模拟退款",
            expected="waiting_approval",
        )
        assert any(event == "workflow_paused" for event, _ in frames)
        request(
            "chat-not-approval",
            "/agent/chat",
            {**context("refund-ok"), "message": "我同意批准退款"},
            expected=409,
        )
        before = await rows(data)
        assert len(before) == 1 and before[0][5] == "PENDING" and before[0][15] is False
        stop(first)
        second = start()
        assert second.pid != first.pid and first.poll() is not None
        report["restart"] = {"old_pid": first.pid, "new_pid": second.pid, "old_exited": True}
        recovered = request(
            "refund-after-restart", "/agent/tasks/current", context("refund-ok")
        ).json()["current_task"]
        assert (
            recovered["task_id"] == current["task_id"] and recovered["refund"] == current["refund"]
        )
        pref = request(
            "preference-after-restart", "/agent/preferences/read", {"user_id": data["user_a"]}
        ).json()
        assert pref["preferences"] == {"answer_style": "concise"}
        resume(recovered, "APPROVED", "refund-ok")
        rejected, _, _ = chat(
            "refund-reject",
            "refund-reject",
            "请为订单 " + data["orders"][1] + " 申请模拟退款",
            expected="waiting_approval",
        )
        resume(rejected, "REJECTED", "refund-reject")
        after = await rows(data)
        assert len(after) == 2 and {r[5] for r in after} == {"SUCCEEDED", "REJECTED"}
        old = next(row for row in after if row[14] == data["orders"][0])
        for index in (0, 1, 2, 3, 4, 6, 7, 8, 9, 12, 13, 14):
            assert old[index] == before[0][index], "refund binding changed"
        assert all(r[11] == "local-demo-approval" and r[15] == (r[5] == "SUCCEEDED") for r in after)
        report["refund_before"] = before
        report["refund_after"] = after
        _, _, rag = chat(
            "knowledge",
            "knowledge",
            "根据银帆模拟服务指南，普通聊天能批准模拟退款吗？应通过什么入口？",
        )
        assert rag["sources"] and any(
            s["document_id"] == data["document"]
            and s["document_version"] == data["document_version"]
            and s["chunk_id"] in data["chunks"]
            for s in rag["sources"]
        )
        chat("preference-new-session", "preference-new", "请简要说明你能处理什么问题。")
        chat("history-first", "history", "我有一把紫色雨伞，请回复收到。")
        chat("history-second", "history", "请用一句话介绍这个演示。")
        chat("history-third", "history", "请说一句简短的问候。")
        chat("history-fourth", "history", "请说一句简短的告别语。")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            context_before = await audit_context(data)
            if any(
                row[2] in ("SUCCEEDED", "FAILED", "EXHAUSTED")
                and row[1] == context("history")["conversation_id"]
                for row in context_before["maintenance"]
            ):
                break
            await asyncio.sleep(0.5)
        report["context_before_followup"] = context_before
        save(folder, "report.json", report)
        chat("history-followup", "history", "我最开始提到的物品是什么？只回答物品。")
        changed, _ = mutate(
            "preference-update",
            {"operation": "upsert", "field": "answer_style", "value": "detailed"},
            pref["revision"],
        )
        deleted, _ = mutate(
            "preference-delete",
            {"operation": "delete", "field": "answer_style"},
            changed["revision"],
        )
        final = request(
            "preference-final", "/agent/preferences/read", {"user_id": data["user_a"]}
        ).json()
        assert final["preferences"] == {} and final["revision"] == deleted["revision"]
        report["context"] = await audit_context(data, prior=context_before["snapshots"])
        assert all(check["unchanged"] for check in report["context"]["prior_checks"])
        report["result"] = "SCENARIOS_COMPLETED_PENDING_REVIEW"
    except BaseException as error:
        report["result"] = "FAIL"
        report["failure"] = {"category": type(error).__name__, "detail": str(error)}
        raise
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=30)
        if client:
            client.close()
        if log:
            log.close()
        save(folder, "report.json", report)
        if (folder / "protected.pickle").exists():
            await cleanup(folder, data, report)
        archive = Path(data["archive"])
        if archive.exists():
            assert archive.parent == folder and archive.name == "archive"
            shutil.rmtree(archive)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.server:
        assert args.manifest and args.port
        serve(args.manifest, args.port)
    else:
        assert args.output
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
            if sys.platform == "win32"
            else asyncio.DefaultEventLoopPolicy()
        )
        asyncio.run(main(args.output.resolve()))
