"""Real local Qwen/BGE plus isolated hybrid retrieval, with exact corpus cleanup."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from app.knowledge.chunking import read_manifest
from app.knowledge.ingest import KnowledgeIngestor
from app.knowledge.models import SearchQuery
from app.main import create_app
from app.runtime.context import DemoIdentity
from scripts import run_async
from scripts.verify_05_memory_manage import compare_publication_snapshots, database_snapshot

OUTPUT = Path("docs/v2/v2-02/evidence/v2-02-task232-real-hybrid-r2.json")


async def main():
    assert not OUTPUT.exists()
    original = Settings()
    validate_test_target(original.test_database_url, original.database_url)
    user = "ctx232-hybrid-" + uuid4().hex
    root, manifest = Path("data/knowledge"), Path("data/knowledge/manifest.json")
    entries = read_manifest(root, manifest)
    ids = [entry.document_id for entry in entries]
    report = {"cases": [], "cleanup": False}

    def save():
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), "utf-8")

    with tempfile.TemporaryDirectory(prefix="ctx232-hybrid-") as archive:
        settings = original.model_copy(
            update={
                "database_url": original.test_database_url,
                "app_env": "test",
                "demo_user_ids": (user,),
                "embedding_enabled": True,
                "knowledge_retrieval_mode": "hybrid",
                "context_model_window_tokens": 16384,
                "context_model_output_tokens": 512,
                "context_summary_output_tokens": 256,
                "context_archive_read_tokens": 4096,
                "context_archive_root": Path(archive),
            }
        )
        guard_pool = await open_pool(settings)
        before = await database_snapshot(guard_pool)
        async with guard_pool.connection() as conn:
            occupied = await (
                await conn.execute(
                    "SELECT document_id FROM knowledge_documents WHERE document_id=ANY(%s)", (ids,)
                )
            ).fetchall()
        assert not occupied, "Fixture document IDs already exist; do not replace them"
        app = create_app(settings)
        try:
            async with app.router.lifespan_context(app):
                retriever = app.state.knowledge_retriever
                assert retriever and app.state.embedding_status == "ready"
                try:
                    ingestor = KnowledgeIngestor(
                        retriever.repository,
                        retriever.candidate_retriever.embeddings,
                        retriever.profile,
                        settings.embedding_batch_size,
                    )
                    report["import"] = await ingestor.ingest(root, manifest)
                    save()
                    identity = DemoIdentity(user, frozenset({"knowledge:read"}))
                    for query in (
                        "模拟退款会扣真实银行卡的钱吗？",
                        "If the stream disconnects, does the accepted task continue?",
                    ):
                        result = await retriever.search(
                            SearchQuery(query=query, top_k=3), identity=identity
                        )
                        source_check = await retriever.validate_evidence(
                            result.evidence, identity=identity
                        )
                        report["cases"].append(
                            {
                                "query": query,
                                "result": result.model_dump(mode="json"),
                                "source_check": source_check,
                            }
                        )
                        save()
                finally:
                    async with guard_pool.connection() as conn:
                        present = await (
                            await conn.execute(
                                "SELECT document_id FROM knowledge_documents "
                                "WHERE document_id=ANY(%s)",
                                (ids,),
                            )
                        ).fetchall()
                    for (document_id,) in present:
                        await retriever.repository.remove(document_id)
                    after = await database_snapshot(guard_pool)
                    report["cleanup"] = compare_publication_snapshots(
                        before, after, expected_delta=2 * len(present)
                    )
                    report["removed_ids"] = [row[0] for row in present]
                    save()
                    assert report["cleanup"]["protected_unchanged"]
        finally:
            await guard_pool.close()


if __name__ == "__main__":
    run_async(main())
