"""Opt-in real pgvector tests; unique knowledge rows and exact cleanup only."""

import os
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from app.knowledge.chunking import prepare_document
from app.knowledge.models import KnowledgeError, ManifestEntry
from app.knowledge.repository import KnowledgeRepository
from scripts import run_async
from scripts.migrate import MIGRATIONS_DIR, migration_files


@pytest.fixture
def knowledge_database():
    url = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Explicit AGENT_TEST_DATABASE_URL required for real pgvector")
    secret = SecretStr(url)
    validate_test_target(secret, Settings().database_url)
    return Settings(_env_file=None, database_url=secret, app_env="test")


async def protected_snapshot(pool):
    result = {}
    async with pool.connection() as connection:
        assert await (
            await connection.execute("SELECT current_database(),current_user")
        ).fetchone() == ("agent_demo_test", "agent_test")
        applied = dict(
            await (
                await connection.execute(
                    "SELECT version,checksum FROM schema_migrations ORDER BY version"
                )
            ).fetchall()
        )
        assert applied == {v: item[0] for v, item in migration_files(MIGRATIONS_DIR).items()}
        for table in (
            "sessions",
            "demo_orders",
            "refund_requests",
            "approvals",
            "schema_migrations",
            "checkpoints",
            "checkpoint_blobs",
            "checkpoint_writes",
            "checkpoint_migrations",
            "knowledge_documents",
            "knowledge_chunks",
        ):
            rows = await (
                await connection.execute(
                    psycopg.sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY 1").format(
                        psycopg.sql.Identifier(table)
                    )
                )
            ).fetchall()
            result[table] = rows
    return result


