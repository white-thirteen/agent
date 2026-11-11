"""Single writer of approved public AI messages, with stable per-Run IDs."""

from langchain_core.messages import AIMessage

from app.graph.state import AgentState


def response_node(state: AgentState):
    answer = state.get("final_answer")
    if not answer:
        return {}
    message_id = f"assistant:{state['run_id']}"
    ids = list(state["task_message_ids"])
    if message_id not in ids:
        ids.append(message_id)
    return {"messages": [AIMessage(content=answer, id=message_id)], "task_message_ids": ids}
