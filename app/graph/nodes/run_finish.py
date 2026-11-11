"""Ordinary in-graph task/budget settlement. Future interrupts bypass this exit."""

from dataclasses import asdict

from langgraph.runtime import Runtime

from app.graph.contracts import ExecutionContext, GraphProtocolError
from app.graph.state import AgentState
from app.runtime.context import RunExecutionContext
from app.runtime.models import TaskStatus


def run_finish_node(state: AgentState, runtime: Runtime[RunExecutionContext]):
    trusted = runtime.context.context
    actual = ExecutionContext(**{field: state[field] for field in ExecutionContext.model_fields})
    if actual != trusted:
        raise GraphProtocolError("Run finish association mismatch")
    status = TaskStatus(state["task_status"])
    if (status is TaskStatus.FAILED) != (state.get("error") is not None):
        raise GraphProtocolError("Only failed tasks must carry an error")
    if status in (TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL, TaskStatus.PAUSED):
        raise GraphProtocolError(
            "Ordinary run finish requires an ordinary terminal/waiting-input result"
        )
    pending = state.get("pending_task") if status is TaskStatus.NEEDS_INPUT else None
    if status is TaskStatus.NEEDS_INPUT:
        if pending is None:
            raise GraphProtocolError("Input waiting requires pending task")
        pending = pending.model_copy(update={"task_message_ids": list(state["task_message_ids"])})
    scope = runtime.context.scope
    return {
        "task_status": status,
        "pending_task": pending,
        "model_call_usage": asdict(scope.model_usage()),
        "run_usage": asdict(scope.finish_active_period()),
    }
