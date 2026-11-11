"""Gateway routing, bounded structural correction and two kinds of clarification."""

from dataclasses import asdict

from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.agents.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT
from app.agents.types import AgentType, TaskType
from app.graph.contracts import GraphProtocolError, PendingTask, SupervisorOutput
from app.graph.state import AgentState
from app.graph.transfers import apply_route_decision, public_task_messages
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import ModelCallContext, ModelCallError
from app.runtime.models import TaskStatus

CAPABILITY_MESSAGE = (
    "演示范围包括本人订单查询、模拟退款申请、知识问答和两项偏好管理。该操作不受支持。"
)


def make_supervisor_node(gateway):
    async def supervisor_node(state: AgentState, runtime: Runtime[RunExecutionContext]):
        execution = runtime.context
        scope = execution.scope
        if scope.budget_exhausted():
            return {
                "task_status": TaskStatus.FAILED,
                "error": {"code": "budget_exceeded", "message": "Task execution budget exhausted."},
            }
        scope.emit_status("routing")
        pending = state.get("pending_task")
        if pending is not None:
            pending = PendingTask.model_validate(pending)
            for field in ("user_id", "conversation_id", "task_id", "workflow_id"):
                if getattr(pending, field) != state[field]:
                    raise GraphProtocolError("Pending task association mismatch")
        messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)]
        if pending:
            messages.append(
                SystemMessage(content="Trusted pending task: " + pending.model_dump_json())
            )
        messages.extend(public_task_messages(state))
        model_context = ModelCallContext(state["run_id"], state["task_id"], AgentType.SUPERVISOR)
        for correction in range(2):
            try:
                result = await gateway.invoke_structured(
                    messages,
                    schema=SupervisorOutput,
                    context=model_context,
                    model_usage=scope.model_usage(),
                )
                scope.adopt_model_usage(result.model_usage)
                output = SupervisorOutput.model_validate(result.parsed)
            except ModelCallError as error:
                scope.adopt_model_usage(error.model_usage)
                if error.code == "model_output_invalid" and correction == 0:
                    messages.append(
                        SystemMessage(
                            content="Return a valid SupervisorOutput matching the schema."
                        )
                    )
                    continue
                return _failure(error.code, scope)
            except ValidationError:
                if correction == 0:
                    messages.append(
                        SystemMessage(
                            content="Correct the route/agent/task and clarification schema."
                        )
                    )
                    continue
                return _failure("model_output_invalid", scope)
            break
        if output.kind == "unsupported":
            if pending and pending.task_type is not TaskType.CLARIFICATION:
                return {
                    "final_answer": CAPABILITY_MESSAGE
                    + " 请继续原目标，或使用 new_task 开始新目标。",
                    "task_status": TaskStatus.NEEDS_INPUT,
                    "model_call_usage": asdict(scope.model_usage()),
                }
            return {
                "final_answer": CAPABILITY_MESSAGE,
                "task_status": TaskStatus.REJECTED,
                "pending_task": None,
                "model_call_usage": asdict(scope.model_usage()),
            }
        decision = output.decision
        if pending and pending.task_type is not TaskType.CLARIFICATION:
            if decision.task_type is not pending.task_type:
                return {
                    "final_answer": "请继续补充原任务信息，或使用 new_task 开始新目标。",
                    "task_status": TaskStatus.NEEDS_INPUT,
                    "model_call_usage": asdict(scope.model_usage()),
                }
            decision = decision.model_copy(
                update={
                    "task_goal": pending.task_goal,
                    "entities": {**pending.entities, **decision.entities},
                }
            )
        return {
            **apply_route_decision(state, decision),
            "model_call_usage": asdict(scope.model_usage()),
        }

    return supervisor_node


def _failure(code, scope):
    return {
        "task_status": TaskStatus.FAILED,
        "final_answer": None,
        "error": {"code": code, "message": "Model routing failed."},
        "model_call_usage": asdict(scope.model_usage()),
    }
