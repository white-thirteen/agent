"""Parent and private child channels; only message lists use a reducer."""

from typing import Annotated, TypedDict
from uuid import uuid4

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


class AgentState(TypedDict):
    """Public conversation and one task; private tool history stays in the child."""

    messages: Annotated[list[AnyMessage], add_messages]
    agent_type: AgentType
    user_id: str
    conversation_id: str
    workflow_id: str
    run_id: str
    task_id: str
    task_type: TaskType | None
    task_goal: str | None
    route_decision: RouteDecision | None
    pending_task: PendingTask | None
    specialist_result: SpecialistResult | None
    final_answer: str | None
    sources: list[SourceReference]


class SpecialistState(TypedDict):
    """Each specialist can extend this schema with its own business channels."""

    request: SpecialistInput
    messages: Annotated[list[AnyMessage], add_messages]
    selected_tools: list[str]
    result: SpecialistResult | None


class RouteUpdate(TypedDict):
    agent_type: AgentType
    task_type: TaskType
    task_goal: str
    route_decision: RouteDecision
    pending_task: PendingTask | None
    specialist_result: None
    final_answer: None
    sources: list[SourceReference]


class ResultUpdate(TypedDict):
    specialist_result: SpecialistResult
    pending_task: PendingTask | None
    final_answer: None
    sources: list[SourceReference]


def create_turn_state(
    context: ExecutionContext,
    message: str,
    *,
    pending_task: PendingTask | None = None,
) -> AgentState:
    """Build new-turn input, not interrupt resume input or a full history update.

    The caller supplies the stored pending task when continuing clarification.
    Messages contain only this turn's delta; a configured graph checkpointer
    owns prior history. This function does not authenticate or persist anything.
    """
    context = ExecutionContext.model_validate(context)
    if not isinstance(message, str) or not message.strip() or len(message) > 32000:
        raise GraphProtocolError("A turn requires a nonblank message of at most 32000 characters")
    if pending_task is not None:
        pending_task = PendingTask.model_validate(pending_task).model_copy(deep=True)
        for field in ("user_id", "conversation_id", "workflow_id"):
            if getattr(pending_task, field) != getattr(context, field):
                raise GraphProtocolError("Pending task does not belong to the current context")
    return AgentState(
        messages=[HumanMessage(content=message, id=f"user:{context.run_id}")],
        agent_type=AgentType.SUPERVISOR,
        user_id=context.user_id,
        conversation_id=context.conversation_id,
        workflow_id=context.workflow_id,
        run_id=context.run_id,
        task_id=pending_task.task_id if pending_task else str(uuid4()),
        task_type=pending_task.task_type if pending_task else None,
        task_goal=pending_task.task_goal if pending_task else None,
        route_decision=None,
        pending_task=pending_task,
        specialist_result=None,
        final_answer=None,
        sources=[],
    )
