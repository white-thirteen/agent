"""Only the preference, context and early-disconnect gaps left by run 01."""

import asyncio
import json
import runpy
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[3]
folder = ROOT / "docs/integration/2026-11-20"
probe = runpy.run_path(str(folder / "project-http-probe.py"))
save = probe["save"]


async def context_rows(data):
    pool = await probe["open_pool"](probe["settings_for"](data))
    try:
        async with pool.connection() as conn:
            result = {}
            for table in (
                "context_archive",
                "context_summary",
                "context_revision",
                "context_maintenance",
            ):
                result[table] = await (
                    await conn.execute(
                        f"SELECT row_to_json(t)::text FROM {table} t WHERE user_id=%s",
                        (data["user_a"],),
                    )
                ).fetchall()
            result["attempts"] = await (
                await conn.execute(
                    "SELECT a.status,a.input_tokens,a.output_tokens,a.total_tokens,a.usage_status "
                    "FROM context_maintenance_attempt a "
                    "JOIN context_maintenance m USING(maintenance_id) "
                    "WHERE m.user_id=%s",
                    (data["user_a"],),
                )
            ).fetchall()
            return result
    finally:
        await pool.close()


async def checkpoint_details(data, snapshots):
    pool = await probe["open_checkpoint_pool"](probe["settings_for"](data))
    try:
        saver = probe["AsyncPostgresSaver"](pool, serde=probe["checkpoint_serializer"]())
        found = {}
        for snapshot in snapshots:
            if not snapshot["checkpoint_id"]:
                continue
            key = (snapshot["thread"], snapshot["checkpoint_id"])
            item = await saver.aget_tuple(
                {"configurable": {"thread_id": key[0], "checkpoint_id": key[1]}}
            )
            assert item
            found[key] = item.checkpoint
        return found
    finally:
        await pool.close()


