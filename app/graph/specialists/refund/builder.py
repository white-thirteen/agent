"""Refund specialist: original tool call, durable approval gate and guarded execution."""

from dataclasses import asdict
from uuid import NAMESPACE_URL, uuid5

import psycopg
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from psycopg_pool import PoolClosed, PoolTimeout

from app.agents.types import AgentType, TaskType
from app.domain.refunds import (
    OriginalRefundCall,
    RefundBusinessContext,
    RefundRejected,
    canonical_digest,
)
from app.graph.contracts import (
    FailureDetails,
    GraphProtocolError,
    SpecialistInput,
    SpecialistResult,
)
from app.graph.specialists.preferences import preference_instructions, read_optional_preferences
from app.graph.state import SpecialistState
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import ModelCallContext, ModelCallError
from app.tools.messages import parse_tool_calls, to_tool_message
from app.tools.models import (
    ParsedToolCall,
    PolicyDecision,
    PreparedToolAttempt,
    ToolExecutionContext,
    ToolExecutionResult,
)
from app.workflows.approvals import ApprovalError, ApprovalReference, InterruptBinding


class RefundState(SpecialistState, total=False):
    order_id: str
    order_facts: dict
    eligibility: dict
    original_ai_message: object
    pending_refund_call: dict
    canonical_args: dict
    tool_version: str
    application_id: str
    operation_id: str
    approval_id: str
    subject_digest: str
    application: dict
    prepared_attempt: PreparedToolAttempt | None
    execution_result: dict | None
    outcome: str | None
    error_code: str | None
    question: str | None
    gate_state: str | None
    tool_result: ToolExecutionResult | None


