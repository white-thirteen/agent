"""Opt-in real-PG, independent-process acceptance through the formal app lifespan.

Only the model and explicit failure boundaries are replaced. No production fault flags,
graph jumps, injected approvals or alternate repositories are used.
"""

import argparse
import inspect
import json
import logging
import os
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from contextlib import nullcontext as _no_patch
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from app.agents.types import AgentType, TaskType
from app.core.config import Settings
from app.domain.refunds import MockRefundService
from app.graph.contracts import RouteDecision, SupervisorOutput
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.postgres import EXPECTED_SCHEMA_VERSION, open_pool, validate_test_target
from app.main import create_app
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from app.workflows.approvals import ApprovalService
from scripts import run_async
from scripts.migrate import MIGRATIONS_DIR, migration_files


class Provider:
    def __init__(self, order, *, structured=False, tools=False):
        self.order, self.structured, self.tools = order, structured, tools

    def with_structured_output(self, schema, **kwargs):
        return Provider(self.order, structured=True)

    def bind_tools(self, tools):
        return Provider(self.order, tools=True)

    async def ainvoke(self, messages):
        if self.structured:
            return {
                "raw": AIMessage(content="controlled"),
                "parsed": SupervisorOutput(
                    kind="route",
                    decision=RouteDecision(
                        agent_type=AgentType.REFUND,
                        task_type=TaskType.REFUND_APPLY,
                        task_goal="申请模拟退款",
                        entities={"order_id": self.order},
                    ),
                ),
                "parsing_error": None,
            }
        if self.tools:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "original-call",
                        "name": "refund_order",
                        "args": {"order_id": self.order},
                    }
                ],
            )
        return AIMessage(content="模拟退款结果以已核验业务事实为准。")


async def database_snapshot(pool):
    """Compare complete business row sets and migration bytes without emitting their data."""
    result = {}
    async with pool.connection() as conn:
        assert await (await conn.execute("SELECT current_database(),current_user")).fetchone() == (
            "agent_demo_test",
            "agent_test",
        )
        for table in (
            "sessions",
            "demo_orders",
            "refund_requests",
            "approvals",
            "schema_migrations",
        ):
            rows = await (
                await conn.execute(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY 1")
            ).fetchall()
            result[table] = [r[0] for r in rows]
        assert len(result["schema_migrations"]) == EXPECTED_SCHEMA_VERSION
        applied = dict(
            await (
                await conn.execute(
                    "SELECT version,checksum FROM schema_migrations ORDER BY version"
                )
            ).fetchall()
        )
        assert applied == {
            version: entry[0] for version, entry in migration_files(MIGRATIONS_DIR).items()
        }
        result["threads"] = [
            r[0]
            for r in await (
                await conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id")
            ).fetchall()
        ]
    return result


async def worker(phase, path, mode):
    logging.disable(logging.CRITICAL)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    settings = Settings()
    validate_test_target(settings.test_database_url, settings.database_url)
    settings = settings.model_copy(
        update={
            "database_url": settings.test_database_url,
            "app_env": "test",
            "log_level": "CRITICAL",
            "demo_user_ids": (*settings.demo_user_ids, data["owner"]),
        }
    )
    pool = await open_pool(settings)
    try:
        if phase == "setup":
            data["before"] = await database_snapshot(pool)
            async with pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO demo_orders VALUES (%s,%s,42.50,'CNY','paid',false,now())",
                    (data["order"], data["owner"]),
                )
        elif phase == "cleanup":
            async with pool.connection() as conn:
                threads = await (
                    await conn.execute(
                        "SELECT thread_id FROM sessions WHERE user_id=%s", (data["owner"],)
                    )
                ).fetchall()
                await conn.execute(
                    "DELETE FROM approvals WHERE application_id IN "
                    "(SELECT application_id FROM refund_requests WHERE user_id=%s)",
                    (data["owner"],),
                )
                await conn.execute("DELETE FROM refund_requests WHERE user_id=%s", (data["owner"],))
                await conn.execute("DELETE FROM sessions WHERE user_id=%s", (data["owner"],))
                await conn.execute(
                    "DELETE FROM demo_orders WHERE owner_id=%s AND order_id=%s",
                    (data["owner"], data["order"]),
                )
            checkpoint_pool = await open_checkpoint_pool(settings)
            try:
                saver = AsyncPostgresSaver(checkpoint_pool, serde=checkpoint_serializer())
                for (thread,) in threads:
                    await saver.adelete_thread(str(thread))
                    async with pool.connection() as conn:
                        for table in ("checkpoints", "checkpoint_writes", "checkpoint_blobs"):
                            assert await (
                                await conn.execute(
                                    f"SELECT count(*) FROM {table} WHERE thread_id=%s",
                                    (str(thread),),
                                )
                            ).fetchone() == (0,)
            finally:
                await checkpoint_pool.close()
            assert await database_snapshot(pool) == data["before"]
            print("CLEANUP_FULL_ROWSETS_MIGRATIONS_THREADS_UNCHANGED", flush=True)
        else:
            await app_phase(settings, data, phase, mode)
        Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    finally:
        await pool.close()


