"""Governed hybrid graph, replay and evidence behavior with controlled models."""

from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from test_knowledge_graph import QUESTION, Provider, Retriever, execution

from app.agents.types import AgentType, TaskType
from app.graph.contracts import GraphProtocolError, SpecialistInput
from app.graph.specialists.knowledge.builder import build_knowledge_graph
from app.graph.transfers import create_specialist_state
from app.knowledge.models import (
    HybridSearchResult,
    RetrievalCandidate,
    SparseIndexProfile,
    canonical,
    digest,
)
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from app.tools.executor import ToolExecutor
from app.tools.implementations.knowledge import knowledge_tools
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry


class Hybrid(Retriever):
    retrieval_profile = "hybrid-profile"

    async def search(self, query, *, identity):
        base = await super().search(query, identity=identity)
        evidence = tuple(
            e.model_copy(update={"content_hash": digest(e.content)}) for e in base.evidence
        )
        base = base.model_copy(
            update={"evidence": evidence, "context": canonical([e.model_dump() for e in evidence])}
        )
        candidates = tuple(
            RetrievalCandidate(
                **{
                    k: getattr(e, k)
                    for k in ("document_id", "document_version", "chunk_id", "content_hash")
                },
                rrf_score=0.1,
                reranker_score=e.retrieval_score,
            )
            for e in base.evidence
        )
        return HybridSearchResult(
            **base.model_dump(),
            contract_version=2,
            mode="hybrid",
            retrieval_profile=self.retrieval_profile,
            sparse_profile=SparseIndexProfile().key,
            index_watermark=1,
            candidates=candidates,
        )


def graph_for(retriever):
    registry = ToolRegistry()
    for tool in knowledge_tools(retriever, mode="hybrid"):
        registry.register(tool)
    registry.freeze()
    executor = ToolExecutor(registry, ToolPolicy())
    return build_knowledge_graph(
        gateway=ModelGateway(Provider(), ModelCallLimits(8, 5, 0)),
        registry=registry,
        executor=executor,
        profile=retriever.profile,
        mode="hybrid",
        retrieval_profile=retriever.retrieval_profile,
    ), registry


async def test_hybrid_governed_graph_replay_and_fresh_source_validation():
    retriever = Hybrid()
    graph, registry = graph_for(retriever)
    assert registry.get("search_knowledge").metadata.version == "2"
    assert registry.get("search_knowledge").metadata.timeout_seconds == 30
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
    assert (
        state["result"].approved_answer and state["retrieval_observation"]["contract_version"] == 2
    )
    node = graph.nodes["retrieve_knowledge"].node.steps[0].afunc
    replay = await node(state, SimpleNamespace(context=live))
    assert replay["retrieval_observation"]["mode"] == "hybrid" and retriever.searches == 1
    old = dict(state["call_records"])
    old["search-1"] = {**old["search-1"], "tool_version": "1"}
    with pytest.raises(GraphProtocolError):
        await node({**state, "call_records": old}, SimpleNamespace(context=live))
    bad = dict(state["call_records"])
    record = dict(bad["search-1"])
    record["result"] = {
        **record["result"],
        "data": {**record["result"]["data"], "retrieval_profile": "other"},
    }
    bad["search-1"] = record
    assert (await node({**state, "call_records": bad}, SimpleNamespace(context=live)))[
        "error_code"
    ] == "tool_result_invalid"
    retriever.changed = True
    validation = graph.nodes["validate_sources"].node.steps[0].afunc
    result = await validation(state, SimpleNamespace(context=live))
    assert result["error_code"] == "source_changed" and "approved_answer" not in result
