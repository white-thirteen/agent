"""Exercise the state schema against the installed LangGraph implementation."""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from app.agents.types import AgentType
from app.graph.contracts import ExecutionContext
from app.graph.state import AgentState, create_turn_state


def initial_state(user_id: str, run_id: str) -> AgentState:
    return create_turn_state(
        ExecutionContext(
            user_id=user_id,
            conversation_id=f"conversation-{user_id}",
            workflow_id=f"workflow-{user_id}",
            run_id=run_id,
        ),
        f"hello from {user_id}",
    )


def test_graph_appends_messages_replaces_matching_ids_and_overwrites_scalars():
    def answer(state: AgentState):
        return {"messages": [AIMessage(content="draft", id="answer")]}

    def revise(state: AgentState):
        return {
            "messages": [AIMessage(content="revised", id="answer")],
            "run_id": "replacement-run",
        }

    builder = StateGraph(AgentState)
    builder.add_node("answer", answer)
    builder.add_node("revise", revise)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", "revise")
    builder.add_edge("revise", END)
    result = builder.compile().invoke(initial_state("user-1", "run-1"))

    assert [message.id for message in result["messages"]] == ["user:run-1", "answer"]
    assert [message.content for message in result["messages"]] == ["hello from user-1", "revised"]
    assert isinstance(result["messages"][1], AIMessage)
    assert result["run_id"] == "replacement-run"
    assert result["agent_type"] == AgentType.SUPERVISOR
    assert result["user_id"] == "user-1"
    assert result["conversation_id"] == "conversation-user-1"
    assert result["workflow_id"] == "workflow-user-1"


@pytest.mark.asyncio
async def test_compiled_state_graph_keeps_concurrent_invocations_separate():
    async def answer(state: AgentState):
        # Allow both invocations to progress before reading their own state.
        await asyncio.sleep(0)
        return {"messages": [AIMessage(content=state["user_id"], id="answer")]}

    builder = StateGraph(AgentState)
    builder.add_node("answer", answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    graph = builder.compile()

    first, second = await asyncio.gather(
        graph.ainvoke(initial_state("user-1", "run-1")),
        graph.ainvoke(initial_state("user-2", "run-2")),
    )

    for result, user_id, run_id in [(first, "user-1", "run-1"), (second, "user-2", "run-2")]:
        assert [message.content for message in result["messages"]] == [
            f"hello from {user_id}",
            user_id,
        ]
        assert result["user_id"] == user_id
        assert result["workflow_id"] == f"workflow-{user_id}"
        assert result["run_id"] == run_id
