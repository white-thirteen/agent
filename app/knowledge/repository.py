"""Current-version publication and exact cosine search using bound PostgreSQL SQL."""

import psycopg
from psycopg.rows import dict_row

from app.knowledge.embedding import validate_vectors
from app.knowledge.models import Document, EvidenceChunk, KnowledgeError, digest


class KnowledgeRepository:
    def __init__(self, pool):
        self.pool = pool

    async def is_complete(self, document: Document) -> bool:
        async with self.pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT d.document_version,d.content_hash,d.embedding_profile,d.chunk_count,"
                "count(c.chunk_id) FROM knowledge_documents d LEFT JOIN knowledge_chunks c "
                "ON c.document_id=d.document_id AND c.document_version=d.document_version "
                "WHERE d.document_id=%s GROUP BY d.document_id",
                (document.entry.document_id,),
            )
            row = await cursor.fetchone()
            return row == (
                document.document_version,
                document.content_hash,
                document.embedding_profile,
                len(document.chunks),
                len(document.chunks),
            )

    async def replace(self, document: Document, vectors: list[list[float]]) -> bool:
        vectors = validate_vectors(vectors, len(document.chunks))
        async with self.pool.connection() as connection, connection.transaction():
            # Advisory lock covers first publication too; no lock is held during embedding.
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("knowledge:" + document.entry.document_id,),
            )
            cursor = await connection.execute(
                "SELECT document_version,chunk_count FROM knowledge_documents "
                "WHERE document_id=%s FOR UPDATE",
                (document.entry.document_id,),
            )
            current = await cursor.fetchone()
            if current == (document.document_version, len(document.chunks)):
                cursor = await connection.execute(
                    "SELECT count(*) FROM knowledge_chunks WHERE document_id=%s",
                    (document.entry.document_id,),
                )
                if (await cursor.fetchone())[0] == len(document.chunks):
                    return False
            await connection.execute(
                "DELETE FROM knowledge_chunks WHERE document_id=%s", (document.entry.document_id,)
            )
            await connection.execute(
                "INSERT INTO knowledge_documents(document_id,document_version,content_hash,domain,"
                "source_title,public_source_key,embedding_profile,chunk_count) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(document_id) DO UPDATE SET "
                "document_version=EXCLUDED.document_version,content_hash=EXCLUDED.content_hash,"
                "domain=EXCLUDED.domain,source_title=EXCLUDED.source_title,"
                "public_source_key=EXCLUDED.public_source_key,embedding_profile=EXCLUDED.embedding_profile,"
                "chunk_count=EXCLUDED.chunk_count,updated_at=now()",
                (
                    document.entry.document_id,
                    document.document_version,
                    document.content_hash,
                    document.entry.domain,
                    document.entry.source_title,
                    document.entry.public_source_key,
                    document.embedding_profile,
                    len(document.chunks),
                ),
            )
            for chunk, vector in zip(document.chunks, vectors, strict=True):
                await connection.execute(
                    "INSERT INTO knowledge_chunks(chunk_id,document_id,document_version,ordinal,"
                    "section,page,line_start,line_end,content,content_hash,token_count,embedding) "
                    "VALUES (%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s::vector)",
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
            return True

    async def remove(self, document_id: str):
        async with self.pool.connection() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("knowledge:" + document_id,),
            )
            await connection.execute(
                "DELETE FROM knowledge_chunks WHERE document_id=%s", (document_id,)
            )
            await connection.execute(
                "DELETE FROM knowledge_documents WHERE document_id=%s", (document_id,)
            )

    async def search(self, vector, profile: str, domain: str | None):
        vector = validate_vectors([vector], 1)[0]
        try:
            async with self.pool.connection() as connection, connection.transaction():
                await connection.execute("SET LOCAL statement_timeout = '5s'")
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        "SELECT c.chunk_id,c.document_id,c.document_version,"
                        "c.content_hash,c.content,"
                        "c.section,c.line_start,c.line_end,d.source_title,d.public_source_key,d.domain,"
                        "1-(c.embedding <=> %s::vector) AS retrieval_score "
                        "FROM knowledge_chunks c JOIN knowledge_documents d "
                        "ON c.document_id=d.document_id AND c.document_version=d.document_version "
                        "WHERE d.embedding_profile=%s AND (%s::text IS NULL OR d.domain=%s) "
                        "ORDER BY c.embedding <=> %s::vector,c.chunk_id LIMIT 5",
                        (str(vector), profile, domain, domain, str(vector)),
                    )
                    rows = await cursor.fetchall()
                    await cursor.execute(
                        "SELECT EXISTS(SELECT 1 FROM knowledge_documents "
                        "WHERE embedding_profile<>%s)",
                        (profile,),
                    )
                    if (await cursor.fetchone())["exists"]:
                        raise KnowledgeError("embedding_profile_mismatch")
            return tuple(EvidenceChunk(evidence_id=digest(row["chunk_id"]), **row) for row in rows)
        except psycopg.errors.QueryCanceled:
            raise KnowledgeError("retrieval_timeout") from None
        except psycopg.Error:
            raise KnowledgeError("knowledge_index_unavailable") from None

    async def validate_evidence(self, refs):
        invalid = []
        try:
            async with self.pool.connection() as connection, connection.transaction():
                await connection.execute("SET LOCAL statement_timeout = '5s'")
                for ref in refs:
                    cursor = await connection.execute(
                        "SELECT 1 FROM knowledge_chunks c JOIN knowledge_documents d "
                        "ON c.document_id=d.document_id AND c.document_version=d.document_version "
                        "WHERE c.document_id=%s AND c.document_version=%s AND c.chunk_id=%s "
                        "AND c.content_hash=%s",
                        (ref.document_id, ref.document_version, ref.chunk_id, ref.content_hash),
                    )
                    if await cursor.fetchone() is None:
                        invalid.append(digest(ref.chunk_id))
        except psycopg.Error:
            raise KnowledgeError("knowledge_index_unavailable") from None
        return {"valid": not invalid, "invalid_evidence_ids": invalid}