def test_real_publication_rollback_current_sources_and_exact_cosine(knowledge_database, tmp_path):
    async def scenario():
        pool = await open_pool(knowledge_database)
        repository = KnowledgeRepository(pool)
        before = await protected_snapshot(pool)
        async with pool.connection() as connection:
            profiles = await (
                await connection.execute(
                    "SELECT DISTINCT embedding_profile FROM knowledge_documents"
                )
            ).fetchall()
        assert len(profiles) <= 1, "Existing test index has incompatible profiles"
        profile = profiles[0][0] if profiles else "controlled-profile"
        identifier = "test-knowledge-" + uuid4().hex
        entry = ManifestEntry(
            document_id=identifier,
            filename="doc.md",
            source_title="Demo",
            domain="platform_help",
            public_source_key=identifier,
        )
        path = tmp_path / "doc.md"
        path.write_text("# Demo\n\nfirst body", encoding="utf-8")
        original = prepare_document(tmp_path, entry, profile)
        vector = [1.0] + [0.0] * 1023
        try:
            assert await repository.replace(original, [vector])
            assert await repository.is_complete(original)
            assert not await repository.replace(original, [vector])
            results = await repository.search(vector, profile, "platform_help")
            assert results[0].chunk_id == original.chunks[0].chunk_id
            assert results[0].retrieval_score == pytest.approx(1)
            assert (await repository.validate_evidence(results))["valid"]
            path.write_text("# Demo\n\nsecond body\n\nthird body", encoding="utf-8")
            updated = prepare_document(tmp_path, entry, profile)
            duplicate = updated.model_copy(
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
                await repository.replace(duplicate, [vector, vector])
            assert await repository.is_complete(original)
            assert (await repository.validate_evidence(results))["valid"]
            assert await repository.replace(updated, [vector, vector])
            assert not (await repository.validate_evidence(results))["valid"]
            with pytest.raises(KnowledgeError, match="embedding_profile_mismatch"):
                await repository.search(vector, "different-profile", None)
            await repository.remove(identifier)
            assert not await repository.is_complete(updated)
            assert all(
                item.document_id != identifier
                for item in await repository.search(vector, profile, None)
            )
        finally:
            await repository.remove(identifier)
            assert await protected_snapshot(pool) == before
            await pool.close()

    run_async(scenario())


def test_governed_rag_pg_sources_checkpoint_and_deleted_draft(knowledge_database, tmp_path):
    """Real SQL/Saver with controlled Chat/embedding; this is not 5.2.2 model acceptance."""
    from dataclasses import replace

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from runtime_support import ControlledModel, context, route, run_to_end
    from test_knowledge_graph import ANSWER, QUESTION, Provider, resources

    from app.agents.types import AgentType, TaskType
    from app.graph.builder import build_supervisor_graph
    from app.graph.specialists.knowledge.builder import AnswerDraft, build_knowledge_graph
    from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
    from app.knowledge.retriever import VectorRetriever
    from app.runtime.agent_runtime import AgentRuntime
    from app.runtime.model_gateway import ModelCallLimits, ModelGateway
    from app.runtime.models import RunLimits

    async def scenario():
        pool = await open_pool(knowledge_database)
        checkpoint_pool = await open_checkpoint_pool(knowledge_database)
        saver = AsyncPostgresSaver(checkpoint_pool, serde=checkpoint_serializer())
        before = await protected_snapshot(pool)
        repository = KnowledgeRepository(pool)
        identifier = "test-rag-" + uuid4().hex
        thread = "test-rag-thread-" + uuid4().hex
        async with pool.connection() as conn:
            profiles = await (
                await conn.execute("SELECT DISTINCT embedding_profile FROM knowledge_documents")
            ).fetchall()
        assert len(profiles) <= 1
        profile = profiles[0][0] if profiles else "controlled-profile"
        (tmp_path / "approval.md").write_text(
            "# Demo审批说明\n\n聊天不能批准退款，应使用本地审批入口。", encoding="utf-8"
        )
        entry = ManifestEntry(
            document_id=identifier,
            filename="approval.md",
            source_title="Demo审批说明",
            domain="after_sales_help",
            public_source_key=identifier,
        )
        document = prepare_document(tmp_path, entry, profile)
        vector = [1.0] + [0.0] * 1023

        class Embeddings:
            async def aembed_query(self, text):
                assert text == QUESTION
                return vector

        class DeletingProvider(Provider):
            delete_before_validation = False

            async def ainvoke(self, messages):
                output = await super().ainvoke(messages)
                if self.delete_before_validation and self.schema is AnswerDraft:
                    await repository.remove(identifier)
                return output

        provider = DeletingProvider()
        retriever = VectorRetriever(repository, Embeddings(), profile)
        child, *_ = resources(retriever, provider)
        supervisor = ModelGateway(
            ControlledModel([route(TaskType.KNOWLEDGE_QA), route(TaskType.KNOWLEDGE_QA)]),
            ModelCallLimits(8, 5, 0),
        )
        graph = build_supervisor_graph(
            gateway=supervisor,
            checkpointer=saver,
            specialists={
                AgentType.ORDER: build_knowledge_graph(),
                AgentType.REFUND: build_knowledge_graph(),
                AgentType.KNOWLEDGE: child,
            },
        )
        runtime = AgentRuntime(graph, run_limits=RunLimits(30, 12))
        try:
            await repository.replace(document, [vector] * len(document.chunks))
            ctx = replace(
                context(message=QUESTION, thread=thread),
                permission_scopes=frozenset({"knowledge:read"}),
            )
            _, view, events = await run_to_end(runtime, ctx)
            assert view.task_status == "completed" and view.final_answer == ANSWER
            source = next(s for s in view.sources if s["document_id"] == identifier)
            assert source["document_version"] == document.document_version and source["checked_at"]
            assert view.run_usage.tool_calls == 2 and view.model_call_usage.model_attempts == 4
            persisted = await graph.aget_state({"configurable": {"thread_id": thread}})
            assert persisted.values["sources"][0].model_dump(mode="json") == view.sources[0]
            provider.delete_before_validation = True
            _, changed, events = await run_to_end(runtime, replace(ctx, run_id=str(uuid4())))
            assert changed.task_status == "failed" and changed.error["code"] == "source_changed"
            assert changed.final_answer is None and not changed.sources
            assert not any(e.kind == "token" for e in events)
        finally:
            await runtime.shutdown()
            await saver.adelete_thread(thread)
            await repository.remove(identifier)
            assert await protected_snapshot(pool) == before
            await checkpoint_pool.close()
            await pool.close()

    run_async(scenario())
