"""Validated, bounded destinations for the edge after SupervisorNode."""

from typing import Literal

from app.agents.types import AgentType
from app.graph.contracts import GraphProtocolError, ResultStatus, RouteDecision, SpecialistResult
from app.graph.state import AgentState

RouteTarget = Literal["order", "refund", "knowledge", "clarification", "response", "run_finish"]
SpecialistRouteTarget = Literal["clarification", "result_aggregator"]


def validated_route(state: AgentState) -> RouteDecision:
    """重新校验 Supervisor 决定及其 State 镜像字段，避免按不一致状态分派。"""
    decision = state.get("route_decision")
    if decision is None:
        raise GraphProtocolError("Supervisor must provide a route decision before dispatch")
    decision = RouteDecision.model_validate(decision)
    for field in ("agent_type", "task_type", "task_goal"):
        if state.get(field) != getattr(decision, field):
            raise GraphProtocolError(f"Route decision conflicts with the parent {field} channel")
    return decision


def route_after_supervisor(state: AgentState) -> RouteTarget:
    """将已验证决定映射到有限节点集合；条件边不调用模型，也不执行工具。"""
    if state.get("error"):
        return "run_finish"
    if state.get("final_answer"):
        return "response"
    decision = validated_route(state)
    if decision.needs_clarification:
        return "clarification"
    match decision.agent_type:
        case AgentType.ORDER:
            return "order"
        case AgentType.REFUND:
            return "refund"
        case AgentType.KNOWLEDGE:
            return "knowledge"
        case _:
            raise GraphProtocolError("The selected agent has no executable specialist branch")


def route_after_specialist(state: AgentState) -> SpecialistRouteTarget:
    """需要补充信息的结果转澄清，其余结果交给统一汇总节点。"""
    result = state.get("specialist_result")
    if result is None:
        raise GraphProtocolError("Specialist must provide a result before dispatch")
    result = SpecialistResult.model_validate(result)
    if result.status is ResultStatus.NEEDS_INPUT:
        return "clarification"
    return "result_aggregator"
