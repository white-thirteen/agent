"""Runtime boundary between service contexts and the compiled agent graph."""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from app.core.errors import AgentNotReadyError
from app.streaming.events import StreamEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentContext:
    user_id: str
    conversation_id: str
    workflow_id: str
    run_id: str
    message: str


class AgentRuntime:
    def __init__(self, graph=None) -> None:
        self._graph = graph

    @property
    def is_ready(self) -> bool:
        return self._graph is not None

    def stream(self, context: AgentContext) -> AsyncIterator[StreamEvent]:
        if self._graph is None:
            raise AgentNotReadyError("Supervisor is not configured.")

        async def events() -> AsyncIterator[StreamEvent]:
            from app.graph.contracts import ExecutionContext, GraphProtocolError, PendingTask
            from app.graph.state import create_turn_state

            graph_context = ExecutionContext(
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                workflow_id=context.workflow_id,
                run_id=context.run_id,
            )
            # 同一用户会话映射到稳定 Checkpoint 线程，确保下一轮能读取待补任务。
            thread_key = json.dumps(
                [context.user_id, context.conversation_id], ensure_ascii=False
            )
            thread_id = str(uuid5(NAMESPACE_URL, thread_key))
            config = {"configurable": {"thread_id": thread_id}}
            try:
                # 新请求只带本轮输入；从快照单独取 pending_task 交给 state 工厂续接。
                snapshot = await self._graph.aget_state(config)
                saved_pending = (snapshot.values or {}).get("pending_task")
                pending_task = (
                    PendingTask.model_validate(saved_pending)
                    if saved_pending is not None
                    else None
                )
                result = await self._graph.ainvoke(
                    create_turn_state(
                        graph_context, context.message, pending_task=pending_task
                    ),
                    config,
                )
                if result.get("final_answer"):
                    yield StreamEvent(event="token", data={"content": result["final_answer"]})
                if result.get("specialist_result") is None and not result.get("final_answer"):
                    raise GraphProtocolError("Graph ended without a user-facing result")
                yield StreamEvent(event="done", data={"status": "completed"})
            except Exception:
                logger.exception(
                    "Agent graph execution failed",
                    extra={
                        "user_id": context.user_id,
                        "conversation_id": context.conversation_id,
                        "workflow_id": context.workflow_id,
                        "run_id": context.run_id,
                    },
                )
                yield StreamEvent(
                    event="error",
                    data={"code": "agent_execution_failed", "message": "Agent execution failed."},
                )
                yield StreamEvent(event="done", data={"status": "failed"})

        return events()
