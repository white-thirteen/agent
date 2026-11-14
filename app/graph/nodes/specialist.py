"""Explicit current-context invocation and allowlisted specialist result mapping."""

from dataclasses import asdict

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from app.agents.types import AgentType, TaskType
from app.graph.contracts import GraphProtocolError, SpecialistInput
from app.graph.state import AgentState
from app.graph.transfers import (
    apply_specialist_result,
    build_specialist_input,
    create_specialist_state,
)
from app.runtime.context import RunExecutionContext


def make_specialist_node(subgraph, *, memory_graph=None):
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
        selected = subgraph
        memory_input = {}
        if request.task_type is TaskType.MEMORY_MANAGE and memory_graph is not None:
            from app.graph.specialists.knowledge.memory import parse_explicit_memory_command

            selected = memory_graph
            # Source IDs were supplied by Runtime, never by route entities or Store.
            humans = [
                m
                for m in state["messages"]
                if isinstance(m, HumanMessage) and m.id in state["task_message_ids"]
            ]
            source = humans[-1] if humans else None
            command = (
                parse_explicit_memory_command(source.content)
                if source and isinstance(source.content, str)
                else None
            )
            if command and any(
                value != command.model_dump().get(key) for key, value in request.entities.items()
            ):
                command = None
            memory_input = {
                "memory_command": command.model_dump(mode="json") if command else None,
                "source_message_id": source.id if source else None,
            }
        output = await selected.ainvoke(
            None
            if continuing
            else {
                **create_specialist_state(request, scope=scope),
                "memory_read_record": state.get("memory_read_record"),
                **memory_input,
            },
            config,
            context=runtime.context,
            **({"durability": "sync"} if selected is memory_graph else {}),
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
            "memory_read_record": output.get("memory_read_record"),
            **({"run_id": effective.run_id} if continuing else {}),
            "model_call_usage": asdict(scope.model_usage()),
            "run_usage": asdict(scope.run_usage()),
        }

    return specialist_node
