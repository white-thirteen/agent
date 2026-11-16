"""Task6.3.1 isolated interactive demo fixtures; real configured Chat/Qwen/PG.

prepare -> uvicorn server_app -> audit/cleanup. Manifest has no credentials;
the complete protected snapshot stays in the local temporary working directory.
Never run against production or seed fixed orders.
"""

import argparse
import json
import logging
import os
import pickle
import tempfile
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp

from app.core.config import Settings
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.postgres import open_pool, validate_test_target
from app.infrastructure.store import store_resources
from app.knowledge.chunking import prepare_document
from app.knowledge.models import ManifestEntry
from app.main import create_app
from app.memory.manager import preference_namespace
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints


def settings_for(data, *, embedding=True):
    original = Settings()
    validate_test_target(original.test_database_url, original.database_url)
    return original.model_copy(
        update={
            "app_env": "test",
            "database_url": original.test_database_url,
            "demo_user_ids": (data["user_a"], data["user_b"]),
            "embedding_enabled": embedding,
            "log_level": "CRITICAL",
        }
    )


def server_app():
    """Single-worker factory, same app topology/model/limits as the actual demo."""
    logging.disable(logging.CRITICAL)
    data = json.loads(Path(os.environ["AGENT_DEMO_MANIFEST"]).read_text("utf-8"))
    return create_app(settings_for(data))


async def prepare(folder):
    """Populate the directory newly acquired by this CLI invocation."""
    prefix = "demo631-" + uuid4().hex
    data = {
        "prefix": prefix,
        "user_a": prefix + "-a",
        "user_b": prefix + "-b",
        "order_ok": prefix + "-ok",
        "order_no": prefix + "-no",
        "document_id": prefix + "-guide",
    }
    path = folder / "manifest.json"
    path.write_text(json.dumps(data, indent=2), "utf-8")
    app = create_app(settings_for(data))
    async with app.router.lifespan_context(app):
        assert app.state.agent_service.is_ready
        assert app.state.embedding_status == "ready" and app.state.knowledge_retriever is not None
        assert app.state.store_status == "ready"
        before = await database_snapshot(app.state.pool)
        (folder / "protected.pickle").write_bytes(pickle.dumps(before))
        (folder / "protected.json").write_text(json.dumps(fingerprints(before), indent=2), "utf-8")
        async with app.state.pool.connection() as conn:
            for order in (data["order_ok"], data["order_no"]):
                await conn.execute(
                    "INSERT INTO demo_orders(order_id,owner_id,amount,currency,"
                    "payment_status,is_refunded,created_at) "
                    "VALUES(%s,%s,12.34,'CNY','paid',false,now())",
                    (order, data["user_a"]),
                )
        source = folder / "guide.md"
        source.write_text(
            "# 银帆演示指南\n\n普通聊天不能批准模拟退款。"
            "模拟退款审批必须通过独立的本地审批入口提交。"
            "审批决定由服务端固定演示操作者记录，聊天中的同意不构成批准。\n",
            "utf-8",
        )
        retriever = app.state.knowledge_retriever
        entry = ManifestEntry(
            document_id=data["document_id"],
            filename=source.name,
            source_title="银帆演示指南",
            domain="platform_help",
            public_source_key="demo631-guide",
        )
        doc = prepare_document(folder, entry, retriever.profile)
        vectors = await retriever.embeddings.aembed_documents(
            [c.embedding_text for c in doc.chunks]
        )
        assert all(len(v) == 1024 for v in vectors)
        await retriever.repository.replace(doc, vectors)
        data["corpus"] = {
            "version": doc.document_version,
            "chunks": [c.chunk_id for c in doc.chunks],
            "dimensions": 1024,
        }
        path.write_text(json.dumps(data, indent=2), "utf-8")
    print(str(path), flush=True)


async def inspect(folder, cleanup=False):
    data = json.loads((folder / "manifest.json").read_text("utf-8"))
    settings = settings_for(data, embedding=False)
    pool = await open_pool(settings)
    try:
        await database_snapshot(pool)  # identity, checksums and full column definitions
        async with pool.connection() as conn:
            sessions = await (
                await conn.execute(
                    "SELECT user_id,conversation_id,thread_id FROM sessions "
                    "WHERE user_id=ANY(%s) ORDER BY conversation_id",
                    ([data["user_a"], data["user_b"]],),
                )
            ).fetchall()
            refunds = await (
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
        result = {"sessions": sessions, "refunds": refunds, "profiles": {}}
        async with store_resources(settings) as resources:
            store = resources
            for user in (data["user_a"], data["user_b"]):
                item = await store.aget(preference_namespace(user), "profile")
                result["profiles"][user] = item.value if item else None
                if cleanup:
                    await store.abatch([PutOp(preference_namespace(user), "profile", None)])
        if cleanup:
            checkpoint_pool = await open_checkpoint_pool(settings)
            try:
                saver = AsyncPostgresSaver(checkpoint_pool, serde=checkpoint_serializer())
                for row in sessions:
                    await saver.adelete_thread(str(row[2]))
            finally:
                await checkpoint_pool.close()
            async with pool.connection() as conn:
                await conn.execute(
                    "DELETE FROM approvals WHERE subject_snapshot->>'user_id'=%s", (data["user_a"],)
                )
                await conn.execute(
                    "DELETE FROM refund_requests WHERE user_id=%s", (data["user_a"],)
                )
                await conn.execute(
                    "DELETE FROM demo_orders WHERE owner_id=%s AND order_id=ANY(%s)",
                    (data["user_a"], [data["order_ok"], data["order_no"]]),
                )
                await conn.execute(
                    "DELETE FROM sessions WHERE user_id=ANY(%s)",
                    ([data["user_a"], data["user_b"]],),
                )
                await conn.execute(
                    "DELETE FROM knowledge_chunks WHERE document_id=%s", (data["document_id"],)
                )
                await conn.execute(
                    "DELETE FROM knowledge_documents WHERE document_id=%s", (data["document_id"],)
                )
            after = await database_snapshot(pool)
            # Only load our own locally generated snapshot, never an imported pickle.
            before = pickle.loads((folder / "protected.pickle").read_bytes())
            result["protected_after"] = fingerprints(after)
            result["protected_unchanged"] = before == after
            assert before == after, "Protected database rows or columns changed"
        return result
    finally:
        await pool.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "audit", "cleanup"))
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    folder = args.folder or Path(tempfile.gettempdir()) / ("demo631-" + uuid4().hex)
    if args.output:
        assert not args.output.exists(), "Use a fresh evidence path"
    if args.action == "prepare":
        # Acquire ownership before entering cleanup scope. An existing directory
        # belongs to an earlier invocation, including its manifest and baseline.
        folder.mkdir(parents=True, exist_ok=False)
        try:
            run_async(prepare(folder))
        except BaseException:
            # The snapshot precedes every fixture write; keep failed evidence and
            # remove only manifest-owned rows, including a partially published corpus.
            if (folder / "protected.pickle").exists():
                result = run_async(inspect(folder, cleanup=True))
                (folder / "prepare-failure-cleanup.json").write_text(
                    json.dumps(result, default=str, indent=2), "utf-8"
                )
            raise
    else:
        result = run_async(inspect(folder, args.action == "cleanup"))
        if args.output:
            args.output.write_text(
                json.dumps(result, default=str, ensure_ascii=False, indent=2), "utf-8"
            )
        else:
            print(json.dumps(result, default=str, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
