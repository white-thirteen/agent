"""Project validated specialist facts to the single public Response boundary."""

from app.agents.types import TaskType
from app.graph.contracts import GraphProtocolError, ResultStatus, SpecialistResult
from app.graph.state import AgentState


def result_aggregator_node(state: AgentState):
    result = SpecialistResult.model_validate(state["specialist_result"])
    if result.status is ResultStatus.FAILED:
        return {"final_answer": None, "error": result.error.model_dump()}
    if result.status not in (ResultStatus.COMPLETED, ResultStatus.REJECTED):
        raise GraphProtocolError("Input-required result must enter clarification")
    answer = (
        result.approved_answer
        if result.task_type is TaskType.KNOWLEDGE_QA and result.status is ResultStatus.COMPLETED
        else result.summary
    )
    return {"final_answer": answer}
