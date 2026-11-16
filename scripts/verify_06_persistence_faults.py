"""Opt-in Task6.2.1 TCP/process probe; controlled Chat, real PG/Saver/Store/Qwen.

Faults and the read-only observation route exist only in this verification factory.
Only this driver's UUID fixtures and child PIDs are managed. No production flags.
"""

import argparse
import asyncio
import hashlib
import inspect
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from app.core.config import Settings
from app.domain.refunds import MockRefundService
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.postgres import open_pool, validate_test_target
from app.main import create_app
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from app.workflows.approvals import ApprovalService
from scripts import run_async
from scripts.verify_04_restart import Provider
from scripts.verify_05_memory_manage import database_snapshot, fingerprints


def test_settings(data):
    original = Settings()
    validate_test_target(original.test_database_url, original.database_url)
    return original.model_copy(
        update={
            "database_url": original.test_database_url,
            "app_env": "test",
            "log_level": "CRITICAL",
            "demo_user_ids": (data["owner"],),
            "embedding_enabled": True,
        }
    )


def server_app():
    """Production lifespan/topology, with 04's exact test-side fault boundaries."""
    logging.disable(logging.CRITICAL)
    data = json.loads(Path(os.environ["PERSISTENCE621_MANIFEST"]).read_text("utf-8"))
    mode, phase = data["mode"], os.environ["PERSISTENCE621_PHASE"]
    settings = test_settings(data)
    writes, nodes, invocations = [], [], []
    fired = False
    add, put, put_writes = (
        StateGraph.add_node,
        AsyncPostgresSaver.aput,
        AsyncPostgresSaver.aput_writes,
    )
    execute, bind, invoke = (
        MockRefundService.execute_original,
        ApprovalService.bind_interrupt,
        CompiledStateGraph.ainvoke,
    )

    def observed_add(self, node, action=None, **kwargs):
        name = node if isinstance(node, str) else node.__name__
        fn = action if isinstance(node, str) else node
        if (
            name
            in {
                "approval_gate",
                "recheck_execution",
                "prepare_refund_attempt",
                "execute_refund",
                "record_tool_outcome",
                "compose_refund_reply",
                "map_result",
            }
            and "runtime" in inspect.signature(fn).parameters
        ):

            async def observe(state, runtime: Runtime[RunExecutionContext]):
                nonlocal fired
                ctx = runtime.context
                nodes.append(
                    {
                        "node": name,
                        "run": ctx.context.run_id,
                        "mode": ctx.execution_mode,
                        "recovery": ctx.refund_recovery.disposition
                        if ctx.refund_recovery
                        else None,
                    }
                )
                if (
                    phase == "fault"
                    and mode in ("unexecuted", "business_unknown")
                    and name == "execute_refund"
                    and not fired
                ):
                    fired = True
                    raise RuntimeError("controlled before-handler boundary")
                # Hold only the controlled Chat-independent observation window so
                # concurrent HTTP resume admissions actually overlap.
                if phase == "resume" and mode == "normal" and name == "approval_gate":
                    await asyncio.sleep(0.3)
                value = fn(state, runtime)
                return await value if inspect.isawaitable(value) else value

            return add(self, name, observe, **kwargs)
        return add(self, node, action, **kwargs)

    async def observed_put(self, config, checkpoint, metadata, new_versions):
        nonlocal fired
        if phase == "fault" and config["configurable"].get("checkpoint_ns"):
            values = checkpoint.get("channel_values", {})
            if (
                mode in ("checkpoint", "pending", "success_expired")
                and values.get("execution_result")
            ) or (mode == "barrier" and values.get("prepared_attempt")):
                fired = True
                raise RuntimeError("controlled sync checkpoint boundary")
        return await put(self, config, checkpoint, metadata, new_versions)

    async def observed_writes(self, config, writes, task_id, task_path=""):
        nonlocal fired
        if phase == "fault" and mode in ("checkpoint", "barrier", "success_expired"):
            field = "prepared_attempt" if mode == "barrier" else "execution_result"
            if any(key == field and value for key, value in writes):
                fired = True
                raise RuntimeError("controlled pending writes boundary")
        return await put_writes(self, config, writes, task_id, task_path)

    get_operation = MockRefundService.get_operation

    async def observed_operation(self, *, user_id, operation_id):
        if mode == "business_unknown" and phase == "resume":
            raise psycopg.OperationalError("controlled operation read unavailable")
        return await get_operation(self, user_id=user_id, operation_id=operation_id)

    async def observed_execute(self, *, context, order_id):
        writes.append({"run": context.run_id, "operation": context.operation_id})
        return await execute(self, context=context, order_id=order_id)

    async def observed_bind(self, approval_id, binding):
        nonlocal fired
        if mode == "repair" and phase == "wait" and not fired:
            fired = True
            raise psycopg.OperationalError("controlled binding boundary")
        return await bind(self, approval_id, binding)

    async def observed_invoke(self, input, config=None, **kwargs):
        ctx = kwargs.get("context")
        invocations.append(
            {
                "graph": "refund_child" if "execute_refund" in self.nodes else "root",
                "input": "None" if input is None else type(input).__name__,
                "run": ctx.context.run_id if ctx else None,
            }
        )
        return await invoke(self, input, config, **kwargs)

    @asynccontextmanager
    async def controlled(config):
        provider = Provider(data["order"])
        yield (
            provider,
            ModelGateway(
                provider,
                ModelCallLimits(config.model_max_attempts, config.model_timeout_seconds, 0),
            ),
        )

    app = create_app(settings)
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        with ExitStack() as stack:
            for target, name, replacement in (
                (StateGraph, "add_node", observed_add),
                (AsyncPostgresSaver, "aput", observed_put),
                (AsyncPostgresSaver, "aput_writes", observed_writes),
                (MockRefundService, "execute_original", observed_execute),
                (MockRefundService, "get_operation", observed_operation),
                (ApprovalService, "bind_interrupt", observed_bind),
                (CompiledStateGraph, "ainvoke", observed_invoke),
            ):
                stack.enter_context(patch.object(target, name, replacement))
            stack.enter_context(patch("app.main.model_resources", controlled))
            async with original_lifespan(application):
                yield

    app.router.lifespan_context = lifespan

    @app.get("/__probe621")
    async def observation():
        runtime = app.state.agent_runtime
        result = {
            "pid": os.getpid(),
            "fired": fired,
            "writes": writes,
            "nodes": nodes,
            "invocations": invocations,
            "runs": [],
            "resources": {
                "store": app.state.store_status,
                "embedding": app.state.embedding_status,
                "checkpoint": app.state.checkpoint_status,
            },
        }
        for record in runtime._records.values():
            result["runs"].append(
                {
                    "run_id": record.context.run_id,
                    "task_id": record.execution.context.task_id,
                    "done": record.task.done(),
                    "task_status": record.task_status,
                    "model": asdict(record.execution.scope.model_usage()),
                    "usage": asdict(record.execution.scope.run_usage()),
                }
            )
        async with app.state.pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT approval_id FROM approvals WHERE application_id IN "
                    "(SELECT application_id FROM refund_requests WHERE user_id=%s)",
                    (data["owner"],),
                )
            ).fetchone()
        if not row:
            return result
        approval, application = await app.state.approval_service.get_application(str(row[0]))
        classified = await runtime._inspect_refund_checkpoint(approval, application)
        fixed_keys = (
            "user_id",
            "conversation_id",
            "thread_id",
            "task_id",
            "workflow_id",
            "application_id",
            "operation_id",
            "call_id",
            "tool_name",
            "raw_args",
            "canonical_args",
            "args_digest",
        )
        result["fixed"] = {
            key: application[key] if isinstance(application[key], dict) else str(application[key])
            for key in fixed_keys
        }
        result["approval"] = {
            key: str(approval[key]) if approval[key] is not None else None
            for key in (
                "approval_id",
                "subject_digest",
                "checkpoint_ns",
                "checkpoint_id",
                "interrupt_id",
                "decision",
                "approver_id",
                "created_at",
                "expires_at",
                "decided_at",
            )
        }
        result["classification"] = classified.kind
        result["business_status"] = application["status"]
        result["next"] = list(classified.child.next) if classified.child else []
        child = classified.child
        if child is None and approval["checkpoint_ns"]:
            child = await runtime._graph.aget_state(
                {
                    "configurable": {
                        "thread_id": str(application["thread_id"]),
                        "checkpoint_ns": approval["checkpoint_ns"],
                    }
                }
            )
        if child and child.values:
            result["saved_usage"] = child.values.get("run_usage")
            result["saved_model"] = child.values.get("model_call_usage")
            result["paired_messages"] = [
                {"id": m.id, "call": m.tool_call_id}
                for m in child.values.get("messages", [])
                if isinstance(m, ToolMessage) and m.tool_call_id == application["call_id"]
            ]
            marker = child.values.get("prepared_attempt")
            result["attempt"] = {"id": marker.attempt_id, "run": marker.run_id} if marker else None
        async with app.state.pool.connection() as conn:
            result["order_refunded"] = (
                await (
                    await conn.execute(
                        "SELECT is_refunded FROM demo_orders WHERE order_id=%s AND owner_id=%s",
                        (data["order"], data["owner"]),
                    )
                ).fetchone()
            )[0]
            result["successful_applications"] = (
                await (
                    await conn.execute(
                        "SELECT count(*) FROM refund_requests "
                        "WHERE user_id=%s AND status='SUCCEEDED'",
                        (data["owner"],),
                    )
                ).fetchone()
            )[0]
        return result

    return app


