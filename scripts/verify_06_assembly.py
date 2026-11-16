"""Task6.1.1: one public HTTP app, real Chat/Qwen/PG, UUID fixtures only.

Explicit verification command; never invoked by default pytest. No deployment or
fixed seed changes. All existing public rows and column definitions are protected.
"""

import argparse
import json
import re
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.checkpoint import checkpoint_serializer
from app.infrastructure.postgres import open_pool, validate_test_target
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
    prefix = "assembly611-" + uuid4().hex
    user, document_id = prefix + "-user", prefix + "-document"
    order_id = prefix + "-order"
    settings = original.model_copy(
        update={
            "database_url": SecretStr(
                make_conninfo(
                    original.test_database_url.get_secret_value(), application_name=prefix
                )
            ),
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

        async def chat(name, message, expected="completed"):
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
            item["snapshot_task_status"] = item["status"]
            item["status"] = item["public_data"][-1]["task_status"]
            report["cases"].append(item)
            save()
            assert item["status"] == expected, "Actual request did not reach expected state"
            print(name, item["status"], flush=True)
            return state, item

        try:
            async with pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO demo_orders(order_id,owner_id,amount,currency,payment_status,"
                    "is_refunded,created_at) VALUES (%s,%s,12.34,'CNY','paid',false,now())",
                    (order_id, user),
                )
                report["framework_migrations"] = {}
                for table in ("checkpoint_migrations", "store_migrations"):
                    from psycopg import sql

                    rows = await (
                        await conn.execute(
                            sql.SQL("SELECT v FROM {} ORDER BY v").format(sql.Identifier(table))
                        )
                    ).fetchall()
                    report["framework_migrations"][table] = [r[0] for r in rows]
                assert report["framework_migrations"] == {
                    "checkpoint_migrations": list(range(10)),
                    "store_migrations": list(range(4)),
                }
            graph_identity = id(app.state.agent_runtime._graph)
            gateway_identity = id(app.state.model_gateway)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                report["health"] = (await client.get("/health")).json()
            assert report["health"]["agent_ready"] and report["health"]["knowledge_ready"]
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
            english_checks = []
            # Fixed plan, once each; Chinese question text alone is not a language override.
            knowledge_questions = (
                (
                    "knowledge-chat",
                    "根据银帆演示指南，普通聊天能批准模拟退款吗？审批应该通过什么入口提交？",
                ),
                (
                    "knowledge-consent",
                    "根据银帆演示指南，聊天中的同意能代替批准吗？模拟退款审批从哪里提交，由谁记录？",
                ),
            )
            report["planned_knowledge_questions"] = knowledge_questions
            save()
            for name, question in knowledge_questions:
                answered, item = await chat(name, question)
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
                async for checkpoint in saver.alist(
                    {"configurable": {"thread_id": item["thread_id"]}}
                ):
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
                assert child["validated_sources"] == [
                    s.model_dump(mode="json") for s in result.sources
                ]
                answer = result.approved_answer
                english_output = len(re.findall(r"[A-Za-z]", answer)) > 40 and all(
                    word in answer.lower() for word in ("chat", "approval", "local")
                )
                english_checks.append(english_output)
                item["language_source"] = "verified stored answer_language=en; no explicit override"
                item["english_output_verified"] = english_output
                report["english_output_verified"] = all(english_checks)
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
                    "PASS_real_outputs"
                    if all(english_checks)
                    else "FAILED_model_answer_not_English"
                )
                save()
                print(
                    "Server-verified sources; three governed tool attempts",
                    flush=True,
                )
            ordered, order_case = await chat("order", f"查询单个模拟订单，订单号={order_id}")
            facts = ordered["specialist_result"].facts
            assert facts["simulated"] and facts["order"]["order_id"] == order_id
            assert facts["order"]["amount"] == "12.34" and not facts["order"]["is_refunded"]
            assert ordered["run_usage"]["tool_calls"] == 2
            pending, refund_case = await chat(
                "refund", f"请申请模拟退款，订单号={order_id}", expected="waiting_approval"
            )
            pause = next(
                d for d in refund_case["public_data"] if d.get("reason") == "waiting_approval"
            )
            approval_id = pause["approval_id"]
            approval = await app.state.approval_service.get(approval_id)
            assert approval["decision"] == "PENDING" and approval["interrupt_id"]
            assert approval["checkpoint_ns"] and approval["checkpoint_id"]
            operation = approval["subject_snapshot"]["operation_id"]
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
                base_url="http://test",
                timeout=180,
            ) as client:
                rejected = await client.post(
                    f"/admin/approvals/{approval_id}/decision",
                    json={"decision": "REJECTED", "subject_digest": approval["subject_digest"]},
                )
                assert rejected.status_code == 200
                resumed = await client.post(f"/admin/approvals/{approval_id}/resume", json={})
                assert resumed.status_code == 202
                resumed_run = resumed.json()["run_id"]
                await app.state.agent_runtime._records[resumed_run].task
            approval = await app.state.approval_service.get(approval_id)
            assert approval["decision"] == "REJECTED"
            assert approval["approver_id"] == "local-demo-approval"
            fact = await app.state.refund_service.get_operation(
                user_id=user, operation_id=operation
            )
            assert fact["status"] == "REJECTED" and fact["execution_result"] is None
            async with pool.connection() as conn:
                row = await (
                    await conn.execute(
                        "SELECT amount,is_refunded FROM demo_orders "
                        "WHERE order_id=%s AND owner_id=%s",
                        (order_id, user),
                    )
                ).fetchone()
            assert str(row[0]) == "12.34" and row[1] is False
            record = app.state.agent_runtime._records[resumed_run]
            assert str(record.task_status) == "rejected"
            report["refund"] = {
                "simulated": True,
                "approval_id": approval_id,
                "operation_id": operation,
                "interrupt_id": approval["interrupt_id"],
                "checkpoint_ns": approval["checkpoint_ns"],
                "decision": approval["decision"],
                "actor": approval["approver_id"],
                "business_status": fact["status"],
                "is_refunded": row[1],
                "resumed_task_status": str(record.task_status),
            }
            for case in (order_case, refund_case):
                children = []
                async for checkpoint in saver.alist(
                    {"configurable": {"thread_id": case["thread_id"]}}
                ):
                    values = checkpoint.checkpoint["channel_values"]
                    if values.get("request") and values.get("call_records"):
                        children.append(values)
                assert children
                case["child_run_usage"] = children[0]["run_usage"]
                case["child_model_usage"] = children[0]["model_call_usage"]
                case["tool_records"] = json.loads(
                    json.dumps(children[0]["call_records"], default=asdict)
                )
            assert id(app.state.agent_runtime._graph) == graph_identity
            assert id(app.state.model_gateway) == gateway_identity
            report["shared_application_resources"] = True
            report["assembly_scenarios_completed"] = True
            save()
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
                    "DELETE FROM approvals WHERE subject_snapshot->>'user_id'=%s", (user,)
                )
                await conn.execute("DELETE FROM refund_requests WHERE user_id=%s", (user,))
                await conn.execute(
                    "DELETE FROM demo_orders WHERE order_id=%s AND owner_id=%s", (order_id, user)
                )
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
                "order_id": order_id,
                "temporary_source_removed": True,
            }
            save()
            assert before == after, "Protected public rows or columns changed"
    probe_pool = await open_pool(
        original.model_copy(update={"database_url": original.test_database_url})
    )
    try:
        async with probe_pool.connection() as conn:
            count = (
                await (
                    await conn.execute(
                        "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s", (prefix,)
                    )
                ).fetchone()
            )[0]
        assert count == 0
        assert not any(t.name.startswith("qwen-embedding") for t in threading.enumerate())
        report["shutdown"] = {"owned_database_connections": count, "qwen_worker_threads": 0}
        save()
    finally:
        await probe_pool.close()
    print("Qwen drained; exact cleanup and all public rows/columns preserved", flush=True)
    report["probe_result"] = (
        "PASS" if report["english_output_verified"] else "FAILED_english_preference_output"
    )
    save()
    assert report["english_output_verified"], "Real model did not follow stored English preference"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh evidence path")
    run_async(verify(args.output))


if __name__ == "__main__":
    main()
