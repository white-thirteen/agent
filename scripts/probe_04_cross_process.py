"""Isolated strict-serializer PG Saver probe across independent Python processes."""

import logging
import subprocess
import sys
from dataclasses import dataclass
from typing import TypedDict
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from app.core.config import Settings
from app.graph.contracts import ExecutionContext
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.postgres import validate_test_target
from app.tools.models import ParsedToolCall, PreparedToolAttempt
from scripts import run_async


class State(TypedDict, total=False):
    request: ExecutionContext
    marker: PreparedToolAttempt
    resumed: str


@dataclass(frozen=True)
class Context:
    resume: bool
    run: str


def graph_for(saver):
    child = StateGraph(State, context_schema=Context)

    def gate(state: State):
        result = interrupt({"kind": "strict-probe"})
        return {"resumed": result}

    def finish(state: State, runtime: Runtime[Context]):
        assert isinstance(state["request"], ExecutionContext)
        assert isinstance(state["marker"], PreparedToolAttempt)
        assert isinstance(state["marker"].call, ParsedToolCall)
        assert runtime.context.run == "run-after-process-restart"
        return {"resumed": state["resumed"]}

    child.add_node("gate", gate)
    child.add_node("finish", finish)
    child.add_edge(START, "gate")
    child.add_edge("gate", "finish")
    child.add_edge("finish", END)
    subgraph = child.compile()
    parent = StateGraph(State, context_schema=Context)

    async def wrapper(state: State, config: RunnableConfig, runtime: Runtime[Context]):
        return await subgraph.ainvoke(
            None if runtime.context.resume else state, config, context=runtime.context
        )

    parent.add_node("wrapper", wrapper)
    parent.add_edge(START, "wrapper")
    parent.add_edge("wrapper", END)
    return parent.compile(checkpointer=saver)


async def worker(phase, thread):
    logging.disable(logging.CRITICAL)
    settings = Settings()
    validate_test_target(settings.test_database_url, settings.database_url)
    pool = await open_checkpoint_pool(
        settings.model_copy(update={"database_url": settings.test_database_url})
    )
    saver = AsyncPostgresSaver(pool, serde=checkpoint_serializer())
    config = {"configurable": {"thread_id": thread}}
    try:
        async with pool.connection() as conn:
            row = await (
                await conn.execute("SELECT current_database() AS db,current_user AS owner")
            ).fetchone()
            assert (row["db"], row["owner"]) == ("agent_demo_test", "agent_test")
        if phase == "cleanup":
            await saver.adelete_thread(thread)
            async with pool.connection() as conn:
                for table in ("checkpoints", "checkpoint_writes", "checkpoint_blobs"):
                    row = await (
                        await conn.execute(
                            f"SELECT count(*) AS n FROM {table} WHERE thread_id=%s", (thread,)
                        )
                    ).fetchone()
                    assert row["n"] == 0
            print("PROBE_THREAD_CLEANED", flush=True)
            return
        graph = graph_for(saver)
        if phase == "write":
            request = ExecutionContext(
                user_id="probe-user",
                conversation_id="probe",
                task_id="task",
                workflow_id="task",
                run_id="run-before",
            )
            marker = PreparedToolAttempt(
                "attempt",
                "run-before",
                "task",
                ParsedToolCall("call", "refund_order", {"order_id": "probe"}),
                "1",
                {"order_id": "probe"},
                "digest",
                "operation",
                0,
                1,
                5,
                {},
                {},
            )
            result = await graph.ainvoke(
                {"request": request, "marker": marker},
                config,
                context=Context(False, "run-before"),
                durability="sync",
            )
            assert len(result.get("__interrupt__", ())) == 1
            print("PROCESS_ONE_INTERRUPT_SAVED", flush=True)
        elif phase == "resume":
            snapshot = await graph.aget_state(config, subgraphs=True)
            child = snapshot.tasks[0].state
            assert child and len(child.interrupts) == 1
            assert isinstance(child.values["request"], ExecutionContext)
            assert isinstance(child.values["marker"], PreparedToolAttempt)
            assert child.config["configurable"]["checkpoint_ns"]
            result = await graph.ainvoke(
                Command(resume={child.interrupts[0].id: "reference"}),
                config,
                context=Context(True, "run-after-process-restart"),
                durability="sync",
            )
            assert result["resumed"] == "reference"
            print("PROCESS_TWO_STRICT_TYPES_AND_RESUME_OK", flush=True)
    finally:
        await pool.close()


def main():
    if len(sys.argv) == 3:
        try:
            run_async(worker(sys.argv[1], sys.argv[2]))
        except Exception as exc:
            print("STRICT_PROBE_FAILED", type(exc).__name__, flush=True)
            return 1
        return 0
    thread = "strict04-" + uuid4().hex
    status = 0
    try:
        for phase in ("write", "resume"):
            if subprocess.run(
                [sys.executable, "-m", "scripts.probe_04_cross_process", phase, thread], check=False
            ).returncode:
                status = 1
                break
    finally:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.probe_04_cross_process", "cleanup", thread], check=False
        )
        if result.returncode:
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
