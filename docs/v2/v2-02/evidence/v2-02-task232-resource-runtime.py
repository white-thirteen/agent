"""Three real model calls on one Runtime-owned experimental Task/Run budget."""

import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agents.types import AgentType
from app.context.compaction import SUMMARY_PROMPT_VERSION, summarize_for_run
from app.core.config import Settings
from app.graph.nodes.run_finish import run_finish_node
from app.graph.state import AgentState
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.model import model_resources
from app.infrastructure.postgres import open_pool, validate_test_target
from app.infrastructure.sessions import SessionRepository
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from app.runtime.context import DemoContext, RunExecutionContext, SubmitOptions
from app.runtime.model_gateway import ModelCallContext
from app.runtime.models import TaskStatus
from scripts import run_async
from scripts.verify_05_memory_manage import compare_publication_snapshots, database_snapshot

ROOT = Path("docs/v2/v2-02/evidence")
OUTPUT = ROOT / (
    "v2-02-task232-resource-runtime-r3.json"
    if "--v5" in sys.argv
    else "v2-02-task232-resource-runtime-r2.json"
)


async def main():
    assert not OUTPUT.exists()
    raw = (ROOT / "context-resource-fixture.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "24ac79e8e06cd7f1021b4acbd40e0669ddf96e637f28d69de9e7f67ead7c3ee3"
    )
    fixture = json.loads(raw)
    history = []
    for i, item in enumerate(fixture["interactions"]):
        history.append(
            (
                HumanMessage(content=item["user"], id=f"resource-{i}-u"),
                AIMessage(content=item["assistant"], id=f"resource-{i}-a"),
            )
        )
    original = Settings()
    assert original.model_configured and original.test_database_url
    validate_test_target(original.test_database_url, original.database_url)
    settings = original.model_copy(
        update={
            "database_url": original.test_database_url,
            "app_env": "test",
            "context_model_window_tokens": 16384,
            "context_model_output_tokens": 512,
            "context_summary_output_tokens": 512,
        }
    )
    prefix = "ctx232-resource-" + uuid4().hex
    report = {
        "model": settings.model_name,
        "prompt_version": SUMMARY_PROMPT_VERSION,
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "calls": [],
        "cleanup": False,
        "limits": {"window": 16384, "output": 512, "summary_output": 512, "summary_input": 8192},
    }

    def save():
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), "utf-8")

    pool = await open_pool(settings)
    checkpoint_pool = await open_checkpoint_pool(settings)
    saver = AsyncPostgresSaver(checkpoint_pool, serde=checkpoint_serializer())
    before = await database_snapshot(pool)
    binding = None
    runtime = None
    try:
        binding = await SessionRepository(pool).get_or_create(
            user_id=prefix, conversation_id=prefix
        )
        async with model_resources(settings) as (_, gateway):

            async def experiment(state: AgentState, runtime: Runtime[RunExecutionContext]):
                execution = runtime.context
                scope = execution.scope
                trusted = execution.context
                assert state["task_id"] == trusted.task_id and state["run_id"] == trusted.run_id
                summary_context = ModelCallContext(
                    trusted.run_id, trusted.task_id, AgentType.SUPERVISOR, prevalidated_summary=True
                )
                started = time.monotonic()
                summary, usage, reports = await summarize_for_run(
                    [m for pair in history for m in pair],
                    running_summary=None,
                    gateway=gateway,
                    context=summary_context,
                    scope=scope,
                    execution_mode="normal",
                    token_counter=count_tokens_approximately,
                    max_input_tokens=8192,
                    max_output_tokens=512,
                )
                scope.adopt_model_usage(usage)
                report["summary"] = {
                    "text": summary.summary,
                    "covered_ids": sorted(summary.summarized_message_ids),
                    "usage": [asdict(item) for item in reports],
                    "elapsed_seconds": time.monotonic() - started,
                }
                save()
                mandatory = [
                    SystemMessage(content="请根据所提供的背景简洁回答当前问题。"),
                    HumanMessage(content=state["messages"][-1].content),
                ]
                for label, selected in (
                    ("full_history", tuple(history)),
                    ("summary_history", ((HumanMessage(content=summary.summary, id="summary"),),)),
                ):
                    context = ModelCallContext(
                        trusted.run_id,
                        trusted.task_id,
                        AgentType.SUPERVISOR,
                        history=selected,
                        on_attempt=scope.adopt_model_usage,
                        on_context_view=scope.record_context_view,
                        on_context_usage=scope.record_context_usage,
                        current_usage=scope.model_usage,
                    )
                    result = await gateway.invoke(
                        mandatory, context=context, model_usage=scope.model_usage()
                    )
                    scope.adopt_model_usage(result.model_usage)
                    report["calls"].append(
                        {
                            "label": label,
                            "view": scope.context_view,
                            "usage": asdict(result.usage),
                            "output": result.message.content,
                        }
                    )
                    save()
                return {"task_status": TaskStatus.COMPLETED, "final_answer": result.message.content}

            builder = StateGraph(AgentState, context_schema=RunExecutionContext)
            builder.add_node("experiment", experiment)
            builder.add_node("run_finish", run_finish_node)
            builder.add_edge(START, "experiment")
            builder.add_edge("experiment", "run_finish")
            builder.add_edge("run_finish", END)
            graph = builder.compile(checkpointer=saver)
            runtime = AgentRuntime(graph, run_limits=RunLimits(120, 12))
            handle = await runtime.submit(
                DemoContext(
                    prefix,
                    prefix,
                    str(binding.thread_id),
                    str(uuid4()),
                    "平台帮助讨论目前的范围是什么？",
                    frozenset(),
                ),
                options=SubmitOptions(),
            )
            await runtime._records[handle.run_id].task
            record = runtime._records[handle.run_id]
            report.update(
                task_id=handle.task_id,
                run_id=handle.run_id,
                task_status=record.task_status,
                model_attempts=record.execution.scope.model_usage().model_attempts,
            )
            save()
    finally:
        if runtime:
            await runtime.shutdown()
        if binding:
            await saver.adelete_thread(str(binding.thread_id))
            async with pool.connection() as conn:
                await conn.execute(
                    "DELETE FROM sessions WHERE user_id=%s AND conversation_id=%s", (prefix, prefix)
                )
        after = await database_snapshot(pool)
        report["cleanup"] = compare_publication_snapshots(before, after, expected_delta=0)
        save()
        await checkpoint_pool.close()
        await pool.close()
        assert report["cleanup"]["protected_unchanged"]


if __name__ == "__main__":
    run_async(main())