async def app_phase(settings, data, phase, mode):
    events, writes, invocations = [], [], []
    original_add = StateGraph.add_node
    original_put = AsyncPostgresSaver.aput
    original_put_writes = AsyncPostgresSaver.aput_writes
    original_execute = MockRefundService.execute_original
    original_invoke = CompiledStateGraph.ainvoke
    original_bind = ApprovalService.bind_interrupt
    fired = False

    async def invoke(self, input, config=None, **kwargs):
        context = kwargs.get("context")
        invocations.append(
            {
                "graph": "refund_child" if "execute_refund" in self.nodes else "supervisor_root",
                "input": "None" if input is None else type(input).__name__,
                "run": context.context.run_id if context else None,
                "mode": context.execution_mode if context else None,
            }
        )
        return await original_invoke(self, input, config, **kwargs)

    async def bind(self, approval_id, binding):
        nonlocal fired
        if phase == "wait" and mode == "repair" and not fired:
            fired = True
            raise psycopg.OperationalError("controlled binding boundary")
        return await original_bind(self, approval_id, binding)

    def add_node(self, node, action=None, **kwargs):
        name = node if isinstance(node, str) else node.__name__
        fn = action if isinstance(node, str) else node
        # Instrument only refund nodes; retain the framework's Runtime injection contract.
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
                recovery = ctx.refund_recovery
                events.append(
                    {
                        "node": name,
                        "run": ctx.context.run_id,
                        "mode": ctx.execution_mode,
                        "recovery": recovery.disposition if recovery else None,
                    }
                )
                if (
                    phase == "fault"
                    and (
                        (mode == "reply" and name == "compose_refund_reply")
                        or (mode == "unexecuted" and name == "execute_refund")
                    )
                    and not fired
                ):
                    fired = True
                    raise RuntimeError("controlled reply boundary")
                value = fn(state, runtime)
                return await value if inspect.isawaitable(value) else value

            return original_add(self, name, observe, **kwargs)
        return original_add(self, node, action, **kwargs)

    async def put(self, config, checkpoint, metadata, new_versions):
        nonlocal fired
        values = checkpoint.get("channel_values", {})
        if phase == "fault" and config["configurable"].get("checkpoint_ns"):
            hit = (
                (mode == "checkpoint" and values.get("execution_result"))
                or (mode == "barrier" and values.get("prepared_attempt"))
                or (mode == "pending" and not fired and values.get("execution_result"))
            )
            if hit:
                fired = True
                raise RuntimeError("controlled sync checkpoint boundary")
        return await original_put(self, config, checkpoint, metadata, new_versions)

    async def put_writes(self, config, writes, task_id, task_path=""):
        nonlocal fired
        if phase == "fault" and mode in ("checkpoint", "barrier"):
            field = "execution_result" if mode == "checkpoint" else "prepared_attempt"
            if any(key == field and value for key, value in writes):
                fired = True
                raise RuntimeError("controlled checkpoint writes boundary")
        return await original_put_writes(self, config, writes, task_id, task_path)

    async def execute(self, *, context, order_id):
        writes.append({"run": context.run_id, "operation": context.operation_id})
        return await original_execute(self, context=context, order_id=order_id)

    @asynccontextmanager
    async def controlled_resources(config):
        provider = Provider(data["order"])
        yield (
            provider,
            ModelGateway(
                provider,
                ModelCallLimits(config.model_max_attempts, config.model_timeout_seconds, 0),
            ),
        )

    # A complete configured model is required by the production lifespan even for the substitute.
    if mode != "real" and not settings.model_configured:
        from pydantic import SecretStr

        settings = settings.model_copy(
            update={"model_name": "controlled", "model_api_key": SecretStr("controlled")}
        )
    app = create_app(settings)
    with (
        patch.object(StateGraph, "add_node", add_node),
        patch.object(AsyncPostgresSaver, "aput", put),
        patch.object(AsyncPostgresSaver, "aput_writes", put_writes),
        patch.object(MockRefundService, "execute_original", execute),
        patch.object(ApprovalService, "bind_interrupt", bind),
        patch.object(CompiledStateGraph, "ainvoke", invoke),
    ):
        with (
            patch("app.main.model_resources", controlled_resources)
            if mode != "real"
            else _no_patch()
        ):
            async with app.router.lifespan_context(app):
                runtime = app.state.agent_runtime
                assert runtime.is_ready
                transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    if phase == "wait":
                        response = await client.post(
                            "/agent/chat",
                            json={
                                "user_id": data["owner"],
                                "conversation_id": data["conversation"],
                                "message": "请申请模拟退款，订单号 " + data["order"],
                            },
                        )
                        assert response.status_code == 200
                        assert (
                            "pause_binding_unavailable"
                            if mode == "repair"
                            else "event: workflow_paused"
                        ) in response.text
                        first = next(iter(runtime._records.values()))
                        data["thread"] = first.context.thread_id
                        data["task"] = first.execution.context.task_id
                        data["first_run"] = first.execution.context.run_id
                        async with app.state.pool.connection() as conn:
                            row = await (
                                await conn.execute(
                                    "SELECT approval_id FROM approvals WHERE application_id IN "
                                    "(SELECT application_id FROM refund_requests WHERE user_id=%s)",
                                    (data["owner"],),
                                )
                            ).fetchone()
                        data["approval"] = str(row[0])
                        if mode == "repair":
                            path = "/admin/approvals/" + data["approval"]
                            detail = (await client.get(path)).json()
                            denied = await client.post(
                                path + "/decision",
                                json={
                                    "decision": "APPROVED",
                                    "subject_digest": detail["subject_digest"],
                                },
                            )
                            assert denied.status_code == 409
                            count = len(runtime._records)
                            repaired = await client.post(path + "/repair-binding", json={})
                            assert repaired.status_code == 200 and repaired.json()["repaired"]
                            repeated = await client.post(path + "/repair-binding", json={})
                            assert repeated.status_code == 200 and not repeated.json()["repaired"]
                            assert len(runtime._records) == count and not writes
                            data["repair_binding"] = "real_interrupt_CAS_idempotent_zero_new_run"
                    else:
                        path = "/admin/approvals/" + data["approval"]
                        detail = (await client.get(path)).json()
                        if phase == "fault" or (
                            phase == "resume" and mode in ("normal", "real", "repair")
                        ):
                            response = await client.post(
                                path + "/decision",
                                json={
                                    "decision": "APPROVED",
                                    "subject_digest": detail["subject_digest"],
                                },
                            )
                            assert response.status_code == 200
                        response = await client.post(path + "/resume", json={})
                        if mode in ("pending", "barrier") and phase == "resume":
                            assert response.status_code == 409
                            assert not writes and not runtime._records and not events
                            data.setdefault("evidence", []).append(
                                {
                                    "phase": phase,
                                    "pid": os.getpid(),
                                    "handler_attempts": 0,
                                    "safe_refusal": True,
                                }
                            )
                            print(
                                "PHASE_OK pending unknown_refused_zero_run_zero_write", flush=True
                            )
                            return
                        assert response.status_code == 202, (response.status_code, response.json())
                        run = response.json()["run_id"]
                        await runtime._records[run].task
                        record = runtime._records[run]
                        assert (
                            record.execution.context.task_id == data["task"]
                            and run != data["first_run"]
                        )
                        data.setdefault("runs", []).append(run)
                        data.setdefault("usage", []).append(
                            {
                                "model": record.execution.scope.model_usage().model_attempts,
                                "tools": record.execution.scope.run_usage().tool_calls,
                                "active_ms": record.execution.scope.run_usage().active_elapsed_ms,
                            }
                        )
                        assert (
                            record.execution.scope.run_usage().tool_calls
                            >= data["waiting_usage"]["tool_calls"]
                        )
                        assert (
                            record.execution.scope.run_usage().active_elapsed_ms
                            >= data["waiting_usage"]["active_elapsed_ms"]
                        )
                        if phase == "resume":
                            assert record.task_status == "completed", record.task_status
                            assert len(writes) == (
                                1 if mode in ("normal", "unexecuted", "real", "repair") else 0
                            )
                            repeated = await client.post(path + "/resume", json={})
                            assert (
                                repeated.status_code == 200 and repeated.json()["accepted"] is False
                            )
                    approval, application = await app.state.approval_service.get_application(
                        data["approval"]
                    )
                    assert (
                        str(application["thread_id"]) == data["thread"]
                        and application["task_id"] == data["task"]
                    )
                    fixed = {
                        k: str(application[k])
                        for k in ("call_id", "args_digest", "operation_id", "task_id", "thread_id")
                    }
                    fixed["canonical_args"] = application["canonical_args"]
                    fixed["raw_args"] = application["raw_args"]
                    fixed["namespace"] = approval["checkpoint_ns"]
                    fixed["subject_digest"] = approval["subject_digest"]
                    if "fixed" in data:
                        assert fixed == data["fixed"]
                    data["fixed"] = fixed
                    root = await runtime._graph.aget_state(
                        {"configurable": {"thread_id": data["thread"]}}, subgraphs=True
                    )
                    if root.next:
                        # Runtime expands nested config pointers with its formal inspector.
                        classified = await runtime._inspect_refund_checkpoint(approval, application)
                        child = classified.child
                        if mode == "pending" and phase == "fault":
                            assert classified.kind == "unknown" and fired and len(writes) == 1
                            assert application["status"] == "SUCCEEDED"
                            data.setdefault("evidence", []).append(
                                {
                                    "phase": phase,
                                    "pid": os.getpid(),
                                    "handler_attempts": 1,
                                    "status": application["status"],
                                    "classification": "unknown",
                                }
                            )
                            print("PHASE_OK pending saved_writes_unknown", flush=True)
                            return
                        if child is None:
                            actual = root.tasks[0].state
                            if isinstance(actual, dict):
                                actual = await runtime._graph.aget_state(actual, subgraphs=True)
                            print(
                                "UNCLASSIFIED_SAFE_POSITION",
                                list(actual.next),
                                [t.name for t in actual.tasks],
                                flush=True,
                            )
                            latest = await runtime._graph.aget_state(
                                {
                                    "configurable": {
                                        "thread_id": data["thread"],
                                        "checkpoint_ns": approval["checkpoint_ns"],
                                    }
                                },
                                subgraphs=True,
                            )
                            print(
                                "LATEST_NAMESPACE_POSITION",
                                list(latest.next),
                                [t.name for t in latest.tasks],
                                "keys",
                                sorted(latest.values),
                                flush=True,
                            )
                        assert child is not None, (
                            "child_unclassified",
                            classified.kind,
                            list(root.next),
                            fired,
                            len(writes),
                        )
                        data.setdefault("positions", []).append(list(child.next))
                        if phase == "wait":
                            assert child.next == ("approval_gate",) and len(child.interrupts) == 1
                            data["waiting_usage"] = child.values["run_usage"]
                            assert len(writes) == 0
                        elif phase == "fault":
                            expected = {
                                "checkpoint": "execute_refund",
                                "barrier": "prepare_refund_attempt",
                                "reply": "compose_refund_reply",
                                "unexecuted": "execute_refund",
                            }[mode]
                            assert child.next == (expected,) and fired, (
                                "fault_position",
                                list(child.next),
                                fired,
                                len(writes),
                            )
                            assert len(writes) == (0 if mode in ("barrier", "unexecuted") else 1), (
                                "handler_count"
                            )
                            if mode == "unexecuted":
                                data["old_attempt"] = child.values["prepared_attempt"].attempt_id
                    elif phase == "fault":
                        raise AssertionError(("fault_graph_ended", fired, len(writes)))
                    if phase == "resume":
                        assert not root.next
                        async with app.state.pool.connection() as conn:
                            assert await (
                                await conn.execute(
                                    "SELECT is_refunded FROM demo_orders WHERE order_id=%s",
                                    (data["order"],),
                                )
                            ).fetchone() == (True,)
                        assert application["status"] == "SUCCEEDED"
                        # Completed child remains accessible in the original namespace.
                        child = await runtime._graph.aget_state(
                            {
                                "configurable": {
                                    "thread_id": data["thread"],
                                    "checkpoint_ns": data["fixed"]["namespace"],
                                }
                            }
                        )
                        messages = [
                            m
                            for m in child.values["messages"]
                            if isinstance(m, ToolMessage)
                            and m.tool_call_id == application["call_id"]
                        ]
                        assert (
                            len(messages) == 1
                            and messages[0].id
                            == "tool:" + data["task"] + ":" + application["call_id"]
                        )
                        assert all(e["run"] == data["runs"][-1] for e in events)
                        if mode in ("checkpoint", "reply"):
                            assert any(e["recovery"] == "succeeded" for e in events)
                        if mode == "unexecuted":
                            assert child.values["prepared_attempt"].run_id == data["runs"][-1]
                            assert (
                                child.values["prepared_attempt"].attempt_id != data["old_attempt"]
                            )
                    data.setdefault("evidence", []).append(
                        {
                            "phase": phase,
                            "pid": os.getpid(),
                            "nodes": events,
                            "invocations": invocations,
                            "handler_attempts": len(writes),
                            "status": application["status"],
                        }
                    )
                    print(
                        "PHASE_OK", mode, phase, "handler_attempts=" + str(len(writes)), flush=True
                    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--real", action="store_true", help="Explicitly enable paid configured model"
    )
    parser.add_argument(
        "--mode",
        choices=("normal", "checkpoint", "reply", "barrier", "pending", "unexecuted", "repair"),
    )
    parser.add_argument("--worker", nargs=3, metavar=("PHASE", "MANIFEST", "MODE"))
    args = parser.parse_args()
    if args.worker:
        run_async(worker(*args.worker))
        return
    modes = (
        ("real",)
        if args.real
        else (args.mode,)
        if args.mode
        else ("normal", "checkpoint", "reply", "barrier", "unexecuted", "pending", "repair")
    )
    for mode in modes:
        identifier = "restart04-" + uuid4().hex
        with tempfile.TemporaryDirectory(prefix="refund04-") as folder:
            manifest = Path(folder) / "manifest.json"
            manifest.write_text(
                json.dumps({"owner": identifier, "order": identifier, "conversation": identifier}),
                encoding="utf-8",
            )
            try:
                phases = [
                    "setup",
                    "wait",
                    *([] if mode in ("normal", "real", "repair") else ["fault"]),
                    "resume",
                ]
                for phase in phases:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "scripts.verify_04_restart",
                            "--worker",
                            phase,
                            str(manifest),
                            mode,
                        ],
                        check=False,
                    )
                    assert result.returncode == 0, "worker_failed_" + phase
                evidence = json.loads(manifest.read_text(encoding="utf-8"))
                assert len({item["pid"] for item in evidence["evidence"]}) == len(
                    evidence["evidence"]
                )
                evidence.pop("before")
                destination = Path("docs") / ("04-restart-evidence-" + mode + ".json")
                destination.write_text(
                    json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print("SCENARIO_PASS", mode, flush=True)
            finally:
                cleanup = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "scripts.verify_04_restart",
                        "--worker",
                        "cleanup",
                        str(manifest),
                        mode,
                    ],
                    check=False,
                )
                assert cleanup.returncode == 0, "cleanup_failed"


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            "RESTART_ACCEPTANCE_FAILED",
            type(exc).__name__,
            str(exc) if isinstance(exc, AssertionError) else "safe_category_only",
            flush=True,
        )
        raise SystemExit(1) from None
