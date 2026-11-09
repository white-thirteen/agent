"""将专业 Agent 的结构化结果整理为 ResponseNode 可展示的文本。"""

from app.graph.contracts import GraphProtocolError, ResultStatus, SpecialistResult
from app.graph.state import AgentState


def result_aggregator_node(state: AgentState) -> dict[str, str]:
    """汇总单个专业分支结果，不额外调用模型，也不改变业务事实。

    Specialist wrapper 已验证结果与当前 task/workflow/run 的关联。这里根据结果状态
    决定是否可向用户展示：completed 和 rejected 使用专业服务提供的摘要；needs_input
    已由条件边转到 ClarificationNode；failed 走 Runtime 的安全错误出口。
    """
    result = state.get("specialist_result")
    if result is None:
        raise GraphProtocolError("Result aggregation requires a specialist result")
    result = SpecialistResult.model_validate(result)

    if result.status in (ResultStatus.COMPLETED, ResultStatus.REJECTED):
        return {"final_answer": result.summary}
    if result.status is ResultStatus.FAILED:
        raise GraphProtocolError("Specialist execution failed")
    raise GraphProtocolError("Input-required results must go through clarification")
