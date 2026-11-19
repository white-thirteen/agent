"""Controlled sparse preparation; never initializes extensions or embeddings."""

from app.knowledge.models import KnowledgeError, SparseIndexProfile

INDEX_NAME = "knowledge_chunks_bm25_idx"
PUBLICATION_LOCK = "knowledge:index-publication"


def search_text(title: str, section: str | None, content: str) -> str:
    """The v1 sparse input preserves all source text and uses fixed separators."""
    return title + "\n" + (section or "") + "\n" + content


async def lock_publication(connection):
    # Always acquire this before a document advisory lock or the state row lock.
    await connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (PUBLICATION_LOCK,)
    )


async def backfill(pool) -> int:
    """Fill only derived input, without touching vectors or source identities."""
    async with pool.connection() as connection, connection.transaction():
        await lock_publication(connection)
        cursor = await connection.execute(
            "UPDATE knowledge_chunks c SET search_text=d.source_title || E'\\n' || "
            "coalesce(c.section,'') || E'\\n' || c.content FROM knowledge_documents d "
            "WHERE c.document_id=d.document_id AND c.document_version=d.document_version "
            "AND c.search_text IS DISTINCT FROM "
            "d.source_title || E'\\n' || coalesce(c.section,'') || E'\\n' || c.content"
        )
        if cursor.rowcount:
            await connection.execute("UPDATE knowledge_index_state SET ready=false WHERE singleton")
        return cursor.rowcount


async def _check_inputs(connection):
    row = await (
        await connection.execute(
            "SELECT EXISTS(SELECT 1 FROM knowledge_documents d WHERE d.chunk_count <> "
            "(SELECT count(*) FROM knowledge_chunks c WHERE c.document_id=d.document_id "
            "AND c.document_version=d.document_version)) OR EXISTS("
            "SELECT 1 FROM knowledge_chunks c JOIN knowledge_documents d "
            "ON c.document_id=d.document_id AND c.document_version=d.document_version "
            "WHERE c.search_text IS DISTINCT FROM "
            "d.source_title || E'\\n' || coalesce(c.section,'') || E'\\n' || c.content)"
        )
    ).fetchone()
    if row[0]:
        raise KnowledgeError("sparse_input_incomplete")


async def _check_environment(connection):
    versions = dict(
        await (
            await connection.execute(
                "SELECT extname,extversion FROM pg_extension "
                "WHERE extname IN ('vector','pg_textsearch','zhparser')"
            )
        ).fetchall()
    )
    server = (await (await connection.execute("SHOW server_version_num")).fetchone())[0]
    config = await (
        await connection.execute(
            "SELECT p.prsname, pn.nspname FROM pg_ts_config c "
            "JOIN pg_namespace n ON n.oid=c.cfgnamespace "
            "JOIN pg_ts_parser p ON p.oid=c.cfgparser "
            "JOIN pg_namespace pn ON pn.oid=p.prsnamespace "
            "WHERE n.nspname='public' AND c.cfgname='chinese'"
        )
    ).fetchone()
    mappings = await (
        await connection.execute(
            "SELECT tok.alias, dn.nspname, d.dictname FROM pg_ts_config c "
            "JOIN pg_namespace n ON n.oid=c.cfgnamespace "
            "JOIN pg_ts_config_map m ON m.mapcfg=c.oid "
            "JOIN pg_ts_dict d ON d.oid=m.mapdict "
            "JOIN pg_namespace dn ON dn.oid=d.dictnamespace "
            "JOIN LATERAL ts_token_type(c.cfgparser) tok ON tok.tokid=m.maptokentype "
            "WHERE n.nspname='public' AND c.cfgname='chinese' "
            "ORDER BY tok.alias"
        )
    ).fetchall()
    if (
        server != "170012"
        or versions != {"vector": "0.8.7", "pg_textsearch": "1.5.1", "zhparser": "2.4"}
        or config != ("zhparser", "public")
        or mappings != [(alias, "pg_catalog", "simple") for alias in ("a", "e", "i", "l", "n", "v")]
    ):
        raise KnowledgeError("sparse_environment_mismatch")


async def _check_index(connection):
    row = await (
        await connection.execute(
            "SELECT i.indisvalid,i.indisready,i.indislive,am.amname, "
            "c.reloptions, i.indnkeyatts=1 AND i.indnatts=1 "
            "AND i.indpred IS NULL AND i.indexprs IS NULL AND NOT i.indisunique "
            "AND i.indkey[0]=(SELECT attnum FROM pg_attribute "
            "WHERE attrelid=t.oid AND attname='search_text' AND NOT attisdropped) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_index i ON i.indexrelid=c.oid JOIN pg_class t ON t.oid=i.indrelid "
            "JOIN pg_namespace tn ON tn.oid=t.relnamespace JOIN pg_am am ON am.oid=c.relam "
            "WHERE n.nspname='public' AND c.relname=%s "
            "AND tn.nspname='public' AND t.relname='knowledge_chunks'",
            (INDEX_NAME,),
        )
    ).fetchone()
    if (
        not row
        or row[:4] != (True, True, True, "bm25")
        or row[4] != ["text_config=public.chinese"]
        or row[5] is not True
    ):
        raise KnowledgeError("sparse_index_unavailable")


async def activate(pool) -> int:
    """Build the pinned index and publish readiness atomically in a maintenance window."""
    async with pool.connection() as connection, connection.transaction():
        await lock_publication(connection)
        await _check_environment(connection)
        await _check_inputs(connection)
        existed = (
            await (
                await connection.execute(
                    "SELECT to_regclass('public.knowledge_chunks_bm25_idx') IS NOT NULL"
                )
            ).fetchone()
        )[0]
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS knowledge_chunks_bm25_idx "
            "ON public.knowledge_chunks USING bm25 (search_text) "
            "WITH (text_config='public.chinese')"
        )
        await _check_index(connection)
        if existed:
            state = await (
                await connection.execute(
                    "SELECT sparse_profile,index_name,watermark,ready "
                    "FROM knowledge_index_state WHERE singleton"
                )
            ).fetchone()
            if (
                state
                and state[0] == SparseIndexProfile().key
                and state[1] == INDEX_NAME
                and state[3]
            ):
                return state[2]
        row = await (
            await connection.execute(
                "UPDATE knowledge_index_state SET sparse_profile=%s,index_name=%s,ready=true, "
                "watermark=watermark+1 WHERE singleton RETURNING watermark",
                (SparseIndexProfile().key, INDEX_NAME),
            )
        ).fetchone()
        return row[0]


async def check_sparse_ready(connection) -> int:
    """Fail closed if the persisted profile, corpus, environment or index drifted."""
    row = await (
        await connection.execute(
            "SELECT sparse_profile,index_name,watermark,ready FROM knowledge_index_state "
            "WHERE singleton"
        )
    ).fetchone()
    if not row or row[0] != SparseIndexProfile().key or row[1] != INDEX_NAME or not row[3]:
        raise KnowledgeError("sparse_index_unavailable")
    await _check_environment(connection)
    await _check_inputs(connection)
    await _check_index(connection)
    return row[2]