def build_refund_graph(*, gateway, registry, executor, approval_service, refund_service):
    """Compile one task-local graph; its child checkpoints inherit the parent Saver."""

    def usage(runtime):
        return {
            "model_call_usage": asdict(runtime.context.scope.model_usage()),
            "run_usage": asdict(runtime.context.scope.run_usage()),
        }

    def original(state):
        call = state["pending_refund_call"]
        return OriginalRefundCall(
            call["call_id"],
            call["name"],
            state["tool_version"],
            call["raw_args"],
            state["canonical_args"],
        )

    def business(state, runtime):
        ctx = runtime.context.context
        return RefundBusinessContext(
            ctx.user_id,
            ctx.task_id,
            ctx.run_id,
            ctx.conversation_id,
            runtime.context.thread_id,
            ctx.workflow_id,
            state["operation_id"],
            state["application_id"],
            state["approval_id"],
            original(state).call_digest(),
        )

    def tool_context(state, runtime, name, node, args, *, binding=None):
        definition = registry.get(name)
        if definition is None:
            raise GraphProtocolError("Required refund tool unavailable")
        origin = "model" if node is None else "node"
        return ToolExecutionContext(
            runtime.context.context,
            AgentType.REFUND,
            TaskType.REFUND_APPLY,
            node,
            runtime.context.permission_scopes,
            origin,
            frozenset({(name, definition.metadata.version)}),
            {name: args},
            runtime.context.scope.limits,
            runtime.context.scope,
            business(state, runtime) if state.get("operation_id") else None,
            binding,
        )

    async def invoke_node(state, runtime, name, node, args):
        call_id = "node:" + str(
            uuid5(NAMESPACE_URL, f"{runtime.context.context.task_id}:{node}:{name}")
        )
        call = ParsedToolCall(call_id, name, args)
        result = await executor.execute(
            call, context=tool_context(state, runtime, name, node, args)
        )
        if result.status != "success":
            status = (
                "rejected"
                if result.status in ("business_rejected", "policy_denied")
                and result.code != "tool_budget_exceeded"
                else "failed"
            )
            return None, {"outcome": status, "error_code": result.code, **usage(runtime)}
        return result.data, None

    def guard(state, runtime):
        recovery = runtime.context.refund_recovery
        if recovery is None:
            return None
        ctx = runtime.context.context
        if (
            runtime.context.execution_mode != "reconcile"
            or recovery.thread_id != runtime.context.thread_id
            or recovery.task_id != ctx.task_id
            or recovery.workflow_id != ctx.workflow_id
            or recovery.application_id != state["application_id"]
            or recovery.approval_id != state["approval_id"]
            or recovery.operation_id != state["operation_id"]
            or recovery.call_id != state["pending_refund_call"]["call_id"]
            or recovery.expected_call_digest != original(state).call_digest()
        ):
            raise GraphProtocolError("Refund recovery association mismatch")
        if recovery.disposition == "unknown":
            raise GraphProtocolError("Refund recovery result remains uncertain")
        if recovery.disposition == "succeeded":
            fact = recovery.committed_result
            expected = {
                "operation_id": state["operation_id"],
                "order_id": state["order_id"],
                "amount": state["application"]["amount"],
                "currency": state["application"]["currency"],
                "simulated": True,
            }
            if fact != expected:
                raise GraphProtocolError("Refund recovery result mismatch")
            return {"execution_result": fact, "outcome": "completed", **usage(runtime)}
        return None

    def check_request(state, runtime):
        request = SpecialistInput.model_validate(state["request"])
        if (
            request.agent_type is not AgentType.REFUND
            or request.task_type is not TaskType.REFUND_APPLY
            or request.context != runtime.context.context
        ):
            raise GraphProtocolError("Refund request association mismatch")
        return {
            "outcome": None,
            "error_code": None,
            "prepared_attempt": None,
            "execution_result": None,
        }

    def prepare_refund_core(state):
        order_id = state["request"].entities.get("order_id")
        if not isinstance(order_id, str) or not order_id.strip():
            return {"outcome": "needs_input", "question": "请提供需要申请模拟退款的订单号。"}
        return {"order_id": order_id.strip()}

    async def prepare_refund(state, runtime):
        update = await read_optional_preferences(
            state, runtime, registry=registry, executor=executor, node="prepare_refund"
        )
        if update.get("outcome"):
            return update
        return {**update, **prepare_refund_core(state)}

    async def load_order(state, runtime):
        result, error = await invoke_node(
            state, runtime, "get_order", "load_order", {"order_id": state["order_id"]}
        )
        return error or {"order_facts": result["order"], **usage(runtime)}

    async def check_eligibility(state, runtime):
        result, error = await invoke_node(
            state,
            runtime,
            "check_refund_eligibility",
            "check_eligibility",
            {"order_id": state["order_id"]},
        )
        return error or {"eligibility": result, **usage(runtime)}

    async def plan_refund_call(state, runtime):
        views = registry.list(
            agent_type=AgentType.REFUND, permission_scopes=runtime.context.permission_scopes
        )
        schemas = [view.model_schema for view in views if view.metadata.name == "refund_order"]
        if len(schemas) != 1:
            return {"outcome": "failed", "error_code": "capability_unavailable"}
        try:
            result = await gateway.invoke(
                [
                    SystemMessage(
                        content="请求退款时必须调用所提供的模拟退款工具；只使用指定订单号："
                        + state["order_id"]
                    ),
                    *state["messages"],
                ],
                context=ModelCallContext(
                    runtime.context.context.run_id,
                    runtime.context.context.task_id,
                    AgentType.REFUND,
                ),
                model_usage=runtime.context.scope.model_usage(),
                tools=schemas,
            )
            runtime.context.scope.adopt_model_usage(result.model_usage)
        except ModelCallError as error:
            runtime.context.scope.adopt_model_usage(error.model_usage)
            return {"outcome": "failed", "error_code": error.code, **usage(runtime)}
        try:
            calls = parse_tool_calls(result.message, used_ids=set(), max_calls=1)
        except ValueError:
            return {"outcome": "failed", "error_code": "invalid_tool_call", **usage(runtime)}
        if len(calls) != 1 or calls[0].name != "refund_order":
            return {"outcome": "failed", "error_code": "invalid_tool_call", **usage(runtime)}
        call = calls[0]
        ctx = tool_context(state, runtime, "refund_order", None, {"order_id": state["order_id"]})
        evaluation = await executor.assess(call, context=ctx)
        if evaluation.decision is not PolicyDecision.REQUIRE_APPROVAL:
            return {"outcome": "failed", "error_code": evaluation.code, **usage(runtime)}
        version = registry.get("refund_order").metadata.version
        key = f"{runtime.context.context.task_id}:{call.call_id}:refund_order:{version}"
        return {
            "messages": [result.message],
            "original_ai_message": result.message,
            "pending_refund_call": asdict(call),
            "canonical_args": evaluation.validated_args.model_dump(mode="json"),
            "tool_version": registry.get("refund_order").metadata.version,
            "operation_id": str(uuid5(NAMESPACE_URL, "operation:" + key)),
            "application_id": str(uuid5(NAMESPACE_URL, "application:" + key)),
            "approval_id": str(uuid5(NAMESPACE_URL, "approval:" + key)),
            **usage(runtime),
        }

    async def prepare_application(state, runtime):
        args = {
            "call_id": state["pending_refund_call"]["call_id"],
            "tool_name": "refund_order",
            "tool_version": state["tool_version"],
            "raw_args": state["pending_refund_call"]["raw_args"],
            "canonical_args": state["canonical_args"],
        }
        result, error = await invoke_node(
            state, runtime, "prepare_refund_application", "prepare_application", args
        )
        return error or {"application": result, **usage(runtime)}

    async def review_policy(state, runtime):
        call = ParsedToolCall(**state["pending_refund_call"])
        evaluated = await executor.assess(
            call,
            context=tool_context(state, runtime, "refund_order", None, state["canonical_args"]),
        )
        if evaluated.decision is not PolicyDecision.REQUIRE_APPROVAL:
            return {"outcome": "rejected", "error_code": evaluated.code, **usage(runtime)}
        return usage(runtime)

    async def persist_approval(state, runtime):
        ctx = runtime.context.context
        subject = {
            "application_id": state["application_id"],
            "operation_id": state["operation_id"],
            "user_id": ctx.user_id,
            "conversation_id": ctx.conversation_id,
            "thread_id": runtime.context.thread_id,
            "task_id": ctx.task_id,
            "workflow_id": ctx.workflow_id,
            "call_id": state["pending_refund_call"]["call_id"],
            "tool_name": "refund_order",
            "tool_version": state["tool_version"],
            "canonical_args": state["canonical_args"],
            "args_digest": canonical_digest(state["canonical_args"]),
            "amount": state["application"]["amount"],
            "currency": state["application"]["currency"],
        }
        result, error = await invoke_node(
            state, runtime, "register_refund_approval", "persist_approval", {"subject": subject}
        )
        return error or {"subject_digest": result["subject_digest"], **usage(runtime)}

    def prepare_approval_wait(state, runtime):
        runtime.context.scope.finish_active_period()
        return usage(runtime)

    async def approval_gate(state, runtime):
        reference = interrupt(
            {
                "kind": "refund_approval",
                "approval_id": state["approval_id"],
                "application_id": state["application_id"],
                "operation_id": state["operation_id"],
                "subject_digest": state["subject_digest"],
            }
        )
        if not isinstance(reference, dict) or reference.get("approval_id") != state["approval_id"]:
            raise GraphProtocolError("Approval reference mismatch")
        row = await approval_service.get(state["approval_id"])
        if not row or row["subject_digest"] != state["subject_digest"]:
            raise GraphProtocolError("Approval subject mismatch")
        if row["decision"] == "APPROVED" and row["expires_at"] > row["db_now"]:
            binding = InterruptBinding(
                row["interrupt_id"], row["checkpoint_ns"], row["checkpoint_id"]
            )
            try:
                await approval_service.verify_for_call(
                    ApprovalReference(state["approval_id"]),
                    original_call=original(state),
                    context=business(state, runtime),
                    interrupt_binding=binding,
                )
            except ApprovalError:
                return {"outcome": "failed", "error_code": "approval_not_valid", **usage(runtime)}
            return {"gate_state": "approved", **usage(runtime)}
        if row["decision"] in ("REJECTED", "EXPIRED") or (
            row["decision"] == "APPROVED" and row["expires_at"] <= row["db_now"]
        ):
            return {"gate_state": "rejected", **usage(runtime)}
        return {"outcome": "failed", "error_code": "approval_pending", **usage(runtime)}

    async def recheck_execution(state, runtime):
        recovered = guard(state, runtime)
        if recovered:
            return recovered
        result, error = await invoke_node(
            state,
            runtime,
            "check_refund_eligibility",
            "recheck_execution",
            {"order_id": state["order_id"]},
        )
        if error:
            return error
        if result.get("status") == "SUCCEEDED":
            return {
                "execution_result": result["execution_result"],
                "outcome": "completed",
                **usage(runtime),
            }
        return usage(runtime)

    async def current_binding(state):
        row = await approval_service.get(state["approval_id"])
        if not row or row["subject_digest"] != state["subject_digest"]:
            raise GraphProtocolError("Approval binding unavailable")
        return InterruptBinding(row["interrupt_id"], row["checkpoint_ns"], row["checkpoint_id"])

    async def prepare_refund_attempt(state, runtime):
        recovered = guard(state, runtime)
        if recovered:
            return recovered
        if runtime.context.refund_recovery is not None:
            result, error = await invoke_node(
                state,
                runtime,
                "check_refund_eligibility",
                "recheck_execution",
                {"order_id": state["order_id"]},
            )
            if error:
                return error
            if result.get("status") == "SUCCEEDED":
                return {
                    "execution_result": result["execution_result"],
                    "outcome": "completed",
                    **usage(runtime),
                }
        call = ParsedToolCall(**state["pending_refund_call"])
        binding = await current_binding(state)
        result = await executor.prepare_attempt(
            call,
            context=tool_context(
                state, runtime, "refund_order", None, state["canonical_args"], binding=binding
            ),
        )
        if not isinstance(result, PreparedToolAttempt):
            return {"outcome": "failed", "error_code": result.code, **usage(runtime)}
        return {"prepared_attempt": result, **usage(runtime)}

    async def execute_refund(state, runtime):
        recovered = guard(state, runtime)
        if recovered:
            return recovered
        marker = state.get("prepared_attempt")
        if (
            not isinstance(marker, PreparedToolAttempt)
            or marker.run_id != runtime.context.context.run_id
        ):
            if (
                runtime.context.refund_recovery
                and runtime.context.refund_recovery.disposition == "not_executed"
            ):
                return {"prepared_attempt": None, **usage(runtime)}
            return {"outcome": "failed", "error_code": "execution_uncertain", **usage(runtime)}
        binding = await current_binding(state)
        result = await executor.execute_prepared(
            marker,
            context=tool_context(
                state, runtime, "refund_order", None, state["canonical_args"], binding=binding
            ),
        )
        if result.status == "success":
            return {
                "tool_result": result,
                "execution_result": result.data,
                "outcome": "completed",
                **usage(runtime),
            }
        if result.effect_status == "unknown":
            return {"outcome": "uncertain", "error_code": "execution_uncertain", **usage(runtime)}
        return {
            "tool_result": result,
            "outcome": "rejected"
            if result.status in ("business_rejected", "policy_denied")
            else "failed",
            "error_code": result.code,
            **usage(runtime),
        }

    async def reconcile_operation(state, runtime):
        recovered = guard(state, runtime)
        if recovered:
            return recovered
        try:
            operation = await refund_service.get_operation(
                user_id=runtime.context.context.user_id, operation_id=state["operation_id"]
            )
        except (RefundRejected, psycopg.Error, PoolClosed, PoolTimeout):
            operation = None
        if operation and operation.get("status") == "SUCCEEDED":
            fact = operation.get("execution_result")
            if (
                str(operation.get("application_id")) != state["application_id"]
                or not fact
                or fact.get("operation_id") != state["operation_id"]
                or fact.get("order_id") != state["order_id"]
                or fact.get("amount") != state["application"]["amount"]
                or fact.get("currency") != state["application"]["currency"]
                or fact.get("simulated") is not True
            ):
                raise GraphProtocolError("Refund operation result mismatch")
            return {"outcome": "completed", "execution_result": fact, **usage(runtime)}
        # Keep this node pending so the original operation can be reconciled later.
        raise GraphProtocolError("Refund execution result remains uncertain")

    def record_tool_outcome(state, runtime):
        recovered = guard(state, runtime)
        if recovered and recovered.get("outcome") == "failed":
            return recovered
        fact = (recovered or {}).get("execution_result") or state.get("execution_result")
        if not fact:
            return {"outcome": "failed", "error_code": "execution_uncertain", **usage(runtime)}
        result = (None if recovered else state.get("tool_result")) or ToolExecutionResult(
            state["pending_refund_call"]["call_id"],
            "refund_order",
            "reused",
            "success",
            "ok",
            "Refund succeeded.",
            fact,
            0,
            runtime.context.scope.run_usage(),
            "completed",
        )
        return {
            "execution_result": fact,
            "messages": [to_tool_message(result, task_id=runtime.context.context.task_id)],
            "outcome": "completed",
            **usage(runtime),
        }

    async def record_rejection(state, runtime):
        recovered = guard(state, runtime)
        if recovered:
            return recovered
        _, error = await invoke_node(
            state,
            runtime,
            "close_refund_application",
            "record_rejection",
            {"reason_code": "approval_rejected"},
        )
        result = ToolExecutionResult(
            state["pending_refund_call"]["call_id"],
            "refund_order",
            "rejected",
            "failed" if error else "business_rejected",
            error["error_code"] if error else "approval_rejected",
            "Refund could not be completed." if error else "Refund was not approved.",
            None,
            0,
            runtime.context.scope.run_usage(),
            "not_started",
        )
        return {
            "messages": [to_tool_message(result, task_id=runtime.context.context.task_id)],
            "outcome": "rejected",
            **usage(runtime),
            **(error or {}),
        }

    async def compose_refund_reply(state, runtime):
        recovered = guard(state, runtime)
        if recovered and recovered.get("outcome") == "failed":
            return recovered
        recovery = runtime.context.refund_recovery
        if runtime.context.scope.remaining_active_seconds() <= 0 or (
            recovery is not None and not recovery.allow_model
        ):
            return {**(recovered or {}), **usage(runtime)}
        messages = list(state["messages"])
        call = state.get("pending_refund_call")
        closure = None
        if call and not any(
            isinstance(message, ToolMessage) and message.tool_call_id == call["call_id"]
            for message in messages
        ):
            fact = (recovered or {}).get("execution_result") or state.get("execution_result")
            result = ToolExecutionResult(
                call["call_id"],
                call["name"],
                "closed",
                "success" if fact else "failed",
                "ok" if fact else state.get("error_code") or "refund_unavailable",
                "Refund succeeded." if fact else "Refund was not completed.",
                fact,
                0,
                runtime.context.scope.run_usage(),
                "completed" if fact else "not_started",
            )
            closure = to_tool_message(result, task_id=runtime.context.context.task_id)
            messages.append(closure)
        try:
            result = await gateway.invoke(
                [
                    SystemMessage(
                        content="简短结束本次模拟退款流程，不补充未提供的事实。"
                        + preference_instructions(state)
                    ),
                    *messages,
                ],
                context=ModelCallContext(
                    runtime.context.context.run_id,
                    runtime.context.context.task_id,
                    AgentType.REFUND,
                ),
                model_usage=runtime.context.scope.model_usage(),
            )
            runtime.context.scope.adopt_model_usage(result.model_usage)
        except ModelCallError as error:
            runtime.context.scope.adopt_model_usage(error.model_usage)
            return {
                **(recovered or {}),
                "outcome": "failed",
                "error_code": error.code,
                **({"messages": [closure]} if closure else {}),
                **usage(runtime),
            }
        return {
            **(recovered or {}),
            **({"messages": [closure]} if closure else {}),
            **usage(runtime),
        }

    def map_result(state, runtime):
        recovered = (
            guard(state, runtime)
            if state.get("approval_id") and state.get("subject_digest")
            else None
        )
        ctx = runtime.context.context
        outcome = (recovered or {}).get("outcome") or state.get("outcome") or "failed"
        fact = (recovered or {}).get("execution_result") or state.get("execution_result")
        if recovered and recovered.get("error_code") == "execution_uncertain":
            fact = None
        if fact and state.get("outcome") == "failed":
            outcome = "failed"
        data = {
            "workflow_id": ctx.workflow_id,
            "task_id": ctx.task_id,
            "run_id": ctx.run_id,
            "agent_type": AgentType.REFUND,
            "task_type": TaskType.REFUND_APPLY,
            "status": outcome,
            "summary": "模拟退款未完成。",
        }
        if outcome == "needs_input":
            data.update(
                summary=state["question"],
                clarification_question=state["question"],
                missing_fields=["order_id"],
            )
        elif outcome == "completed" and fact:
            data.update(
                summary=(
                    f"模拟退款已完成：{fact['order_id']}，{fact['amount']} {fact['currency']}。"
                ),
                facts=fact,
                operation_id=state["operation_id"],
                approval_id=state["approval_id"],
            )
        elif outcome == "rejected":
            data.update(
                summary="模拟退款未获批准或不符合条件。",
                operation_id=state.get("operation_id"),
                approval_id=state.get("approval_id"),
            )
        else:
            if fact:
                data.update(
                    summary="模拟退款已完成，但本次回复未能生成。",
                    facts=fact,
                    operation_id=state.get("operation_id"),
                    approval_id=state.get("approval_id"),
                )
            data.update(
                status="failed",
                error=FailureDetails(
                    code=state.get("error_code") or "refund_unavailable",
                    message="Refund could not be completed.",
                ),
            )
        update = {"result": SpecialistResult(**data), **usage(runtime)}
        call = state.get("pending_refund_call")
        if call and not any(
            isinstance(message, ToolMessage) and message.tool_call_id == call["call_id"]
            for message in state["messages"]
        ):
            result = ToolExecutionResult(
                call["call_id"],
                call["name"],
                "closed",
                "success" if fact else "failed",
                "ok" if fact else state.get("error_code") or "refund_unavailable",
                "Refund succeeded." if fact else "Refund was not completed.",
                fact,
                0,
                runtime.context.scope.run_usage(),
                "completed" if fact else "not_started",
            )
            update["messages"] = [to_tool_message(result, task_id=ctx.task_id)]
        return update

    graph = StateGraph(RefundState, context_schema=RunExecutionContext)
    nodes = [
        check_request,
        prepare_refund,
        load_order,
        check_eligibility,
        plan_refund_call,
        prepare_application,
        review_policy,
        persist_approval,
        prepare_approval_wait,
        approval_gate,
        recheck_execution,
        prepare_refund_attempt,
        execute_refund,
        reconcile_operation,
        record_tool_outcome,
        record_rejection,
        compose_refund_reply,
        map_result,
    ]
    for node in nodes:
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "check_request")
    graph.add_edge("check_request", "prepare_refund")

    def route_normal(next_node):
        return lambda state: "map_result" if state.get("outcome") else next_node

    for source, target in [
        ("prepare_refund", "load_order"),
        ("load_order", "check_eligibility"),
        ("check_eligibility", "plan_refund_call"),
        ("plan_refund_call", "prepare_application"),
        ("prepare_application", "review_policy"),
        ("persist_approval", "prepare_approval_wait"),
    ]:
        graph.add_conditional_edges(
            source, route_normal(target), {"map_result": "map_result", target: target}
        )
    graph.add_edge("prepare_approval_wait", "approval_gate")
    graph.add_conditional_edges(
        "review_policy",
        lambda s: "record_rejection" if s.get("outcome") == "rejected" else "persist_approval",
        {"record_rejection": "record_rejection", "persist_approval": "persist_approval"},
    )
    graph.add_conditional_edges(
        "approval_gate",
        lambda s: (
            "map_result"
            if s.get("outcome")
            else "recheck_execution"
            if s["gate_state"] == "approved"
            else "record_rejection"
        ),
        {
            "map_result": "map_result",
            "recheck_execution": "recheck_execution",
            "record_rejection": "record_rejection",
        },
    )

    def after_recheck(s):
        return (
            "record_tool_outcome"
            if s.get("outcome") == "completed"
            else "record_rejection"
            if s.get("outcome") == "rejected"
            else "map_result"
            if s.get("outcome")
            else "prepare_refund_attempt"
        )

    graph.add_conditional_edges(
        "recheck_execution",
        after_recheck,
        {
            "record_tool_outcome": "record_tool_outcome",
            "record_rejection": "record_rejection",
            "map_result": "map_result",
            "prepare_refund_attempt": "prepare_refund_attempt",
        },
    )
    graph.add_conditional_edges(
        "prepare_refund_attempt",
        lambda s: (
            "record_tool_outcome"
            if s.get("outcome") == "completed"
            else "record_rejection"
            if s.get("outcome") == "rejected"
            else "map_result"
            if s.get("outcome")
            else "execute_refund"
        ),
        {
            "record_tool_outcome": "record_tool_outcome",
            "record_rejection": "record_rejection",
            "map_result": "map_result",
            "execute_refund": "execute_refund",
        },
    )
    graph.add_conditional_edges(
        "execute_refund",
        lambda s: (
            "record_tool_outcome"
            if s.get("outcome") == "completed"
            else "reconcile_operation"
            if s.get("outcome") == "uncertain"
            else "record_rejection"
            if s.get("outcome") == "rejected"
            else "map_result"
            if s.get("outcome")
            else "recheck_execution"
        ),
        {
            "record_tool_outcome": "record_tool_outcome",
            "reconcile_operation": "reconcile_operation",
            "record_rejection": "record_rejection",
            "map_result": "map_result",
            "prepare_refund_attempt": "prepare_refund_attempt",
            "recheck_execution": "recheck_execution",
        },
    )
    graph.add_conditional_edges(
        "reconcile_operation",
        lambda s: "record_tool_outcome" if s.get("outcome") == "completed" else "map_result",
        {"record_tool_outcome": "record_tool_outcome", "map_result": "map_result"},
    )
    graph.add_edge("record_tool_outcome", "compose_refund_reply")
    graph.add_conditional_edges(
        "record_rejection",
        lambda s: (
            "record_tool_outcome"
            if s.get("outcome") == "completed"
            else "map_result"
            if s.get("outcome") == "failed"
            else "compose_refund_reply"
        ),
        {
            "record_tool_outcome": "record_tool_outcome",
            "map_result": "map_result",
            "compose_refund_reply": "compose_refund_reply",
        },
    )
    graph.add_edge("compose_refund_reply", "map_result")
    graph.add_edge("map_result", END)
    return graph.compile()
