"""Opt-in isolated PostgreSQL through hybrid retriever and governed graph."""

import os
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import AsyncConnectionPool
from test_hybrid_task131 import graph_for
from test_knowledge_graph import QUESTION, execution

from app.agents.types import AgentType, TaskType
from app.graph.contracts import SpecialistInput
from app.graph.transfers import create_specialist_state
from app.knowledge.chunking import prepare_document
from app.knowledge.models import ManifestEntry
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.retriever import HybridRetriever
from scripts import run_async


def test_isolated_pg_governed_hybrid(tmp_path):
    dsn = os.getenv("AGENT_HYBRID_TASK131_DATABASE_URL")
    if not dsn:
        pytest.skip("Explicit isolated Task 1.3.1 database required")
    target = conninfo_to_dict(dsn)
    assert (target.get("host"), target.get("port"), target.get("dbname"), target.get("user")) == (
        "127.0.0.1",
        "56431",
        "agent_demo_test",
        "agent_test",
    )

    async def scenario():
        pool = AsyncConnectionPool(conninfo=dsn, open=False, min_size=1, max_size=2)
        await pool.open(wait=True)
        identifier = "task131-" + uuid4().hex
        repo = KnowledgeRepository(pool)
        created = False

        class Embeddings:
            async def aembed_query(self, query):
                return [1.0] + [0.0] * 1023

        class Reranker:
            async def score(self, query, candidates):
                return [1.0] * len(candidates)

        try:
            async with pool.connection() as conn:
                row = await (
                    await conn.execute(
                        "SELECT current_database(),current_user,"
                        "shobj_description(oid,'pg_database') "
                        "FROM pg_database WHERE datname=current_database()"
                    )
                ).fetchone()
            assert row == ("agent_demo_test", "agent_test", "codex-task131-0e62")
            await repo.check_ready("controlled-task131")
            await repo.check_hybrid_ready()
            path = tmp_path / "source.md"
            path.write_text("# 审批\n\n普通聊天不得批准退款。", encoding="utf-8")
            doc = prepare_document(
                tmp_path,
                ManifestEntry(
                    document_id=identifier,
                    filename=path.name,
                    source_title="审批",
                    domain="after_sales_help",
                    public_source_key=identifier,
                ),
                "controlled-task131",
            )
            await repo.replace(doc, [[1.0] + [0.0] * 1023 for _ in doc.chunks])
            created = True
            retriever = HybridRetriever(repo, Embeddings(), Reranker(), "controlled-task131", 30)
            graph, _ = graph_for(retriever)
            live = execution()
            request = SpecialistInput(
                context=live.context,
                task_id="task",
                agent_type=AgentType.KNOWLEDGE,
                task_type=TaskType.KNOWLEDGE_QA,
                task_goal="ignored",
                entities={},
                messages=[HumanMessage(content=QUESTION)],
            )
            state = await graph.ainvoke(
                create_specialist_state(request, scope=live.scope), context=live
            )
            assert state["result"].approved_answer
            assert state["result"].sources[0].document_id == identifier
            assert state["retrieval_observation"]["candidates"][0]["sparse"] is not None
        finally:
            if created:
                await repo.remove(identifier)
            await pool.close()

    run_async(scenario())
