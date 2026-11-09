"""父图到专业子图的调用适配器。"""

from app.graph.contracts import GraphProtocolError
from app.graph.state import AgentState
from app.graph.transfers import (
    apply_specialist_result,
    build_specialist_input,
    create_specialist_state,
)


def make_specialist_node(subgraph):
    """把编译后的固定专业子图包装成主图节点。

    父图只向子图传 SpecialistInput 白名单；子图返回完整私有 State 后，
    wrapper 只取结构化 result 并通过 apply_specialist_result 校验、映射回父图，
    不把工具调用、私有消息或子图其他状态合并到公共会话。
    """

    async def specialist_node(state: AgentState) -> dict[str, object]:
        request = build_specialist_input(state)
        output = await subgraph.ainvoke(create_specialist_state(request))
        result = output.get("result")
        if result is None:
            raise GraphProtocolError("Specialist must produce a structured result")
        return apply_specialist_result(state, result)

    return specialist_node