async def fixtures(data, action):
    settings = test_settings(data)
    pool = await open_pool(settings)
    try:
        if action == "snapshot":
            return await database_snapshot(pool)
        async with pool.connection() as conn:
            if action == "setup":
                await conn.execute(
                    "INSERT INTO demo_orders VALUES (%s,%s,42.50,'CNY','paid',false,now())",
                    (data["order"], data["owner"]),
                )
            elif action == "expire":
                await conn.execute(
                    "UPDATE approvals SET created_at=now()-interval '31 minutes', "
                    "expires_at=now()-interval '1 minute' WHERE approval_id=%s",
                    (data["approval_id"],),
                )
            elif action in ("cleanup", "clear_checkpoint"):
                threads = await (
                    await conn.execute(
                        "SELECT thread_id FROM sessions WHERE user_id=%s", (data["owner"],)
                    )
                ).fetchall()
            if action == "cleanup":
                await conn.execute(
                    "DELETE FROM approvals WHERE application_id IN "
                    "(SELECT application_id FROM refund_requests WHERE user_id=%s)",
                    (data["owner"],),
                )
                await conn.execute("DELETE FROM refund_requests WHERE user_id=%s", (data["owner"],))
                await conn.execute("DELETE FROM sessions WHERE user_id=%s", (data["owner"],))
                await conn.execute(
                    "DELETE FROM demo_orders WHERE order_id=%s AND owner_id=%s",
                    (data["order"], data["owner"]),
                )
        if action in ("cleanup", "clear_checkpoint"):
            cp = await open_checkpoint_pool(settings)
            try:
                saver = AsyncPostgresSaver(cp, serde=checkpoint_serializer())
                for (thread,) in threads:
                    await saver.adelete_thread(str(thread))
            finally:
                await cp.close()
    finally:
        await pool.close()


