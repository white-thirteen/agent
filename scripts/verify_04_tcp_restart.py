"""Explicit uvicorn/TCP refund restart acceptance; never invoked by default tests."""

import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from app.main import create_app
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from scripts import run_async
from scripts.verify_04_restart import Provider


def server_app():
    """Test-only factory uses the production app and all production PG resources."""
    logging.disable(logging.CRITICAL)
    import app.main as main_module

    data = json.loads(Path(os.environ["REFUND04_MANIFEST"]).read_text(encoding="utf-8"))
    settings = Settings()
    validate_test_target(settings.test_database_url, settings.database_url)
    settings = settings.model_copy(
        update={
            "database_url": settings.test_database_url,
            "app_env": "test",
            "log_level": "CRITICAL",
            "demo_user_ids": (*settings.demo_user_ids, data["owner"]),
            "model_name": "controlled",
            "model_api_key": SecretStr("controlled"),
        }
    )

    @asynccontextmanager
    async def model_resources(config):
        provider = Provider(data["order"])
        yield (
            provider,
            ModelGateway(
                provider,
                ModelCallLimits(config.model_max_attempts, config.model_timeout_seconds, 0),
            ),
        )

    main_module.model_resources = model_resources
    return create_app(settings)


async def get_rows(data):
    settings = Settings()
    validate_test_target(settings.test_database_url, settings.database_url)
    pool = await open_pool(settings.model_copy(update={"database_url": settings.test_database_url}))
    try:
        async with pool.connection() as conn:
            assert await (
                await conn.execute("SELECT current_database(),current_user")
            ).fetchone() == ("agent_demo_test", "agent_test")
            row = await (
                await conn.execute(
                    "SELECT r.task_id,r.thread_id,r.call_id,r.raw_args,r.canonical_args,"
                    "r.args_digest,"
                    "r.operation_id,r.status,a.approval_id,a.subject_digest,a.checkpoint_ns,"
                    "o.is_refunded FROM refund_requests r JOIN approvals a USING(application_id) "
                    "JOIN demo_orders o USING(order_id) WHERE r.user_id=%s",
                    (data["owner"],),
                )
            ).fetchone()
            return [str(v) if k in (1, 6, 8) else v for k, v in enumerate(row)]
    finally:
        await pool.close()


def main():
    logging.disable(logging.CRITICAL)
    identifier = "restart04-tcp-" + uuid4().hex
    with tempfile.TemporaryDirectory(prefix="refund04-tcp-") as folder:
        manifest = Path(folder) / "manifest.json"
        data = {"owner": identifier, "order": identifier, "conversation": identifier}
        manifest.write_text(json.dumps(data), encoding="utf-8")
        processes = []
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        address = "http://127.0.0.1:" + str(port)

        def start():
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "scripts.verify_04_tcp_restart:server_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--loop",
                    "app.infrastructure.postgres:selector_event_loop",
                    "--log-level",
                    "critical",
                ],
                env={**os.environ, "REFUND04_MANIFEST": str(manifest)},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            processes.append(process)
            deadline = time.monotonic() + Settings().database_startup_timeout_seconds * 3
            while time.monotonic() < deadline:
                assert process.poll() is None, "server_exited"
                try:
                    health = httpx.get(address + "/health")
                    if health.status_code == 200 and health.json()["agent_ready"]:
                        return process
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            raise AssertionError("server_not_ready")

        def stop(process):
            process.terminate()
            process.wait(timeout=Settings().runtime_shutdown_grace_seconds + 5)
            assert process.poll() is not None

        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.verify_04_restart",
                    "--worker",
                    "setup",
                    str(manifest),
                    "normal",
                ],
                check=True,
            )
            old = start()
            response = httpx.post(
                address + "/agent/chat",
                json={
                    "user_id": identifier,
                    "conversation_id": identifier,
                    "message": "申请模拟退款",
                },
                timeout=Settings().run_timeout_seconds,
            )
            assert response.status_code == 200 and "event: workflow_paused" in response.text
            before = run_async(get_rows(data))
            assert before[7] == "PENDING" and before[11] is False
            stop(old)
            new = start()
            assert new.pid != old.pid and old.poll() is not None
            prefix = address + "/admin/approvals/" + before[8]
            response = httpx.post(
                prefix + "/decision", json={"decision": "APPROVED", "subject_digest": before[9]}
            )
            assert response.status_code == 200
            response = httpx.post(prefix + "/resume", json={})
            assert response.status_code == 202
            run_id = response.json()["run_id"]
            deadline = time.monotonic() + Settings().run_timeout_seconds
            while time.monotonic() < deadline:
                response = httpx.post(
                    address + "/agent/tasks/current",
                    json={"user_id": identifier, "conversation_id": identifier},
                )
                assert response.status_code == 200
                current = response.json()["current_task"]
                if current["task_status"] == "completed":
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("resume_did_not_complete")
            after = run_async(get_rows(data))
            assert before[:7] == after[:7] and before[8:11] == after[8:11]
            assert after[7] == "SUCCEEDED" and after[11] is True
            assert current["task_id"] == before[0]
            stop(new)
            evidence = {
                "old_pid": old.pid,
                "new_pid": new.pid,
                "old_exit_confirmed": True,
                "before": before,
                "after": after,
                "resume_run": run_id,
                "topology": "uvicorn TCP production lifespan with controlled model",
            }
            Path("docs/04-restart-evidence-tcp.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("UVICORN_TCP_FULL_PROCESS_RESTART_PASS", flush=True)
        finally:
            for process in processes:
                if process.poll() is None:
                    stop(process)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.verify_04_restart",
                    "--worker",
                    "cleanup",
                    str(manifest),
                    "normal",
                ],
                check=False,
            )
            assert result.returncode == 0, "cleanup_failed"


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            "TCP_RESTART_FAILED",
            type(exc).__name__,
            str(exc) if isinstance(exc, AssertionError) else "safe_category_only",
            flush=True,
        )
        raise SystemExit(1) from None
