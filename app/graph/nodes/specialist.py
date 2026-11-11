"""Explicit current-context invocation and allowlisted specialist result mapping."""

from dataclasses import asdict

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from app.graph.contracts import GraphProtocolError, SpecialistInput
from app.graph.state import AgentState
from app.graph.transfers import (
    apply_specialist_result,
    build_specialist_input,
    create_specialist_state,
)
from app.runtime.context import RunExecutionContext


def make_specialist_node(subgraph):
    async def specialist_node(
        state: AgentState, config: RunnableConfig, runtime: Runtime[RunExecutionContext]
    ):
        request = build_specialist_input(state)
        if request.context != runtime.context.context:
            raise GraphProtocolError("Parent execution association mismatch")
        scope = runtime.context.scope
        output = await subgraph.ainvoke(
            create_specialist_state(request, scope=scope), config, context=runtime.context
        )
        returned_request = SpecialistInput.model_validate(output["request"])
        if returned_request != request:
            raise GraphProtocolError("Specialist changed its trusted request")
        if output.get("result") is None:
            raise GraphProtocolError("Specialist must produce a structured result")
        # Only the trusted shared scope is authoritative; child counters are not added or adopted.
        return {
            **apply_specialist_result(state, output["result"]),
            "model_call_usage": asdict(scope.model_usage()),
            "run_usage": asdict(scope.run_usage()),
        }

    return specialist_node