def verify(output, modes):
    logging.disable(logging.CRITICAL)
    report = {
        "task": "6.2.1",
        "chat": "controlled; no paid requests",
        "cases": [],
        "result": "IN_PROGRESS",
    }

    protected_paths = (
        ".env",
        "migrations/006_knowledge_vectors.sql",
        "tests/test_order_postgres.py",
        ".codex/agents/implementer.toml",
        ".codex/agents/qa.toml",
    )

    def file_hashes():
        return {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in protected_paths
        }

    report["protected_files_before"] = file_hashes()

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")

    save()

    def run_case(mode):
        uid = "persistence621-" + uuid4().hex
        data = {"mode": mode, "owner": uid, "order": uid, "conversation": uid}
        case = {"mode": mode, "identity": data.copy(), "processes": [], "observations": []}
        report["cases"].append(case)
        before = run_async(fixtures(data, "snapshot"))
        case["protected_before"] = fingerprints(before)
        processes = []
        with tempfile.TemporaryDirectory(prefix=uid) as folder:
            manifest = Path(folder) / "manifest.json"
            manifest.write_text(json.dumps(data), "utf-8")
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            address = "http://127.0.0.1:" + str(port)
            client = httpx.Client(base_url=address, timeout=Settings().run_timeout_seconds)

            def start(phase):
                command = [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "scripts.verify_06_persistence_faults:server_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--loop",
                    "app.infrastructure.postgres:selector_event_loop",
                    "--log-level",
                    "critical",
                ]
                started = time.monotonic()
                process = subprocess.Popen(
                    command,
                    env={
                        **os.environ,
                        "PERSISTENCE621_MANIFEST": str(manifest),
                        "PERSISTENCE621_PHASE": phase,
                    },
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                processes.append(process)
                entry = {
                    "pid": process.pid,
                    "phase": phase,
                    "command": command,
                    "started_at": datetime.now(UTC).isoformat(),
                }
                case["processes"].append(entry)
                save()
                deadline = started + Settings().database_startup_timeout_seconds * 3
                while time.monotonic() < deadline:
                    assert process.poll() is None, "server_exited"
                    try:
                        response = client.get("/health", timeout=2)
                        if response.status_code == 200 and response.json()["agent_ready"]:
                            health = response.json()
                            assert (
                                health["store_status"]
                                == health["embedding_status"]
                                == health["checkpoint_status"]
                                == "ready"
                            )
                            entry.update(
                                ready_seconds=round(time.monotonic() - started, 3), health=health
                            )
                            entry["server_pid"] = client.get("/__probe621").json()["pid"]
                            return process
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                raise AssertionError("server_not_ready")

            def stop(process):
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                process.wait(timeout=Settings().runtime_shutdown_grace_seconds + 10)
                next(e for e in case["processes"] if e["pid"] == process.pid).update(
                    exit_code=process.returncode, exit_confirmed=True
                )
                save()

            def probe(label):
                deadline = time.monotonic() + Settings().run_timeout_seconds
                while True:
                    response = client.get("/__probe621")
                    assert response.status_code == 200
                    value = response.json()
                    if all(r["done"] for r in value["runs"]):
                        break
                    assert time.monotonic() < deadline, "run_did_not_finish"
                    time.sleep(0.1)
                case["observations"].append({"label": label, **value})
                save()
                return value

            def decide(prefix, decision="APPROVED"):
                detail = client.get(prefix).json()
                body = {"decision": decision, "subject_digest": detail["subject_digest"]}
                response = client.post(prefix + "/decision", json=body)
                assert response.status_code == 200, response.text
                return body

            try:
                run_async(fixtures(data, "setup"))
                old = start("wait")
                response = client.post(
                    "/agent/chat",
                    json={"user_id": uid, "conversation_id": uid, "message": "申请模拟退款"},
                )
                assert response.status_code == 200
                assert (
                    "pause_binding_unavailable" if mode == "repair" else "event: workflow_paused"
                ) in response.text
                waiting = probe("waiting")
                assert waiting["classification"] == "pending" and not waiting["writes"]
                data["approval_id"] = waiting["approval"]["approval_id"]
                prefix = "/admin/approvals/" + data["approval_id"]
                if mode == "missing":
                    # Remove only the UUID session's own Saver snapshots. Keep its
                    # original application/approval untouched to test safe refusal.
                    run_async(fixtures(data, "clear_checkpoint"))
                stop(old)
                process = start(
                    "fault"
                    if mode
                    in (
                        "checkpoint",
                        "success_expired",
                        "unexecuted",
                        "business_unknown",
                        "pending",
                        "barrier",
                    )
                    else "resume"
                )
                fresh = probe("new_process_before_admission")
                assert not fresh["runs"] and not fresh["invocations"]
                assert fresh["fixed"] == waiting["fixed"]
                if mode == "missing":
                    assert fresh["classification"] == "unknown"
                    response = client.post(prefix + "/resume", json={})
                    case["missing_resume"] = {
                        "status": response.status_code,
                        "body": response.json(),
                    }
                    assert response.status_code == 409
                    assert response.json()["error"]["code"] == "execution_uncertain"
                    final = probe("missing_snapshot_refused")
                    assert not final["runs"] and not final["writes"] and not final["invocations"]
                    assert final["approval"] == fresh["approval"]
                    assert final["business_status"] == "PENDING" and not final["order_refunded"]
                    case["result"] = "PASS"
                    return
                if mode == "repair":
                    assert (
                        client.post(
                            prefix + "/decision",
                            json={
                                "decision": "APPROVED",
                                "subject_digest": fresh["approval"]["subject_digest"],
                            },
                        ).status_code
                        == 409
                    )
                    assert (
                        client.post(prefix + "/repair-binding", json={}).json()["repaired"] is True
                    )
                    assert (
                        client.post(prefix + "/repair-binding", json={}).json()["repaired"] is False
                    )
                    fixed = probe("repaired")
                    assert (
                        fixed["fixed"] == waiting["fixed"]
                        and not fixed["runs"]
                        and not fixed["writes"]
                    )
                    waiting["approval"] = fixed["approval"]
                if mode != "expired_pending":
                    body = decide(prefix, "REJECTED" if mode == "reject" else "APPROVED")
                    first_decision = probe("decided")["approval"]
                    assert client.post(prefix + "/decision", json=body).status_code == 200
                    opposite = {
                        **body,
                        "decision": "APPROVED" if body["decision"] == "REJECTED" else "REJECTED",
                    }
                    assert client.post(prefix + "/decision", json=opposite).status_code == 409
                    assert probe("duplicate_decision")["approval"] == first_decision
                if mode in ("expired_pending", "expired_approved"):
                    run_async(fixtures(data, "expire"))
                    expired = probe("expired_get_read_only")
                    assert expired["approval"]["decision"] == (
                        "PENDING" if mode == "expired_pending" else "APPROVED"
                    )
                if mode == "normal":
                    with ThreadPoolExecutor(max_workers=2) as workers:
                        responses = list(
                            workers.map(
                                lambda _: httpx.post(
                                    address + prefix + "/resume", json={}, timeout=30
                                ),
                                range(2),
                            )
                        )
                    case["concurrent_resume"] = [
                        {"status": r.status_code, "body": r.json()} for r in responses
                    ]
                    save()
                    assert sum(r.json().get("accepted", False) for r in responses) == 1
                    assert all(r.status_code in (200, 202, 409) for r in responses)
                    assert all(
                        r.json()["error"]["code"] == "thread_busy"
                        for r in responses
                        if r.status_code == 409
                    )
                    assert len({r.json()["run_id"] for r in responses if "run_id" in r.json()}) == 1
                else:
                    response = client.post(prefix + "/resume", json={})
                    assert response.status_code == 202, response.text
                resumed = probe("first_resume")
                if mode in (
                    "checkpoint",
                    "success_expired",
                    "unexecuted",
                    "business_unknown",
                    "pending",
                    "barrier",
                ):
                    assert resumed["fired"]
                    assert len(resumed["writes"]) == (
                        0 if mode in ("unexecuted", "business_unknown", "barrier") else 1
                    )
                    assert resumed["business_status"] == (
                        "PENDING"
                        if mode in ("unexecuted", "business_unknown", "barrier")
                        else "SUCCEEDED"
                    )
                    if mode == "success_expired":
                        run_async(fixtures(data, "expire"))
                    stop(process)
                    process = start("resume")
                    pre = probe("fault_restarted")
                    assert pre["fixed"] == waiting["fixed"]
                    response = client.post(prefix + "/resume", json={})
                    if mode in ("pending", "barrier", "business_unknown"):
                        assert response.status_code == 409, response.text
                        final = probe("unknown_refused")
                        assert (
                            not final["runs"] and not final["writes"] and not final["invocations"]
                        )
                        case["result"] = "PASS"
                        return
                    assert response.status_code == 202, response.text
                    final = probe("reconciled")
                    assert len(final["writes"]) == (1 if mode == "unexecuted" else 0)
                    assert any(
                        n["recovery"] == ("not_executed" if mode == "unexecuted" else "succeeded")
                        for n in final["nodes"]
                    )
                    if mode == "unexecuted":
                        assert final["attempt"]["id"] != resumed["attempt"]["id"]
                        assert final["attempt"]["run"] == final["runs"][0]["run_id"]
                else:
                    final = resumed
                rejected = mode in ("reject", "expired_pending", "expired_approved")
                assert final["fixed"] == waiting["fixed"]
                assert final["business_status"] == ("REJECTED" if rejected else "SUCCEEDED")
                assert final["order_refunded"] is (not rejected)
                assert final["successful_applications"] == (0 if rejected else 1)
                if rejected:
                    assert not final["writes"]
                assert final["classification"] == "ended"
                assert final["approval"]["checkpoint_ns"] == waiting["approval"]["checkpoint_ns"]
                assert len(final["paired_messages"]) == 1
                assert final["paired_messages"][0] == {
                    "id": "tool:" + waiting["fixed"]["task_id"] + ":" + waiting["fixed"]["call_id"],
                    "call": waiting["fixed"]["call_id"],
                }
                assert final["saved_usage"]["tool_calls"] >= waiting["saved_usage"]["tool_calls"]
                assert (
                    final["saved_usage"]["active_elapsed_ms"]
                    >= waiting["saved_usage"]["active_elapsed_ms"]
                )
                assert (
                    final["saved_model"]["model_attempts"]
                    >= waiting["saved_model"]["model_attempts"]
                )
                assert final["runs"][0]["run_id"] != waiting["runs"][0]["run_id"]
                # Prove cross-process END once; other branches reuse that unchanged
                # classification and verify their own read-only result in this process.
                if mode == "normal":
                    stop(process)
                    process = start("ended")
                ended_before = probe("end_before_read")
                response = client.post(prefix + "/resume", json={})
                assert (
                    response.status_code == 200
                    and response.json()["accepted"] is False
                    and response.json()["run_id"] is None
                )
                ended_after = probe("end_read_only")
                for key in ("runs", "invocations", "writes"):
                    assert ended_after[key] == ended_before[key]
                assert ended_after["approval"] == ended_before["approval"]
                case["result"] = "PASS"
            except Exception as exc:
                case["result"] = "FAIL"
                case["failure"] = {
                    "category": type(exc).__name__,
                    "assertion": str(exc)
                    if isinstance(exc, AssertionError)
                    else "safe_category_only",
                }
                raise
            finally:
                for process in processes:
                    if process.poll() is None:
                        stop(process)
                client.close()
                run_async(fixtures(data, "cleanup"))
                after = run_async(fixtures(data, "snapshot"))
                case["protected_after"] = fingerprints(after)
                case["all_public_rows_columns_unchanged"] = before == after
                save()
                assert before == after, "protected_database_changed"
        print("PERSISTENCE621_PASS", mode, flush=True)

    for mode in modes:
        run_case(mode)
    report["protected_files_after"] = file_hashes()
    assert report["protected_files_before"] == report["protected_files_after"]
    report["result"] = "PASS"
    save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--modes",
        nargs="+",
        default=[
            "normal",
            "reject",
            "repair",
            "checkpoint",
            "unexecuted",
            "pending",
            "barrier",
            "expired_pending",
            "expired_approved",
            "success_expired",
            "business_unknown",
            "missing",
        ],
    )
    args = parser.parse_args()
    try:
        verify(args.output, args.modes)
    except Exception as exc:
        print(
            "PERSISTENCE621_FAILED",
            type(exc).__name__,
            str(exc) if isinstance(exc, AssertionError) else "safe_category_only",
            flush=True,
        )
        raise SystemExit(1) from None
