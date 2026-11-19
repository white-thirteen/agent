"""Isolated real PostgreSQL hybrid retrieval; opt in with the dedicated database."""

import os
from contextlib import AsyncExitStack
from pathlib import Path
from time import monotonic

import pytest
from psycopg.conninfo import conninfo_to_dict
from psycopg.pq import TransactionStatus
from psycopg_pool import AsyncConnectionPool

from app.knowledge.chunking import prepare_document
from app.knowledge.models import KnowledgeError, ManifestEntry, SearchQuery
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.retriever import HybridCandidateRetriever
from app.knowledge.sparse import activate
from app.runtime.context import DemoIdentity
from scripts import run_async


def test_hybrid_real_snapshot_filters_and_failure(tmp_path, monkeypatch):
    dsn = os.environ.get("AGENT_HYBRID_TASK121_DATABASE_URL")
    if not dsn:
        pytest.skip("Explicit isolated Task 1.2.1 database required")
    target = conninfo_to_dict(dsn)
    assert (target.get("dbname"), target.get("user")) == (
        "agent_hybrid_task121_test",
        "agent_hybrid_task121",
    )

    async def scenario():
        pool = AsyncConnectionPool(conninfo=dsn, open=False, min_size=1, max_size=3)
        await pool.open(wait=True)
        created = False
        vector = [1.0] + [0.0] * 1023

        class Embeddings:
            async def aembed_query(self, query):
                return vector

        identity = DemoIdentity(user_id="u", permission_scopes=frozenset({"knowledge:read"}))
        denied = DemoIdentity(user_id="u", permission_scopes=frozenset())
        repo = KnowledgeRepository(pool)
        retriever = HybridCandidateRetriever(repo, Embeddings(), "controlled")

        def doc(identifier, domain, text):
            path = tmp_path / (identifier + ".md")
            path.write_text("# 标题\n\n" + text, encoding="utf-8")
            return prepare_document(
                tmp_path,
                ManifestEntry(
                    document_id=identifier,
                    filename=path.name,
                    source_title="标题",
                    domain=domain,
                    public_source_key=identifier,
                ),
                "controlled",
            )

        try:
            async with pool.connection() as conn, conn.transaction():
                assert await (
                    await conn.execute(
                        "SELECT current_database(),current_user,"
                        "shobj_description(oid,'pg_database') FROM pg_database "
                        "WHERE datname=current_database()"
                    )
                ).fetchone() == (
                    "agent_hybrid_task121_test",
                    "agent_hybrid_task121",
                    "codex-task121-9db5",
                )
                assert await (
                    await conn.execute(
                        "SELECT to_regclass('public.knowledge_documents'),"
                        "to_regclass('public.knowledge_chunks'),"
                        "to_regclass('public.knowledge_index_state')"
                    )
                ).fetchone() == (None, None, None)
                await conn.execute(Path("migrations/006_knowledge_vectors.sql").read_text("utf-8"))
                await conn.execute(Path("migrations/007_knowledge_sparse.sql").read_text("utf-8"))
            created = True
            await activate(pool)
            query = SearchQuery(query="退款", domain="platform_help")
            assert (await retriever.search(query, identity=identity)).status == "empty"
            with pytest.raises(KnowledgeError, match="policy_denied"):
                await retriever.search(query, identity=denied)
            original = doc("old", "platform_help", "退款银行卡 oldpolicy")
            other = doc("other", "after_sales_help", "退款退款退款")
            await repo.replace(original, [vector] * len(original.chunks))
            await repo.replace(other, [vector] * len(other.chunks))
            # More than a route's Top10 in another domain must not crowd out the hit.
            for number in range(11):
                excluded = doc(f"excluded{number}", "after_sales_help", "退款退款退款")
                await repo.replace(excluded, [vector] * len(excluded.chunks))
            result = await retriever.search(query, identity=identity)
            assert len(result.candidates) == 1
            item = result.candidates[0]
            assert item.evidence.document_id == "old"
            assert item.scores.dense.rank == item.scores.sparse.rank == 1
            assert item.scores.sparse.score < 0 and item.scores.rrf_score == pytest.approx(2 / 61)
            no_match = await retriever.search(
                SearchQuery(query="unmatchedxyz", domain="platform_help"), identity=identity
            )
            assert no_match.candidates[0].scores.sparse is None
            import app.knowledge.repository as repository_module

            actual = repository_module.check_sparse_ready
            updated = doc("old", "platform_help", "新政策 newpolicy")

            async def concurrent(conn):
                mark = await actual(conn)
                await repo.replace(updated, [vector] * len(updated.chunks))
                return mark

            monkeypatch.setattr(repository_module, "check_sparse_ready", concurrent)
            snapshot = await retriever.search(query, identity=identity)
            assert snapshot.index_watermark == result.index_watermark
            assert snapshot.candidates[0].evidence.document_version == original.document_version
            monkeypatch.setattr(repository_module, "check_sparse_ready", actual)
            fresh = await retriever.search(query, identity=identity)
            assert fresh.index_watermark == snapshot.index_watermark + 1
            assert fresh.candidates[0].evidence.document_version == updated.document_version
            assert not (await repo.validate_evidence([snapshot.candidates[0].evidence]))["valid"]
            with pytest.raises(KnowledgeError, match="embedding_profile_mismatch"):
                await repo.hybrid_candidates(vector, "退款", "wrong", None)

            async def slow_readiness(conn):
                mark = await actual(conn)
                await conn.execute("SELECT pg_sleep(2.7)")
                await conn.execute("SELECT pg_sleep(2.7)")
                return mark

            monkeypatch.setattr(repository_module, "check_sparse_ready", slow_readiness)
            started = monotonic()
            with pytest.raises(KnowledgeError, match="retrieval_timeout"):
                await retriever.search(query, identity=identity)
            assert 4.5 <= monotonic() - started < 7
            monkeypatch.setattr(repository_module, "check_sparse_ready", actual)
            async with AsyncExitStack() as stack:
                for _ in range(3):
                    conn = await stack.enter_async_context(pool.connection())
                    assert conn.info.transaction_status == TransactionStatus.IDLE
                    assert await (await conn.execute("SELECT 1")).fetchone() == (1,)
            assert (await retriever.search(query, identity=identity)).status == "found"

            # Pool acquisition is part of the same budget and leaves the pool usable.
            async with AsyncExitStack() as stack:
                for _ in range(3):
                    await stack.enter_async_context(pool.connection())
                started = monotonic()
                with pytest.raises(KnowledgeError, match="retrieval_timeout"):
                    await retriever.search(query, identity=identity)
                assert 4.5 <= monotonic() - started < 7
            assert (await retriever.search(query, identity=identity)).status == "found"
            async with pool.connection() as conn, conn.transaction():
                await conn.execute("UPDATE knowledge_index_state SET ready=false")
            with pytest.raises(KnowledgeError, match="sparse_index_unavailable"):
                await retriever.search(query, identity=identity)
        finally:
            if created:
                async with pool.connection() as conn, conn.transaction():
                    await conn.execute("DROP TABLE knowledge_index_state")
                    await conn.execute("DROP TABLE knowledge_chunks")
                    await conn.execute("DROP TABLE knowledge_documents")
            await pool.close()

    run_async(scenario())