async def main():
    output = folder / "project-http-run-02"
    output.mkdir(exist_ok=False)
    prefix = "project-http-gap-" + uuid4().hex
    data = {
        "user_a": prefix + "-a",
        "user_b": prefix + "-b",
        "document": prefix + "-doc",
        "orders": [prefix + "-one", prefix + "-two"],
        "archive": str(output / "archive"),
    }
    report = {
        "result": "IN_PROGRESS",
        "cases": [],
        "limitations": [
            "Context uses legitimate order queries and a non-authoritative marker",
            "No UI tested; early disconnect is not replay",
            "Unreported model tokens remain unknown; task attempts are cumulative",
        ],
    }
    save(output, "manifest.json", data)
    save(output, "report.json", report)
    process = client = server_log = None
    try:
        await probe["setup"](output, data, report)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=180)
        server_log = (output / "server.log").open("xb")
        process = subprocess.Popen(
            [
                sys.executable,
                str(folder / "project-http-probe.py"),
                "--server",
                "--manifest",
                str(output / "manifest.json"),
                "--port",
                str(port),
            ],
            cwd=ROOT,
            stdout=server_log,
            stderr=subprocess.STDOUT,
        )
        for _ in range(600):
            assert process.poll() is None, "server exited"
            try:
                health = client.get("/health", timeout=3)
                if health.status_code == 200 and health.json().get("agent_ready"):
                    break
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.5)
        else:
            raise AssertionError("server startup timeout")
        report["pid"] = process.pid
        serial = 0

        def req(label, path, body):
            nonlocal serial
            serial += 1
            response = client.post(path, json=body)
            filename = f"http-{serial:02d}-{label}.bin"
            (output / filename).write_bytes(response.content)
            report["cases"].append(
                {"label": label, "status": response.status_code, "raw": filename}
            )
            save(output, "report.json", report)
            assert response.status_code == 200, (label, response.status_code, response.text)
            return response

        def identity(conversation, user=None):
            return {
                "user_id": user or data["user_a"],
                "conversation_id": prefix + "-" + conversation,
            }

        def chat(label, conversation, message):
            ident = identity(conversation)
            response = req(
                label,
                "/agent/chat",
                {**ident, "message": message, "input_mode": "new_task", "request_id": str(uuid4())},
            )
            frames = []
            for block in response.text.replace("\r\n", "\n").split("\n\n"):
                lines = block.splitlines()
                event = next((x[7:] for x in lines if x.startswith("event: ")), None)
                payload = next((x[6:] for x in lines if x.startswith("data: ")), None)
                if event and payload:
                    frames.append((event, json.loads(payload)))
            assert sum(event == "done" for event, _ in frames) == 1
            run_id = next((body.get("run_id") for _, body in frames if body.get("run_id")), None)
            assert run_id
            run = req(label + "-run", f"/agent/runs/{run_id}/status", ident).json()
            report["cases"][-1]["run"] = run
            save(output, "report.json", report)
            assert run["task_status"] == "completed", (label, run)
            return run

        def mutate(name, operation, revision):
            payload = {
                "user_id": data["user_a"],
                "operation_id": str(uuid4()),
                "expected_revision": revision,
                "command": operation,
            }
            result = req(name, "/agent/preferences/mutations", payload).json()
            assert result["status"] == "applied"
            return result, payload

        written, payload = mutate(
            "preference-create",
            {"operation": "upsert", "field": "answer_language", "value": "en"},
            0,
        )
        assert (
            req("preference-idempotent", "/agent/preferences/mutations", payload).json() == written
        )
        assert (
            req("preference-other", "/agent/preferences/read", {"user_id": data["user_b"]}).json()[
                "revision"
            ]
            is None
        )
        chat("preference-cross-session", "new-session", "请查询我的订单 " + data["orders"][0])
        history = "history"
        for i in range(4):
            message = "请查询我的订单 " + data["orders"][0]
            if i == 0:
                message += "，备注：蓝色海星。"
            chat(f"history-{i + 1}", history, message)
        before = await probe["audit_context"](data)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            before = await probe["audit_context"](data)
            if any(
                row[1] == identity(history)["conversation_id"]
                and row[2] in ("SUCCEEDED", "FAILED", "EXHAUSTED")
                for row in before["maintenance"]
            ):
                break
            await asyncio.sleep(0.5)
        report["context_before_followup"] = before
        report["context_database_before"] = await context_rows(data)
        old_checkpoints = await checkpoint_details(data, before["snapshots"])
        report["context_views_before"] = [
            {
                "thread": thread,
                "checkpoint_id": checkpoint,
                "view": values.get("channel_values", {}).get("context_view"),
                "memory_context": values.get("channel_values", {}).get("memory_context"),
            }
            for (thread, checkpoint), values in old_checkpoints.items()
        ]
        save(output, "report.json", report)
        chat("history-followup", history, "请再查询我的订单 " + data["orders"][0])
        report["context_after_followup"] = await probe["audit_context"](data)
        report["context_database_after"] = await context_rows(data)
        reread = await checkpoint_details(data, before["snapshots"])
        report["prior_checkpoints_unchanged"] = old_checkpoints == reread
        assert report["prior_checkpoints_unchanged"]
        updated, _ = mutate(
            "preference-update",
            {"operation": "upsert", "field": "answer_language", "value": "zh-CN"},
            written["revision"],
        )
        deleted, _ = mutate(
            "preference-delete",
            {"operation": "delete", "field": "answer_language"},
            updated["revision"],
        )
        assert (
            req("preference-final", "/agent/preferences/read", {"user_id": data["user_a"]}).json()[
                "revision"
            ]
            == deleted["revision"]
        )
        ident = identity("disconnect")
        body = {
            **ident,
            "message": "请查询我的订单 " + data["orders"][1],
            "input_mode": "new_task",
            "request_id": str(uuid4()),
        }
        with client.stream("POST", "/agent/chat", json=body) as response:
            assert response.status_code == 200
            chunks = bytearray()
            for chunk in response.iter_raw():
                chunks.extend(chunk)
                if b"\n\n" in chunks.replace(b"\r\n", b"\n"):
                    break
        (output / "sse-disconnect-prefix.bin").write_bytes(chunks)
        lines = chunks.decode("utf-8").splitlines()
        events = [json.loads(x[6:]) for x in lines if x.startswith("data: ")]
        run_id = next(item["run_id"] for item in events if item.get("run_id"))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = req("disconnect-status", f"/agent/runs/{run_id}/status", ident).json()
            if state["run_status"] != "running":
                break
            await asyncio.sleep(0.5)
        assert state["task_status"] == "completed", state
        report["disconnect_run"] = state
        report["result"] = "SCENARIOS_COMPLETED_PENDING_REVIEW"
    except BaseException as error:
        report["result"] = "FAIL"
        report["failure"] = {"category": type(error).__name__, "detail": str(error)}
        raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=30)
        if client:
            client.close()
        if server_log:
            server_log.close()
        save(output, "report.json", report)
        if (output / "protected.pickle").exists():
            await probe["cleanup"](output, data, report)
        archive = Path(data["archive"])
        if archive.exists():
            assert archive.parent == output and archive.name == "archive"
            shutil.rmtree(archive)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
