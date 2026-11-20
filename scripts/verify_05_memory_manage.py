"""Explicit limited real Chat acceptance; isolated test identities, no config overrides.

The database target and UUID allowlist provide test isolation. Model/provider,
embedding flags and budgets retain Settings exactly; disabled RAG is reported.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp

from app.core.config import PROJECT_ROOT, Settings
from app.infrastructure.checkpoint import checkpoint_serializer
from app.infrastructure.postgres import validate_test_target
from app.main import create_app
from app.memory.manager import preference_namespace
from scripts import run_async

sys.path.insert(0, str(PROJECT_ROOT / "tests"))
from test_memory_postgres import database_snapshot  # noqa: E402


def fingerprints(snapshot):
    return {
        table: {
            "rows": len(value[0]),
            "columns": len(value[1]),
            "sha256": hashlib.sha256(repr(value).encode()).hexdigest(),
        }
        for table, value in snapshot.items()
    }


def compare_publication_snapshots(before, after, *, expected_delta=0):
    """Compare all protected state, allowing only a monotonic publication watermark."""
    result = {"protected_unchanged": False, "watermark_before": None, "watermark_after": None}
    if before.keys() != after.keys() or "knowledge_index_state" not in before:
        return result
    if any(before[name] != after[name] for name in before if name != "knowledge_index_state"):
        return result
    old_rows, old_columns = before["knowledge_index_state"]
    new_rows, new_columns = after["knowledge_index_state"]
    if old_columns != new_columns or len(old_rows) != 1 or len(new_rows) != 1:
        return result
    old, new = json.loads(old_rows[0][0]), json.loads(new_rows[0][0])
    old_watermark = old.pop("watermark", None)
    new_watermark = new.pop("watermark", None)
    result.update(watermark_before=old_watermark, watermark_after=new_watermark)
    if type(old_watermark) is not int or type(new_watermark) is not int:
        return result
    delta = new_watermark - old_watermark
    result["protected_unchanged"] = (
        old == new and old_watermark > 0 and delta >= 0 and delta == expected_delta
    )
    return result


async def verify(output):
    original = Settings()
    assert original.model_configured and original.test_database_url is not None
    validate_test_target(original.test_database_url, original.database_url)
    prefix = "memory532-real-" + uuid4().hex
    user = prefix + "-a"
    settings = original.model_copy(
        update={
            "database_url": original.test_database_url,
            "demo_user_ids": (user,),
            "app_env": "test",
        }
    )
    report = {
        "probe_id": prefix,
        "chat": {
            "host": urlsplit(settings.model_base_url or "https://api.openai.com").hostname,
            "model": settings.model_name,
        },
        "embedding_enabled": settings.embedding_enabled,
        "configuration": (
            "Original model/provider/flags/budgets retained; "
            "only test database and UUID identity isolation."
        ),
        "cases": [],
    }

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")

    save()
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert app.state.agent_service.is_ready and app.state.store_status == "ready"
        report["resources"] = {
            "store": app.state.store_status,
            "embedding": app.state.embedding_status,
            "knowledge_ready": app.state.knowledge_retriever is not None,
        }
        pool = app.state.pool
        before = await database_snapshot(pool)
        report["protected_before"] = fingerprints(before)
        saver = AsyncPostgresSaver(app.state.checkpoint_pool, serde=checkpoint_serializer())
        conversations, threads = [], []

        async def chat(name, text, expected):
            conversation = prefix + "-" + name
            conversations.append(conversation)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=180
            ) as client:
                response = await client.post(
                    "/agent/chat",
                    json={"user_id": user, "conversation_id": conversation, "message": text},
                )
            assert response.status_code == 200
            binding = await app.state.sessions.get(user_id=user, conversation_id=conversation)
            thread = str(binding.thread_id)
            threads.append(thread)
            saved = await app.state.agent_runtime._graph.aget_state(
                {"configurable": {"thread_id": thread}}
            )
            state = saved.values
            result = state.get("specialist_result")
            item = {
                "name": name,
                "status": str(state["task_status"]),
                "task_id": state["task_id"],
                "run_id": state["run_id"],
                "thread_id": thread,
                "task_type": result.task_type.value if result else None,
                "summary": result.summary if result else None,
                "facts": result.facts if result else None,
                "model_usage": state["model_call_usage"],
                "run_usage": state["run_usage"],
                "sources": [s.model_dump(mode="json") for s in result.sources] if result else [],
                "public_data": [
                    json.loads(line[6:])
                    for line in response.text.splitlines()
                    if line.startswith("data: ")
                ],
            }
            report["cases"].append(item)
            save()
            assert item["status"] == "completed", "Real model did not complete command"
            assert item["task_type"] == "memory_manage" and not item["sources"]
            assert item["run_usage"]["tool_calls"] == expected
            print(name, item["status"], flush=True)
            return result

        try:
            saved = await chat("save-en", "请记住：回答语言=英语", 2)
            assert saved.facts["memory_result"]["status"] == "applied"
            assert saved.facts["memory_result"]["preferences"] == {"answer_language": "en"}
            viewed = await chat("read-en", "请查看偏好记忆", 1)
            assert viewed.facts["preferences"] == {"answer_language": "en"}
            assert viewed.facts["revision"] == 1
            # Never enable a disabled embedding resource or bypass its readiness gate.
            report["english_preference_real_rag"] = {
                "status": "not_verified_configuration_blocked"
                if not settings.embedding_enabled
                else "not_executed",
                "reason": (
                    "Existing embedding_enabled=False; "
                    "explicit no configuration override instruction retained."
                )
                if not settings.embedding_enabled
                else "This limited command probe does not run a separate RAG corpus.",
            }
            await chat("delete-en", "请删除我的回答语言偏好", 2)
            empty = await chat("read-empty", "请查看偏好记忆", 1)
            assert empty.facts["preferences"] == {} and empty.facts["revision"] == 2
            report["commands_completed"] = True
        finally:
            await app.state.agent_runtime.shutdown()
            for conversation in conversations:
                binding = await app.state.sessions.get(user_id=user, conversation_id=conversation)
                if binding and str(binding.thread_id) not in threads:
                    threads.append(str(binding.thread_id))
            for thread in threads:
                await saver.adelete_thread(thread)
            async with pool.connection() as conn:
                await conn.execute(
                    "DELETE FROM sessions WHERE user_id=%s AND conversation_id=ANY(%s)",
                    (user, conversations),
                )
            await app.state.memory_store.abatch(
                [PutOp(preference_namespace(user), "profile", None)]
            )
            after = await database_snapshot(pool)
            report["protected_after"] = fingerprints(after)
            report["protected_unchanged"] = before == after
            report["exact_cleanup"] = {
                "user": user,
                "conversations": conversations,
                "threads": threads,
                "namespace": list(preference_namespace(user)),
                "key": "profile",
            }
            save()
            assert before == after, "Protected public rows/columns changed"
    print("Exact cleanup and complete public rows/columns protection passed", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh evidence path")
    run_async(verify(args.output))


if __name__ == "__main__":
    main()
