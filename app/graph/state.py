"""Public task channels and private specialist channels with explicit turn preparation."""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph import add_messages

from app.agents.types import AgentType, TaskType
from app.graph.contracts import (
    ExecutionContext,
    GraphProtocolError,
    PendingTask,
    RouteDecision,
    SourceReference,
    SpecialistInput,
    SpecialistResult,
)
from app.runtime.models import TaskStatus


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    agent_type: AgentType
    user_id: str
    conversation_id: str
    workflow_id: str
    run_id: str
    task_id: str
    task_status: TaskStatus
    task_type: TaskType | None
    task_goal: str | None
    task_message_ids: list[str]
    route_decision: RouteDecision | None
    pending_task: PendingTask | None
    specialist_result: SpecialistResult | None
    final_answer: str | None
    sources: list[SourceReference]
    error: dict | None
    model_call_usage: dict
    run_usage: dict


class SpecialistState(TypedDict):
    request: SpecialistInput
    messages: Annotated[list[AnyMessage], add_messages]
    selected_tools: list[str]
    result: SpecialistResult | None
    model_call_usage: dict
    run_usage: dict


# Updates contain only changed channels, with no budget summation reducer.
RouteUpdate = dict[str, object]
ResultUpdate = dict[str, object]


def create_turn_state(
    context: ExecutionContext,
    message: str,
    *,
    task_mode: Literal["new", "continue"],
    saved_task: dict | None,
) -> AgentState:
    """Runtime supplies task identity and mode. This function never generates IDs."""
    context = ExecutionContext.model_validate(context)
    if not isinstance(message, str) or not message.strip() or len(message) > 32000:
        raise GraphProtocolError("A turn requires a nonblank message of at most 32000 characters")
    pending = None
    if task_mode == "continue":
        if not saved_task or saved_task.get("task_status") != TaskStatus.NEEDS_INPUT:
            raise GraphProtocolError("Continuation requires a saved input-waiting task")
        pending = PendingTask.model_validate(saved_task["pending_task"])
        for field in ("user_id", "conversation_id", "workflow_id", "task_id"):
            if getattr(pending, field) != getattr(context, field):
                raise GraphProtocolError("Pending task does not belong to the current context")
    ids = list(saved_task["task_message_ids"]) if pending else []
    ids.append(f"user:{context.run_id}")
    return AgentState(
        messages=[HumanMessage(content=message, id=f"user:{context.run_id}")],
        agent_type=pending.task_type.target_agent if pending else AgentType.SUPERVISOR,
        user_id=context.user_id,
        conversation_id=context.conversation_id,
        workflow_id=context.workflow_id,
        run_id=context.run_id,
        task_id=context.task_id,
        task_status=TaskStatus.RUNNING,
        task_type=pending.task_type if pending else None,
        task_goal=pending.task_goal if pending else None,
        task_message_ids=ids,
        route_decision=None,
        pending_task=pending,
        specialist_result=None,
        final_answer=None,
        sources=[],
        error=None,
        model_call_usage=dict(saved_task["model_call_usage"]) if pending else {"model_attempts": 0},
        run_usage=dict(saved_task["run_usage"])
        if pending
        else {"tool_calls": 0, "active_elapsed_ms": 0},
    )
