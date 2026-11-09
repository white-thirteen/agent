"""Supervisor 图节点：识别用户任务、补全待补上下文并给出受约束的路由决定。

Supervisor 只负责调度，不直接调用订单/退款/知识工具。它将模型的结构化输出
转换为主图 State 更新，后续由条件边选择澄清节点或专业 Agent。
"""

from collections.abc import Awaitable, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from app.agents.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT
from app.graph.contracts import GraphProtocolError, PendingTask, RouteDecision
from app.graph.state import AgentState, RouteUpdate
from app.graph.transfers import apply_route_decision

PredictRoute = Callable[[list[SystemMessage | HumanMessage]], Awaitable[RouteDecision]]


def make_supervisor_node(predict_route: PredictRoute):
    """构造 Supervisor 节点，并注入模型预测函数以隔离模型调用与路由逻辑。

    节点本身只依赖 predict_route，便于在图构建时绑定真实模型，同时让任务续接、
    决定校验和 State 更新保持为独立且可读的流程。
    """

    async def supervisor_node(state: AgentState) -> RouteUpdate:
        # 每次模型调用都带上固定职责说明；业务决定由结构化输出约束，而不是自由文本解析。
        messages: list[SystemMessage | HumanMessage] = [
            SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)
        ]
        pending = state.get("pending_task")
        if pending is not None:
            # Checkpoint 中的待补任务是跨轮续接依据；先确认它仍属于当前用户会话和任务。
            pending = PendingTask.model_validate(pending)
            _ensure_pending_matches_state(state, pending)
            messages.append(
                SystemMessage(
                    content=(
                        "Continue this saved task. Keep its task type and goal. "
                        "Use its existing entities, then ask only for missing information.\n"
                        f"Saved task: {pending.model_dump_json()}"
                    )
                )
            )
        # 只将用户消息作为本次意图输入；工具记录和 Supervisor 内部信息不送入路由模型。
        for message in state["messages"]:
            if isinstance(message, HumanMessage):
                messages.append(HumanMessage(content=message.content))

        # 即使模型返回了合法 JSON，也要按 RouteDecision 校验任务/Agent 归属和澄清字段。
        decision = RouteDecision.model_validate(await predict_route(messages))
        if pending is not None:
            # 用户补充信息不能把原任务悄悄改成另一种业务；实体允许用新值覆盖旧候选值。
            if decision.task_type is not pending.task_type:
                raise GraphProtocolError("Supervisor changed the pending task type")
            decision = RouteDecision.model_validate(
                {
                    **decision.model_dump(),
                    "agent_type": pending.task_type.target_agent,
                    "task_type": pending.task_type,
                    "task_goal": pending.task_goal,
                    "entities": {**pending.entities, **decision.entities},
                }
            )
        return apply_route_decision(state, decision)

    return supervisor_node


def make_structured_predictor(model: Runnable):
    """将 LangChain 模型绑定到 RouteDecision Schema，统一产出可校验的 Python 对象。"""
    structured_model = model.with_structured_output(RouteDecision)

    async def predict(messages: list[SystemMessage | HumanMessage]) -> RouteDecision:
        return RouteDecision.model_validate(await structured_model.ainvoke(messages))

    return predict


def _ensure_pending_matches_state(state: AgentState, pending: PendingTask) -> None:
    """拒绝将 Checkpoint 中其他用户、会话、工作流或任务的待补内容拼入当前请求。"""
    for field in ("user_id", "conversation_id", "workflow_id", "task_id"):
        if state.get(field) != getattr(pending, field):
            raise GraphProtocolError("Pending task does not match the current graph state")
