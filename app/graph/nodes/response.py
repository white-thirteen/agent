"""唯一将已批准展示文本写入公共对话历史的主图出口。"""

from langchain_core.messages import AIMessage

from app.graph.contracts import GraphProtocolError
from app.graph.state import AgentState


def response_node(state: AgentState) -> dict[str, object]:
    """把 ClarificationNode 或 ResultAggregator 选定的回复写入消息历史。

    此节点不生成业务结论：它只持久化已经确定的澄清问题或专业结果摘要，
    令 Checkpoint 中的 public history 与本次 SSE 回复保持一致。
    """
    answer = state.get("final_answer")
    if not answer:
        raise GraphProtocolError("Response requires a final answer")
    return {
        "messages": [AIMessage(content=answer, id=f"assistant:{state['run_id']}")]
    }
