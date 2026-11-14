"""Compile the Supervisor topology once with explicit Gateway, specialists and Saver."""

from collections.abc import Mapping

from langgraph.graph import END, START, StateGraph

from app.agents.types import AgentType
from app.graph.nodes.clarification import clarification_node
from app.graph.nodes.response import response_node
from app.graph.nodes.result_aggregator import result_aggregator_node
from app.graph.nodes.run_finish import run_finish_node
from app.graph.nodes.specialist import make_specialist_node
from app.graph.nodes.supervisor import make_supervisor_node
from app.graph.router import route_after_specialist, route_after_supervisor
from app.graph.state import AgentState
from app.runtime.context import RunExecutionContext


def build_supervisor_graph(*, gateway, specialists: Mapping, checkpointer, memory_graph=None):
    required = {AgentType.ORDER, AgentType.REFUND, AgentType.KNOWLEDGE}
    if set(specialists) != required:
        raise ValueError("Exactly the three specialist graphs must be injected")
    graph = StateGraph(AgentState, context_schema=RunExecutionContext)
    graph.add_node("supervisor", make_supervisor_node(gateway))
    graph.add_node("clarification", clarification_node)
    graph.add_node("result_aggregator", result_aggregator_node)
    graph.add_node("response", response_node)
    graph.add_node("run_finish", run_finish_node)
    for role in required:
        graph.add_node(
            role.value,
            make_specialist_node(
                specialists[role],
                memory_graph=memory_graph if role is AgentType.KNOWLEDGE else None,
            ),
        )
        graph.add_conditional_edges(role.value, route_after_specialist)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", route_after_supervisor)
    graph.add_edge("clarification", "response")
    graph.add_edge("result_aggregator", "response")
    graph.add_edge("response", "run_finish")
    graph.add_edge("run_finish", END)
    return graph.compile(checkpointer=checkpointer)
