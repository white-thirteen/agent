"""Opt-in isolated PostgreSQL test; never targets the project's normal test DB."""

import asyncio
import os
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import AsyncConnectionPool

from app.knowledge.chunking import prepare_document
from app.knowledge.models import KnowledgeError, ManifestEntry
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.sparse import activate, backfill, check_sparse_ready, lock_publication
from scripts import run_async


def test_sparse_publication_and_backfill(tmp_path):
    dsn = os.environ.get("AGENT_SPARSE_TASK112_DATABASE_URL")
    if not dsn:
        pytest.skip("Explicit isolated Task 1.1.2 database required")
    target = conninfo_to_dict(dsn)
    assert target.get("dbname") == "agent_sparse_task112_test"
    assert target.get("user") == "agent_sparse_task112"

    async def scenario():
        entry = ManifestEntry(
            document_id="task112",
            filename="doc.md",
            source_title="标题",
            domain="platform_help",
            public_source_key="task112",
        )
        path = tmp_path / "doc.md"
        path.write_text("# 章节\n\n退款银行卡 oldpolicy", encoding="utf-8")
        original = prepare_document(tmp_path, entry, "controlled")
        chunk = original.chunks[0]
        vector = [1.0] + [0.0] * 1023

        async def hits(conn, term):
            return await (
                await conn.execute(
                    "SELECT chunk_id FROM knowledge_chunks WHERE "
                    "search_text <@> to_bm25query(%s,%s) < 0 "
                    "ORDER BY search_text <@> to_bm25query(%s,%s)",
                    (term, "knowledge_chunks_bm25_idx", term, "knowledge_chunks_bm25_idx"),
                )
            ).fetchall()

        pool = AsyncConnectionPool(conninfo=dsn, open=False, min_size=1, max_size=3)
        await pool.open(wait=True)
        created = False
        try:
            async with pool.connection() as conn, conn.transaction():
                assert await (
                    await conn.execute(
                        "SELECT current_database(),current_user,"
                        "shobj_description(oid,'pg_database') FROM pg_database "
                        "WHERE datname=current_database()"
                    )
                ).fetchone() == (
                    "agent_sparse_task112_test",
                    "agent_sparse_task112",
                    "codex-task112-7c41",
                )
                assert await (
                    await conn.execute(
                        "SELECT to_regclass('public.knowledge_documents'), "
                        "to_regclass('public.knowledge_chunks'), "
                        "to_regclass('public.knowledge_index_state')"
                    )
                ).fetchone() == (None, None, None)
                await conn.execute(Path("migrations/006_knowledge_vectors.sql").read_text("utf-8"))
                await conn.execute(
                    "INSERT INTO knowledge_documents VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())",
                    (
                        entry.document_id,
                        original.document_version,
                        original.content_hash,
                        entry.domain,
                        entry.source_title,
                        entry.public_source_key,
                        "controlled",
                        1,
                    ),
                )
                await conn.execute(
                    "INSERT INTO knowledge_chunks VALUES "
                    "(%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s::vector)",
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.document_version,
                        chunk.ordinal,
                        chunk.section,
                        chunk.line_start,
                        chunk.line_end,
                        chunk.content,
                        chunk.content_hash,
                        chunk.token_count,
                        str(vector),
                    ),
                )
                before = await (
                    await conn.execute(
                        "SELECT chunk_id,document_id,document_version,content_hash,embedding::text "
                        "FROM knowledge_chunks"
                    )
                ).fetchall()
                await conn.execute(Path("migrations/007_knowledge_sparse.sql").read_text("utf-8"))
            created = True
            repository = KnowledgeRepository(pool)
            with pytest.raises(KnowledgeError, match="sparse_input_incomplete"):
                await activate(pool)
            assert await backfill(pool) == 1
            assert await backfill(pool) == 0
            mark = await activate(pool)
            assert await activate(pool) == mark
            async with pool.connection() as conn, conn.transaction():
                assert await check_sparse_ready(conn) == mark
                assert (
                    await (
                        await conn.execute(
                            "SELECT chunk_id,document_id,document_version,content_hash,"
                            "embedding::text FROM knowledge_chunks"
                        )
                    ).fetchall()
                    == before
                )
                assert await (
                    await conn.execute(
                        "SELECT chunk_id FROM knowledge_chunks WHERE "
                        "search_text <@> to_bm25query(%s,%s) < 0 "
                        "ORDER BY search_text <@> to_bm25query(%s,%s)",
                        ("退款", "knowledge_chunks_bm25_idx", "退款", "knowledge_chunks_bm25_idx"),
                    )
                ).fetchall() == [(original.chunks[0].chunk_id,)]
                await conn.execute(
                    "ALTER INDEX knowledge_chunks_bm25_idx RENAME TO task112_hidden_idx"
                )
                with pytest.raises(KnowledgeError, match="sparse_index_unavailable"):
                    await check_sparse_ready(conn)
                await conn.execute(
                    "CREATE INDEX knowledge_chunks_bm25_idx ON knowledge_chunks "
                    "USING bm25 (search_text) WITH (text_config='public.chinese') "
                    "WHERE ordinal=0"
                )
                with pytest.raises(KnowledgeError, match="sparse_index_unavailable"):
                    await check_sparse_ready(conn)
                await conn.execute("DROP INDEX knowledge_chunks_bm25_idx")
                await conn.execute(
                    "ALTER INDEX task112_hidden_idx RENAME TO knowledge_chunks_bm25_idx"
                )
            path.write_text("# 章节\n\n新条款 newpolicy\n\n第二段", encoding="utf-8")
            updated = prepare_document(tmp_path, entry, "controlled")
            bad = updated.model_copy(
                update={
                    "chunks": (
                        updated.chunks[0],
                        updated.chunks[1].model_copy(
                            update={"chunk_id": updated.chunks[0].chunk_id}
                        ),
                    )
                }
            )
            with pytest.raises(psycopg.errors.UniqueViolation):
                await repository.replace(bad, [vector, vector])
            assert await repository.is_complete(original)
            async with pool.connection() as conn, conn.transaction():
                assert await check_sparse_ready(conn) == mark
            async with pool.connection() as conn, conn.transaction():
                await lock_publication(conn)
                pending = asyncio.create_task(repository.replace(updated, [vector, vector]))
                done, _ = await asyncio.wait({pending}, timeout=0.2)
                assert not done
            assert await pending
            async with pool.connection() as conn, conn.transaction():
                assert await check_sparse_ready(conn) == mark + 1
                assert await hits(conn, "oldpolicy") == []
                assert await hits(conn, "newpolicy") == [(updated.chunks[0].chunk_id,)]
            await repository.remove(entry.document_id)
            async with pool.connection() as conn, conn.transaction():
                assert await check_sparse_ready(conn) == mark + 2
                assert await hits(conn, "newpolicy") == []
                assert (
                    await (await conn.execute("SELECT count(*) FROM knowledge_chunks")).fetchone()
                )[0] == 0
        finally:
            if created:
                async with pool.connection() as conn, conn.transaction():
                    await conn.execute("DROP TABLE knowledge_index_state")
                    await conn.execute("DROP TABLE knowledge_chunks")
                    await conn.execute("DROP TABLE knowledge_documents")
            await pool.close()

    run_async(scenario())
