"""将主图路由或专业子图提出的补充问题写入本轮最终回复。"""

from app.graph.contracts import GraphProtocolError
from app.graph.state import AgentState


def clarification_node(state: AgentState) -> dict[str, str]:
    """读取待补任务上的问题；Supervisor 初始澄清则读取本轮路由决定。

    两种澄清最终都进入 ResponseNode 写入公共历史，pending_task 留在主状态中，
    供下一轮 Runtime 从 Checkpoint 取出并交给 Supervisor 续接。
    """
    pending = state.get("pending_task")
    if pending is not None:
        question = pending.clarification_question
    else:
        decision = state.get("route_decision")
        question = decision.clarification_question if decision is not None else None

    if not question:
        raise GraphProtocolError("Clarification requires a saved question")
    return {"final_answer": question}
