"""Independent Task6.1.1 QA: no paid calls; existing tests and real factory lifecycle."""

import asyncio
import json
import os
from pathlib import Path
import sys
import threading
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import httpx
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr
import pytest

from app.core.config import Settings
from app.graph.specialists.preferences import preference_instructions
from app.infrastructure.postgres import open_pool, validate_test_target
from app.knowledge.chunking import token_count
from app.main import create_app
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints

OUT = ROOT / "docs/question/06-assembly-qa-evidence.json"
report = {}


def save():
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


settings = Settings()
assert settings.test_database_url is not None
validate_test_target(settings.test_database_url, settings.database_url)
test_settings = settings.model_copy(update={"database_url": settings.test_database_url})


async def snapshot():
    pool = await open_pool(test_settings)
    try:
        return await database_snapshot(pool)
    finally:
        await pool.close()


before = run_async(snapshot())
os.environ["AGENT_TEST_DATABASE_URL"] = settings.test_database_url.get_secret_value()
selected = [
    "tests/test_resources.py", "tests/test_application.py",
    "tests/test_knowledge_graph.py", "tests/test_memory_reader.py",
    "tests/test_knowledge_postgres.py", "tests/test_memory_postgres.py",
    "tests/test_memory_manage_postgres.py",
]
if "--factory-only" in sys.argv:
    report = json.loads(OUT.read_text(encoding="utf-8"))
    result = report["tests"]["exit_code"]
else:
    result = pytest.main([*selected, "-q"])
    report["tests"] = {"files": selected, "exit_code": int(result)}
after = run_async(snapshot())
report["protected_before"] = fingerprints(before)
report["protected_after_tests"] = fingerprints(after)
report["tests_public_unchanged"] = before == after
save()
assert result == 0 and before == after


async def real_factory():
    name = "qa611-" + uuid4().hex
    local = settings.model_copy(update={
        "database_url": SecretStr(make_conninfo(
            settings.test_database_url.get_secret_value(), application_name=name)),
        "app_env": "test", "demo_user_ids": (name,), "embedding_enabled": True,
    })
    app = create_app(local)
    current = asyncio.current_task()
    baseline_tasks = set(asyncio.all_tasks())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            health = response.json()
        assert health["agent_ready"] and health["knowledge_ready"]
        assert all(health[key] == "ready" for key in (
            "database_status", "checkpoint_status", "embedding_status", "store_status",
            "knowledge_status"))
        repository = app.state.knowledge_retriever.repository
        await repository.check_ready(app.state.knowledge_retriever.profile)
        assert app.state.tool_registry.frozen
        for tool in ("get_order", "refund_order", "search_knowledge", "read_preferences",
                     "write_preferences"):
            assert app.state.tool_registry.get(tool).metadata.enabled
        raw_model = app.state.model_gateway._model
        assert app.state.agent_runtime.is_ready
        report["real_factory_health"] = health
        report["profile"] = json.loads(app.state.knowledge_retriever.profile)
        assert await database_snapshot(app.state.pool) == before
    await asyncio.sleep(0)
    assert app.state.pool.closed and app.state.checkpoint_pool.closed
    assert raw_model.http_client.is_closed and raw_model.http_async_client.is_closed
    probe_pool = await open_pool(test_settings)
    try:
        async with probe_pool.connection() as conn:
            count = (await (await conn.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s", (name,)
            )).fetchone())[0]
        assert count == 0
        assert await database_snapshot(probe_pool) == before
    finally:
        await probe_pool.close()
    await asyncio.sleep(0)
    extra = [t for t in asyncio.all_tasks() - baseline_tasks if t is not current and not t.done()]
    qwen = [t for t in threading.enumerate() if t.name.startswith("qwen-embedding")]
    assert not extra and not qwen
    report["real_shutdown"] = {"named_pg_connections": count,
                                "qwen_threads": len(qwen), "extra_tasks": len(extra)}
    report["factory_public_unchanged"] = True


run_async(real_factory())
prompt = preference_instructions({"memory_context": {"preferences": {
    "answer_language": "en", "answer_style": "detailed"}}})
assert token_count(prompt) <= 128
assert "write the answer in English" in prompt
assert "current explicit language/style request > stored preferences" in prompt
report["preference_prompt_tokens"] = token_count(prompt)
report["result"] = "PASS"
save()
print(json.dumps({"result": "PASS", "prompt_tokens": token_count(prompt)}, ensure_ascii=False))
