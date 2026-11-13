"""Opt-in, isolated PG Saver probe for nested interrupt and post-gate recovery."""

import logging
from dataclasses import dataclass
from typing import TypedDict
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from app.core.config import Settings
from app.infrastructure.checkpoint import open_checkpoint_pool
from app.infrastructure.postgres import validate_test_target
from scripts import run_async


class State(TypedDict, total=False):
    value: str
    gate_value: str
    result: str


@dataclass(frozen=True)
class Context:
    mode: str
    current_run: str
    recovery: str | None = None


def create_graph(saver, observed):
    child = StateGraph(State, context_schema=Context)

    def prepare(state: State):
        observed.append(("prepare", None))
        return {"value": "prepared"}

    def gate(state: State):
        observed.append(("gate", None))
        answer = interrupt({"kind": "test"})
        return {"gate_value": answer}

    def execute(state: State, runtime: Runtime[Context]):
        observed.append(("execute", runtime.context.current_run, runtime.context.recovery))
        if runtime.context.mode == "fault":
            raise RuntimeError("Controlled fault")
        return {"result": runtime.context.recovery or runtime.context.current_run}

    child.add_node("prepare", prepare)
    child.add_node("gate", gate)
    child.add_node("execute_refund", execute)
    child.add_edge(START, "prepare")
    child.add_edge("prepare", "gate")
    child.add_edge("gate", "execute_refund")
    child.add_edge("execute_refund", END)
    compiled_child = child.compile()
    parent = StateGraph(State, context_schema=Context)

    async def wrapper(state: State, config: RunnableConfig, runtime: Runtime[Context]):
        observed.append(("wrapper", runtime.context.current_run))
        payload = state if runtime.context.mode == "start" else None
        return await compiled_child.ainvoke(payload, config, context=runtime.context)

    parent.add_node("wrapper", wrapper)
    parent.add_edge(START, "wrapper")
    parent.add_edge("wrapper", END)
    return parent.compile(checkpointer=saver)


async def main():
    logging.disable(logging.CRITICAL)
    settings = Settings()
    validate_test_target(settings.test_database_url, settings.database_url)
    pool = await open_checkpoint_pool(
        settings.model_copy(update={"database_url": settings.test_database_url})
    )
    saver = AsyncPostgresSaver(pool)
    thread = "probe04-" + uuid4().hex
    config = {"configurable": {"thread_id": thread}}
    observed = []
    try:
        graph = create_graph(saver, observed)
        result = await graph.ainvoke(
            {"value": "initial"}, config, context=Context("start", "run1"), durability="sync"
        )
        pending = result.get("__interrupt__", ())
        assert len(pending) == 1 and pending[0].id
        snapshot = await graph.aget_state(config, subgraphs=True)
        child = snapshot.tasks[0].state
        assert child and child.interrupts and child.interrupts[0].id == pending[0].id
        assert child.config["configurable"]["checkpoint_ns"]
        print("NESTED_INTERRUPT_NAMESPACE_OK", flush=True)
        try:
            await graph.ainvoke(
                Command(resume={pending[0].id: "approved-reference"}),
                config,
                context=Context("fault", "run2"),
                durability="sync",
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("Controlled effect-node failure not observed")
        failed = await graph.aget_state(config, subgraphs=True)
        child = failed.tasks[0].state
        assert child and child.next == ("execute_refund",)
        assert ("execute", "run2", None) in observed
        print("COMMAND_WRAPPER_REENTRY_AND_EXECUTE_NEXT_OK", flush=True)
        result = await graph.ainvoke(
            None,
            config,
            context=Context("reconcile", "run3", "verified-success"),
            durability="sync",
        )
        assert result["result"] == "verified-success"
        assert ("execute", "run3", "verified-success") in observed
        assert sum(entry[0] == "prepare" for entry in observed) == 1
        print("NONE_REENTERS_EXECUTE_RECOVERY_CONTEXT_OK", flush=True)
    finally:
        await saver.adelete_thread(thread)
        async with pool.connection() as conn:
            for table in ("checkpoints", "checkpoint_writes", "checkpoint_blobs"):
                row = await (
                    await conn.execute(
                        f"SELECT count(*) AS n FROM {table} WHERE thread_id=%s", (thread,)
                    )
                ).fetchone()
                assert row["n"] == 0
        await pool.close()
        print("PROBE_THREAD_CLEANED", flush=True)


if __name__ == "__main__":
    try:
        run_async(main())
    except Exception as exc:
        print("CHECKPOINT_PROBE_FAILED", type(exc).__name__, flush=True)
        raise SystemExit(1) from None
