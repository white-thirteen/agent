"""构建并编译 Supervisor 主图；应用启动时调用一次，复用其拓扑和 Checkpointer。"""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.graph.contracts import GraphProtocolError
from app.graph.nodes.clarification import clarification_node
from app.graph.nodes.response import response_node
from app.graph.nodes.result_aggregator import result_aggregator_node
from app.graph.nodes.specialist import make_specialist_node
from app.graph.nodes.supervisor import make_structured_predictor, make_supervisor_node
from app.graph.router import route_after_specialist, route_after_supervisor
from app.graph.state import AgentState


def build_supervisor_graph(model, specialists=None):
    """创建 Supervisor → 条件路由 → 澄清/专业分支的主图。

    已编译的专业子图可通过 specialists 注入；未注入的分支明确失败，不伪造业务结果。
    InMemorySaver 只在当前进程内保存会话快照，服务重启后不会保留。
    """
    builder = StateGraph(AgentState)
    if specialists is None:
        specialists = {}
    unknown_specialists = set(specialists) - {"order", "after_sales", "knowledge"}
    if unknown_specialists:
        raise ValueError(f"Unknown specialist graph names: {sorted(unknown_specialists)}")

    # 将模型适配放在节点构造阶段，Supervisor 执行时只关注决策流程。
    builder.add_node("supervisor", make_supervisor_node(make_structured_predictor(model)))
    builder.add_node("clarification", clarification_node)
    builder.add_node("result_aggregator", result_aggregator_node)
    builder.add_node("response", response_node)
    for name in ("order", "after_sales", "knowledge"):
        node = (
            make_specialist_node(specialists[name])
            if name in specialists
            else _specialist_not_ready
        )
        builder.add_node(name, node)
    builder.add_edge(START, "supervisor")
    # 条件函数只返回有限节点名，不执行模型或业务副作用。
    builder.add_conditional_edges("supervisor", route_after_supervisor)
    for name in ("order", "after_sales", "knowledge"):
        builder.add_conditional_edges(name, route_after_specialist)
    builder.add_edge("clarification", "response")
    builder.add_edge("result_aggregator", "response")
    builder.add_edge("response", END)
    return builder.compile(checkpointer=InMemorySaver())


def _specialist_not_ready(state: AgentState) -> None:
    """占位专业分支：拓扑完整可编译，但未实现时绝不伪造业务成功结果。"""
    raise GraphProtocolError("The selected specialist graph has not been implemented")
