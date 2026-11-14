"""Limited real English-preference + Qwen/Chat/PG probe for Task 5.3.2.

Explicitly enables the approved local embedding only in test Settings. Existing
evidence, .env, provider/model and all limits remain unchanged.
"""

import argparse
import json
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp

from app.core.config import Settings
from app.infrastructure.checkpoint import checkpoint_serializer
from app.infrastructure.postgres import validate_test_target
from app.knowledge.chunking import prepare_document
from app.knowledge.models import ManifestEntry
from app.main import create_app
from app.memory.manager import preference_namespace
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints


async def verify(output):
    original = Settings()
    assert original.model_configured and original.test_database_url is not None
    validate_test_target(original.test_database_url, original.database_url)
    prefix = "memory532-rag-" + uuid4().hex
    user, document_id = prefix + "-user", prefix + "-document"
    settings = original.model_copy(
        update={
            "database_url": original.test_database_url,
            "app_env": "test",
            "demo_user_ids": (user,),
            "embedding_enabled": True,
        }
    )
    report = {
        "probe_id": prefix,
        "chat": {
            "model": settings.model_name,
            "host": urlsplit(settings.model_base_url or "https://api.openai.com").hostname,
        },
        "configuration": (
            "Authorized test-local embedding_enabled=True; original Qwen CPU path, "
            "provider, model and limits retained; .env unchanged."
        ),
        "original_embedding_enabled": original.embedding_enabled,
        "embedding_model_path": str(settings.embedding_model_path),
        "embedding_cpu_threads": settings.embedding_cpu_threads,
        "embedding_dtype": settings.embedding_dtype,
        "limits": {
            "run_seconds": settings.run_timeout_seconds,
            "tool_calls": settings.run_max_tool_calls,
            "embedding_seconds": settings.embedding_timeout_seconds,
        },
        "cases": [],
    }

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")

    save()
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert app.state.store_status == "ready"
        assert app.state.embedding_status == "ready" and app.state.knowledge_retriever is not None
        pool, retriever = app.state.pool, app.state.knowledge_retriever
        saver = AsyncPostgresSaver(app.state.checkpoint_pool, serde=checkpoint_serializer())
        before = await database_snapshot(pool)
        report["protected_before"] = fingerprints(before)
        report["profile"] = json.loads(retriever.profile)
        async with pool.connection() as conn:
            report["database"] = list(
                await (
                    await conn.execute(
                        "SELECT current_database(),current_user,current_setting('server_version'),"
                        "(SELECT extversion FROM pg_extension WHERE extname='vector')"
                    )
                ).fetchone()
            )
        conversations, threads = [], []
        root = Path(tempfile.mkdtemp(prefix=prefix))
        source = root / "approval.md"

        async def chat(name, message):
            conversation = prefix + "-" + name
            conversations.append(conversation)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=180
            ) as client:
                response = await client.post(
                    "/agent/chat",
                    json={"user_id": user, "conversation_id": conversation, "message": message},
                )
            assert response.status_code == 200
            binding = await app.state.sessions.get(user_id=user, conversation_id=conversation)
            thread = str(binding.thread_id)
            threads.append(thread)
            snapshot = await app.state.agent_runtime._graph.aget_state(
                {"configurable": {"thread_id": thread}}
            )
            state = snapshot.values
            result = state.get("specialist_result")
            item = {
                "name": name,
                "question": message,
                "task_id": state["task_id"],
                "run_id": state["run_id"],
                "thread_id": thread,
                "status": str(state["task_status"]),
                "result": result.model_dump(mode="json") if result else None,
                "run_usage": state["run_usage"],
                "model_usage": state["model_call_usage"],
                "public_data": [
                    json.loads(line[6:])
                    for line in response.text.splitlines()
                    if line.startswith("data: ")
                ],
            }
            report["cases"].append(item)
            save()
            assert item["status"] == "completed", "Actual request did not complete"
            print(name, item["status"], flush=True)
            return state, item

        try:
            source.write_text(
                "# Demo银帆演示指南\n\n"
                "银帆演示指南规定：普通聊天不能批准模拟退款。"
                "模拟退款审批必须通过独立的本地审批入口提交。"
                "审批决定由服务端固定演示操作者记录，聊天中的同意不构成批准。\n",
                "utf-8",
            )
            entry = ManifestEntry(
                document_id=document_id,
                filename=source.name,
                source_title="Demo银帆演示指南",
                domain="platform_help",
                public_source_key="memory532-approval",
            )
            doc = prepare_document(root, entry, retriever.profile)
            vectors = await retriever.embeddings.aembed_documents(
                [c.embedding_text for c in doc.chunks]
            )
            assert all(len(v) == 1024 for v in vectors)
            await retriever.repository.replace(doc, vectors)
            report["corpus"] = {
                "document_id": document_id,
                "version": doc.document_version,
                "chunk_ids": [c.chunk_id for c in doc.chunks],
                "text": source.read_text("utf-8"),
                "vector_dimensions": 1024,
            }
            print("Unique corpus embedded and committed", flush=True)
            saved, _ = await chat("save-en", "请记住：回答语言=英语")
            mutation = saved["specialist_result"].facts["memory_result"]
            assert mutation["status"] == "applied" and mutation["preferences"] == {
                "answer_language": "en"
            }
            assert saved["run_usage"]["tool_calls"] == 2
            assert (await app.state.memory_manager.snapshot(user_id=user)).preferences == {
                "answer_language": "en"
            }
            answered, item = await chat(
                "knowledge",
                "根据银帆演示指南，普通聊天能批准模拟退款吗？审批应该通过什么入口提交？",
            )
            result = answered["specialist_result"]
            assert (
                result.task_type.value == "knowledge_qa"
                and result.approved_answer
                and result.sources
            )
            assert answered["run_usage"]["tool_calls"] == 3
            assert answered["model_call_usage"]["model_attempts"] == 4
            assert {s.document_id for s in result.sources} == {document_id}
            assert all(
                s.document_version == doc.document_version
                and s.chunk_id in report["corpus"]["chunk_ids"]
                for s in result.sources
            )
            private = []
            async for checkpoint in saver.alist({"configurable": {"thread_id": item["thread_id"]}}):
                values = checkpoint.checkpoint["channel_values"]
                if values.get("validated_sources") and values.get("result"):
                    private.append(values)
            assert private
            child = private[0]
            assert child["memory_context"]["preferences"] == {"answer_language": "en"}
            records = {r["call"]["name"]: r for r in child["call_records"].values()}
            assert set(records) == {
                "read_preferences",
                "search_knowledge",
                "validate_knowledge_sources",
            }
            assert all(
                r["result"]["status"] == "success" and r["result"]["attempts"] == 1
                for r in records.values()
            )
            assert records["validate_knowledge_sources"]["result"]["data"]["valid"] is True
            assert child["validated_sources"] == [s.model_dump(mode="json") for s in result.sources]
            answer = result.approved_answer
            assert len(re.findall(r"[A-Za-z]", answer)) > 40
            assert all(word in answer.lower() for word in ("chat", "approval", "local"))
            item["records"] = [
                {
                    "tool": name,
                    "origin": r["origin"],
                    "node_name": r["node_name"],
                    "result": r["result"],
                }
                for name, r in records.items()
            ]
            item["memory_context"] = child["memory_context"]
            item["retrieval"] = {
                key: child["retrieval_observation"][key]
                for key in (
                    "embedding_request_attempts",
                    "candidate_count",
                    "context_tokens",
                    "elapsed_ms",
                )
            }
            report["english_preference_real_rag"] = (
                "PASS_real_output_pending_implementer_semantic_review"
            )
            save()
            print(
                "English answer and server-verified sources; three governed tool attempts",
                flush=True,
            )
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
            await retriever.repository.remove(document_id)
            if source.exists():
                source.unlink()
            root.rmdir()
            after = await database_snapshot(pool)
            report["protected_after"] = fingerprints(after)
            report["protected_unchanged"] = before == after
            report["exact_cleanup"] = {
                "user": user,
                "namespace": list(preference_namespace(user)),
                "key": "profile",
                "document_id": document_id,
                "conversations": conversations,
                "threads": threads,
                "temporary_source_removed": True,
            }
            save()
            assert before == after, "Protected public rows or columns changed"
    print("Qwen drained; exact cleanup and all public rows/columns preserved", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh evidence path")
    run_async(verify(args.output))


if __name__ == "__main__":
    main()
