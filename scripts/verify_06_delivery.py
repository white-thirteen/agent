"""Explicit delivery gate: full pytest, real test PG protection and clean startup.

Run with the independently installed delivery interpreter. No initialization,
fixed-order writes or paid Chat calls are added by this wrapper.
"""

import argparse
import asyncio
import importlib.metadata
import json
import os
import platform
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from app.main import create_app
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints


async def snapshot(settings):
    pool = await open_pool(settings)
    try:
        return await database_snapshot(pool)
    finally:
        await pool.close()


async def startup(settings):
    """Actual loopback HTTP with Uvicorn's graceful lifespan shutdown."""
    app = create_app(settings.model_copy(update={"embedding_enabled": True}))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8632, log_level="critical"))
    execution = asyncio.create_task(server.serve())
    started = time.perf_counter()
    try:
        while not server.started:
            if execution.done():
                await execution
                raise AssertionError("Server exited before readiness")
            await asyncio.sleep(0.1)
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:8632/health")
        response.raise_for_status()
        health = response.json()
        assert health["agent_ready"] and health["embedding_status"] == "ready"
        assert health["store_status"] == health["checkpoint_status"] == "ready"
        result = {"health": health, "startup_seconds": round(time.perf_counter() - started, 3)}
    finally:
        server.should_exit = True
        await execution
    result["business_pool_closed"] = app.state.pool.closed
    result["checkpoint_pool_closed"] = app.state.checkpoint_pool.closed
    assert result["business_pool_closed"] and result["checkpoint_pool_closed"]
    result["remaining_async_tasks"] = [
        task.get_name()
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task() and not task.done()
    ]
    assert not result["remaining_async_tasks"]
    result["remaining_qwen_threads"] = [
        thread.name for thread in threading.enumerate() if thread.name.startswith("qwen-embedding")
    ]
    assert not result["remaining_qwen_threads"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qwen-evidence", type=Path, required=True)
    args = parser.parse_args()
    print(f"Delivery verifier PID={os.getpid()}", flush=True)
    assert not args.output.exists() and not args.qwen_evidence.exists()
    original = Settings()
    validate_test_target(original.test_database_url, original.database_url)
    settings = original.model_copy(
        update={
            "database_url": original.test_database_url,
            "app_env": "test",
            "log_level": "CRITICAL",
        }
    )
    os.environ["AGENT_TEST_DATABASE_URL"] = original.test_database_url.get_secret_value()
    os.environ["AGENT_VERIFY_DEMO_QWEN"] = "1"
    os.environ["AGENT_DEMO_FIX_EVIDENCE"] = str(args.qwen_evidence.resolve())
    report = {
        "python": platform.python_version(),
        "executable": sys.executable,
        "pid": os.getpid(),
        "base_prefix": sys.base_prefix,
        "prefix": sys.prefix,
        "pyvenv_cfg": (Path(sys.prefix) / "pyvenv.cfg").read_text("utf-8"),
        "versions": {
            name: importlib.metadata.version(name)
            for name in (
                "torch",
                "sentence-transformers",
                "transformers",
                "openai",
                "langchain-openai",
                "langgraph",
                "langgraph-checkpoint-postgres",
                "psycopg",
            )
        },
        "paid_chat_calls": 0,
        "pytest_args": ["-q"],
        "real_qwen_enabled": True,
    }
    before = run_async(snapshot(settings))
    report["protected_before"] = fingerprints(before)
    outcomes = {"passed": 0, "failed": 0, "skipped": 0}

    class Outcomes:
        def pytest_runtest_logreport(self, report):
            if report.when == "call" or report.failed or report.skipped:
                outcomes[report.outcome] += 1

    started = time.perf_counter()
    try:
        report["pytest_exit"] = int(pytest.main(["-q"], plugins=[Outcomes()]))
        report["pytest_seconds"] = round(time.perf_counter() - started, 3)
        report["pytest_outcomes"] = outcomes
        assert report["pytest_exit"] == 0
        assert outcomes["failed"] == outcomes["skipped"] == 0
        report["startup"] = run_async(startup(settings))
    finally:
        after = run_async(snapshot(settings))
        report["protected_after"] = fingerprints(after)
        report["protected_unchanged"] = before == after
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        assert before == after


if __name__ == "__main__":
    main()
