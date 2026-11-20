import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from test_hybrid_task121 import evidence
from test_hybrid_task131 import Hybrid, graph_for
from test_knowledge_graph import QUESTION, execution

from app.agents.types import AgentType, TaskType
from app.core.config import Settings
from app.graph.contracts import SpecialistInput
from app.graph.transfers import create_specialist_state
from app.knowledge.models import KnowledgeError, SearchQuery
from app.knowledge.reranker import BGEReranker
from app.knowledge.retriever import HybridRetriever, local_rerank_order
from app.runtime.context import DemoIdentity

IDENTITY = DemoIdentity("test", frozenset({"knowledge:read"}))


class Repository:
    async def hybrid_candidates(self, vector, query, profile, domain):
        return (
            1,
            [
                evidence(name, 1.0).model_copy(update={"content": name})
                for name in ("a", "b", "c", "d", "e")
            ],
            [],
        )


class Embeddings:
    async def aembed_query(self, query):
        return [1.0]


async def test_local_order_scores_suffix_and_default():
    class Reranker:
        async def score(self, query, candidates):
            assert [c.document_id for c in candidates] == list("abcde")
            return [1.0, 3.0, 2.0, 100.0, 200.0]

    result = await HybridRetriever(Repository(), Embeddings(), Reranker(), "profile", 30).search(
        SearchQuery(query="question", top_k=5), identity=IDENTITY
    )
    assert [e.document_id for e in result.evidence] == list("bcade")
    assert [e.retrieval_score for e in result.evidence] == [3, 2, 1, 100, 200]
    assert [c.reranker_score for c in result.candidates] == [3, 2, 1, 100, 200]
    assert Settings(_env_file=None).knowledge_retrieval_mode == "dense"


def test_order_short_prefix_ties_and_score_alignment():
    ids = [(s, "v", s, "h") for s in "cbaed"]
    assert local_rerank_order([1, 1, 1, 100, 200], ids) == (2, 1, 0, 3, 4)
    assert local_rerank_order([1, 2], ids[:2]) == (1, 0)
    assert local_rerank_order([], []) == ()
    with pytest.raises(ValueError):
        local_rerank_order([1], [])


async def test_full_pool_oversize_and_deadline_still_fail():
    class Tokenizer:
        def __call__(self, query, passage, **kwargs):
            return {"input_ids": [1] * (513 if passage.endswith("d") else 10)}

    reranker = BGEReranker(Settings(_env_file=None))
    reranker._model = SimpleNamespace(tokenizer=Tokenizer(), model=None)
    try:
        # The oversized fourth RRF candidate must fail before any inference.
        with pytest.raises(KnowledgeError, match="rerank_input_too_long"):
            await HybridRetriever(Repository(), Embeddings(), reranker, "profile", 30).search(
                SearchQuery(query="question"), identity=IDENTITY
            )
    finally:
        await reranker.aclose()

    class Slow:
        async def score(self, query, candidates):
            await asyncio.sleep(1)

    with pytest.raises(KnowledgeError, match="retrieval_timeout"):
        await HybridRetriever(Repository(), Embeddings(), Slow(), "profile", 0.01).search(
            SearchQuery(query="question"), identity=IDENTITY
        )


async def test_old_profile_is_rejected_by_graph_replay():
    retriever = Hybrid()
    retriever.retrieval_profile = HybridRetriever(
        Repository(), Embeddings(), None, retriever.profile, 30
    ).retrieval_profile
    old_profile = json.loads(retriever.retrieval_profile)
    del old_profile["reranker_order"]
    assert json.loads(retriever.retrieval_profile)["reranker_order"] == "rrf-top3-bge-local-v1"
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
    state = await graph.ainvoke(create_specialist_state(request, scope=live.scope), context=live)
    records = dict(state["call_records"])
    record = dict(records["search-1"])
    from app.knowledge.models import canonical

    record["result"] = {
        **record["result"],
        "data": {**record["result"]["data"], "retrieval_profile": canonical(old_profile)},
    }
    records["search-1"] = record
    node = graph.nodes["retrieve_knowledge"].node.steps[0].afunc
    result = await node({**state, "call_records": records}, SimpleNamespace(context=live))
    assert result["error_code"] == "tool_result_invalid"
    assert retriever.searches == 1
