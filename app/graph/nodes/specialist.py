"""Explicit current-context invocation and allowlisted specialist result mapping."""

from dataclasses import asdict

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from app.agents.types import AgentType
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
        effective = runtime.context.context
        continuing = runtime.context.execution_mode in ("resume", "reconcile")
        if continuing and request.agent_type is not AgentType.REFUND:
            raise GraphProtocolError("Recovery is only supported for refund tasks")
        association = ("user_id", "conversation_id", "task_id", "workflow_id")
        if any(getattr(request.context, key) != getattr(effective, key) for key in association):
            raise GraphProtocolError("Parent execution association mismatch")
        if not continuing and request.context.run_id != effective.run_id:
            raise GraphProtocolError("Parent run association mismatch")
        scope = runtime.context.scope
        output = await subgraph.ainvoke(
            None if continuing else create_specialist_state(request, scope=scope),
            config,
            context=runtime.context,
        )
        returned_request = SpecialistInput.model_validate(output["request"])
        if returned_request != request:
            raise GraphProtocolError("Specialist changed its trusted request")
        if output.get("result") is None:
            raise GraphProtocolError("Specialist must produce a structured result")
        # Only the trusted shared scope is authoritative; child counters are not added or adopted.
        result_state = {**state, "run_id": effective.run_id} if continuing else state
        return {
            **apply_specialist_result(result_state, output["result"]),
            **({"run_id": effective.run_id} if continuing else {}),
            "model_call_usage": asdict(scope.model_usage()),
            "run_usage": asdict(scope.run_usage()),
        }

    return specialist_node
