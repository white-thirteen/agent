"""Explicit parent/child mappings. Return updates rather than mutating shared state."""

from copy import deepcopy

from langchain_core.messages import AIMessage, HumanMessage

from app.graph.contracts import (
    ExecutionContext,
    GraphProtocolError,
    PendingTask,
    ResultStatus,
    RouteDecision,
    SpecialistInput,
    SpecialistResult,
)
from app.graph.router import validated_route
from app.graph.state import AgentState, ResultUpdate, RouteUpdate, SpecialistState


def apply_route_decision(state: AgentState, decision: RouteDecision) -> RouteUpdate:
    """SupervisorNode returns this update; the edge reads the updated channels."""
    decision = RouteDecision.model_validate(decision).model_copy(deep=True)
    context = _context_from_state(state)
    pending = None
    if decision.needs_clarification:
        pending = PendingTask(
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            workflow_id=context.workflow_id,
            task_id=state["task_id"],
            task_type=decision.task_type,
            task_goal=decision.task_goal,
            entities=deepcopy(decision.entities),
            missing_fields=list(decision.missing_fields),
            clarification_question=decision.clarification_question,
        )
    return RouteUpdate(
        agent_type=decision.agent_type,
        task_type=decision.task_type,
        task_goal=decision.task_goal,
        route_decision=decision,
        pending_task=pending,
        specialist_result=None,
        final_answer=None,
        sources=[],
    )


def build_specialist_input(state: AgentState) -> SpecialistInput:
    """Copy only public context and selected task into the child contract."""
    decision = validated_route(state)
    if decision.needs_clarification:
        raise GraphProtocolError("A task requiring clarification cannot enter a specialist")
    messages = []
    for message in state["messages"]:
        if isinstance(message, HumanMessage):
            messages.append(HumanMessage(content=deepcopy(message.content), id=message.id))
        elif isinstance(message, AIMessage) and not (
            message.tool_calls or message.invalid_tool_calls
        ):
            messages.append(AIMessage(content=deepcopy(message.content), id=message.id))
    return SpecialistInput(
        context=_context_from_state(state),
        task_id=state["task_id"],
        agent_type=decision.agent_type,
        task_type=decision.task_type,
        task_goal=decision.task_goal,
        entities=deepcopy(decision.entities),
        messages=messages,
    )


def create_specialist_state(request: SpecialistInput) -> SpecialistState:
    request = SpecialistInput.model_validate(request).model_copy(deep=True)
    return SpecialistState(
        request=request,
        messages=deepcopy(request.messages),
        selected_tools=[],
        result=None,
    )


def apply_specialist_result(state: AgentState, result: SpecialistResult) -> ResultUpdate:
    """Reject foreign results and whitelist updates; never copy child messages back."""
    request = build_specialist_input(state)
    result = SpecialistResult.model_validate(result).model_copy(deep=True)
    expected = {
        "workflow_id": request.context.workflow_id,
        "run_id": request.context.run_id,
        "task_id": request.task_id,
        "agent_type": request.agent_type,
        "task_type": request.task_type,
    }
    for field, value in expected.items():
        if getattr(result, field) != value:
            raise GraphProtocolError(f"Specialist result does not match the current {field}")
    pending = None
    if result.status is ResultStatus.NEEDS_INPUT:
        pending = PendingTask(
            user_id=request.context.user_id,
            conversation_id=request.context.conversation_id,
            workflow_id=request.context.workflow_id,
            task_id=request.task_id,
            task_type=request.task_type,
            task_goal=request.task_goal,
            entities=deepcopy({**request.entities, **result.entities}),
            missing_fields=list(result.missing_fields),
            clarification_question=result.clarification_question,
        )
    return ResultUpdate(
        specialist_result=result,
        pending_task=pending,
        final_answer=None,
        sources=deepcopy(result.sources),
    )


def _context_from_state(state: AgentState) -> ExecutionContext:
    try:
        return ExecutionContext(
            user_id=state["user_id"],
            conversation_id=state["conversation_id"],
            workflow_id=state["workflow_id"],
            run_id=state["run_id"],
        )
    except KeyError as exc:
        raise GraphProtocolError("Parent state is missing execution context") from exc
