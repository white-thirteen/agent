"""Compiled order skeleton. Domain behavior belongs to its later stage."""

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agents.types import AgentType
from app.graph.contracts import (
    FailureDetails,
    GraphProtocolError,
    SpecialistInput,
    SpecialistResult,
)
from app.graph.state import SpecialistState
from app.runtime.context import RunExecutionContext


def build_order_graph():
    def check_contract(state: SpecialistState, runtime: Runtime[RunExecutionContext]):
        request = SpecialistInput.model_validate(state["request"])
        if request.agent_type is not AgentType.ORDER or request.context != runtime.context.context:
            raise GraphProtocolError("Specialist request association mismatch")
        if request.task_id != request.context.task_id:
            raise GraphProtocolError("Specialist task association mismatch")
        return {}

    def capability_unavailable(state: SpecialistState):
        request = state["request"]
        return {
            "result": SpecialistResult(
                workflow_id=request.context.workflow_id,
                run_id=request.context.run_id,
                task_id=request.task_id,
                agent_type=request.agent_type,
                task_type=request.task_type,
                status="failed",
                summary="This capability is not implemented yet.",
                error=FailureDetails(
                    code="capability_unavailable", message="This capability is not implemented yet."
                ),
            )
        }

    def map_result(state: SpecialistState, runtime: Runtime[RunExecutionContext]):
        from dataclasses import asdict

        return {
            "result": SpecialistResult.model_validate(state["result"]),
            "model_call_usage": asdict(runtime.context.scope.model_usage()),
            "run_usage": asdict(runtime.context.scope.run_usage()),
        }

    graph = StateGraph(SpecialistState, context_schema=RunExecutionContext)
    graph.add_node("check_contract", check_contract)
    graph.add_node("capability_unavailable", capability_unavailable)
    graph.add_node("map_result", map_result)
    graph.add_edge(START, "check_contract")
    graph.add_edge("check_contract", "capability_unavailable")
    graph.add_edge("capability_unavailable", "map_result")
    graph.add_edge("map_result", END)
    return graph.compile()
