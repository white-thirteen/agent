"""Gateway routing, bounded structural correction and two kinds of clarification."""

import re
from dataclasses import asdict

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.agents.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT
from app.agents.types import AgentType, TaskType
from app.graph.contracts import GraphProtocolError, NewSupervisorOutput, PendingTask
from app.graph.state import AgentState
from app.graph.transfers import apply_route_decision, public_task_messages
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import ModelCallContext, ModelCallError
from app.runtime.models import TaskStatus

CAPABILITY_MESSAGE = (
    "演示范围包括本人订单查询、模拟退款申请、知识问答和两项偏好管理。该操作不受支持。"
)


def make_supervisor_node(gateway):
    async def route_node(state: AgentState, runtime: Runtime[RunExecutionContext]):
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
        from app.graph.specialists.knowledge.memory import parse_explicit_memory_command

        humans = [m for m in public_task_messages(state) if isinstance(m, HumanMessage)]
        if (
            humans
            and isinstance(humans[-1].content, str)
            and parse_explicit_memory_command(humans[-1].content)
        ):
            return {
                "final_answer": (
                    "偏好管理已迁移，请使用 /agent/preferences/read 或 "
                    "/agent/preferences/mutations 接口。"
                ),
                "task_status": TaskStatus.NEEDS_INPUT if pending else TaskStatus.REJECTED,
                "model_call_usage": asdict(scope.model_usage()),
            }
        messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)]
        if pending:
            messages.append(
                SystemMessage(content="Trusted pending task: " + pending.model_dump_json())
            )
        messages.extend(public_task_messages(state))
        model_context = ModelCallContext(
            state["run_id"],
            state["task_id"],
            AgentType.SUPERVISOR,
            history=tuple(
                tuple(i)
                for i in (
                    scope.context_history_override
                    if scope.context_history_override is not None
                    else state.get("context_history", [])
                )
            ),
            on_context_view=scope.record_context_view,
            on_context_usage=scope.record_context_usage,
            on_compact=execution.context_compactor,
            before_attempt=scope.reserve_model_attempt,
            current_usage=scope.model_usage,
        )
        for correction in range(2):
            try:
                result = await gateway.invoke_structured(
                    messages,
                    schema=NewSupervisorOutput,
                    context=model_context,
                    model_usage=scope.model_usage(),
                )
                scope.adopt_model_usage(result.model_usage)
                output = NewSupervisorOutput.model_validate(result.parsed.model_dump())
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
        if decision.task_type is TaskType.REFUND_APPLY:
            order_id = decision.entities.get("order_id")
            if isinstance(order_id, str) and not any(
                re.search(
                    r"(?<![A-Za-z0-9_-])" + re.escape(order_id) + r"(?![A-Za-z0-9_-])",
                    message.content,
                )
                for message in humans
                if order_id.strip() and isinstance(message.content, str)
            ):
                # Background is never authority to select a refund target.
                decision = decision.model_copy(
                    update={
                        "entities": {k: v for k, v in decision.entities.items() if k != "order_id"},
                        "needs_clarification": True,
                        "missing_fields": ["order_id"],
                        "clarification_question": "请提供需要申请模拟退款的订单号。",
                    }
                )
        return {
            **apply_route_decision(state, decision),
            "model_call_usage": asdict(scope.model_usage()),
            "context_view": scope.context_view,
        }

    async def supervisor_node(state: AgentState, runtime: Runtime[RunExecutionContext]):
        plan = runtime.context.context_adoption
        update = {}
        if plan is not None and runtime.context.execution_mode == "normal":
            ref = state.get("context_ref")
            base = ref.get("revision") if ref else None
            if base == plan["revision"]:
                if (
                    ref.get("summary_id") != plan["summary_id"]
                    or any(m.id in plan["message_ids"] for m in state["messages"])
                    or any(
                        i in state.get("public_message_metadata", {}) for i in plan["message_ids"]
                    )
                ):
                    raise GraphProtocolError("Applied context revision is inconsistent")
                result = await route_node(state, runtime)
                if runtime.context.scope.context_history_override is not None:
                    result["context_history"] = runtime.context.scope.context_history_override
                return result
            hot = state["messages"][: len(plan["messages"])]
            actual = [
                (
                    m.id,
                    "user"
                    if type(m) is HumanMessage
                    else "assistant"
                    if type(m) is AIMessage
                    else "other",
                    m.content,
                )
                for m in hot
            ]
            if base != plan["base_revision"] or actual != plan["messages"]:
                raise GraphProtocolError("Context adoption source changed")
            metadata = dict(state.get("public_message_metadata", {}))
            for message_id in plan["message_ids"]:
                metadata.pop(message_id, None)
            update = {
                "context_ref": {"revision": plan["revision"], "summary_id": plan["summary_id"]},
                "messages": [RemoveMessage(id=message_id) for message_id in plan["message_ids"]],
                "public_message_metadata": metadata,
            }
        result = await route_node(state, runtime)
        if runtime.context.scope.context_history_override is not None:
            result["context_history"] = runtime.context.scope.context_history_override
        return {**result, **update}

    return supervisor_node


def _failure(code, scope):
    return {
        "task_status": TaskStatus.FAILED,
        "final_answer": None,
        "error": {"code": code, "message": "Model routing failed."},
        "model_call_usage": asdict(scope.model_usage()),
    }
