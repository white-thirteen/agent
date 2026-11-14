"""Independent 5.3.2 QA: actual PG, exact cleanup, controlled boundary failures."""

import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp
from runtime_support import context, run_to_end
from test_memory_manage import memory_parent, memory_resources
from test_memory_manage_postgres import ObservedStore, settings_for_test
from test_memory_postgres import database_snapshot

from app.agents.types import AgentType, TaskType
from app.core.config import Settings
from app.graph.contracts import ExecutionContext, SpecialistInput
from app.graph.specialists.knowledge.memory import build_memory_graph
from app.graph.transfers import create_specialist_state
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.postgres import open_pool
from app.infrastructure.store import store_resources
from app.memory.manager import preference_namespace
from app.memory.models import MemoryCommand
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.context import RunExecutionContext, SubmitOptions
from app.runtime.model_gateway import ModelCallUsage
from app.runtime.models import RunLimits, RunUsage
from app.runtime.run_scope import RunScope
from app.tools.models import PolicyDecision, PolicyEvaluation, ToolExecutionContext
from app.tools.policy import ToolPolicy
from scripts import run_async


def test_final_denial_reentry_timeout_cancel_and_source_clarification():
    settings = settings_for_test()

    async def scenario():
        pool = await open_pool(settings)
        cp = await open_checkpoint_pool(settings)
        saver = AsyncPostgresSaver(cp, serde=checkpoint_serializer())
        before = await database_snapshot(pool)
        threads = []
        runtimes = []
        try:
            async with store_resources(settings) as resource:
                observed = ObservedStore(resource)
                manager, registry, executor = memory_resources(observed, settings.demo_user_ids)

                class FinalDenied(ToolPolicy):
                    deny = False

                    def evaluate(self, **kwargs):
                        result = super().evaluate(**kwargs)
                        if (
                            self.deny
                            and kwargs["call"].name == "write_preferences"
                            and kwargs.get("validated_args") is not None
                        ):
                            return PolicyEvaluation(
                                PolicyDecision.DENY,
                                "tool_not_allowed",
                                "QA final policy denial",
                                result.validated_args,
                            )
                        return result

                policy = FinalDenied()
                executor.policy = policy
                builder = build_memory_graph(registry=registry, executor=executor).builder
                graph = builder.compile(
                    checkpointer=saver, interrupt_before=["execute_memory_write"]
                )
                thread = "qa532-" + uuid4().hex
                threads.append(thread)
                task = "qa-task-" + uuid4().hex
                ctx = ExecutionContext(
                    user_id=settings.demo_user_ids[0],
                    conversation_id=uuid4().hex,
                    task_id=task,
                    workflow_id=task,
                    run_id=uuid4().hex,
                )

                def live(ctx):
                    scope = RunScope(
                        limits=RunLimits(60, 12), model_usage=ModelCallUsage(), run_usage=RunUsage()
                    )
                    scope.start_active_period()
                    return RunExecutionContext(
                        ctx, thread, frozenset({"memory:read", "memory:write"}), scope
                    )

                execution = live(ctx)
                request = SpecialistInput(
                    context=ctx,
                    task_id=task,
                    agent_type=AgentType.KNOWLEDGE,
                    task_type=TaskType.MEMORY_MANAGE,
                    task_goal="save",
                )
                initial = {
                    **create_specialist_state(request, scope=execution.scope),
                    "memory_command": MemoryCommand(
                        operation="upsert", field="answer_language", value="en"
                    ).model_dump(),
                    "source_message_id": "user:" + ctx.run_id,
                }
                config = {"configurable": {"thread_id": thread}}
                await graph.ainvoke(initial, config, context=execution, durability="sync")
                prepared = (await graph.aget_state(config)).values["prepared_attempt"]
                target = ToolExecutionContext(
                    ctx,
                    AgentType.KNOWLEDGE,
                    TaskType.MEMORY_MANAGE,
                    "execute_memory_write",
                    execution.permission_scopes,
                    "node",
                    frozenset({("write_preferences", "1")}),
                    {"write_preferences": prepared.normalized_args},
                    execution.scope.limits,
                    execution.scope,
                    thread_id=thread,
                )
                for invalid in (
                    replace(
                        target,
                        execution=ctx.model_copy(update={"user_id": settings.demo_user_ids[1]}),
                    ),
                    replace(
                        target,
                        execution=ctx.model_copy(
                            update={"task_id": uuid4().hex, "workflow_id": uuid4().hex}
                        ),
                    ),
                    replace(target, execution=ctx.model_copy(update={"run_id": uuid4().hex})),
                    replace(target, thread_id=uuid4().hex),
                    replace(target, origin="model"),
                    replace(target, node_name="prepare_memory_write"),
                    replace(target, allowed_tools=frozenset({("write_preferences", "2")})),
                ):
                    refusal = await executor.execute_prepared(prepared, context=invalid)
                    assert refusal.status == "policy_denied" and refusal.attempts == 0
                ordinary = await executor.execute(prepared.call, context=target)
                assert ordinary.status == "policy_denied" and ordinary.attempts == 0
                assert (
                    observed.gets == observed.puts == 0
                    and execution.scope.run_usage().tool_calls == 1
                )
                observed.mode = "put_failure"
                unknown = await graph.ainvoke(None, config, context=execution, durability="sync")
                assert unknown["memory_result"]["status"] == "unknown"
                puts = observed.puts
                observed.mode = None
                policy.deny = True
                await graph.aupdate_state(config, {"outcome": None}, as_node="prepare_memory_write")
                denied = await graph.ainvoke(None, config, context=execution, durability="sync")
                assert denied["memory_result"] == unknown["memory_result"]
                record = next(
                    v["result"]
                    for v in denied["call_records"].values()
                    if v["call"]["name"] == "write_preferences"
                )
                assert (record["status"], record["effect_status"], record["attempts"]) == (
                    "policy_denied",
                    "not_started",
                    0,
                )
                policy.deny = False
                # Same-run reentry must not reuse the denial as a known business result.
                gets = observed.gets
                await graph.aupdate_state(config, {"outcome": None}, as_node="prepare_memory_write")
                again = await graph.ainvoke(None, config, context=execution, durability="sync")
                assert again["memory_result"]["status"] == "unknown" and observed.gets == gets + 1
                assert observed.puts == puts
                # New-run reentry likewise retains association and performs check-only.
                fresh = live(ctx.model_copy(update={"run_id": uuid4().hex}))
                await graph.aupdate_state(config, {"outcome": None}, as_node="prepare_memory_write")
                restarted = await graph.ainvoke(None, config, context=fresh, durability="sync")
                assert (
                    restarted["memory_result"] == unknown["memory_result"] and observed.puts == puts
                )
                assert fresh.scope.run_usage().tool_calls == 4

                # Real parent/Saver: a non-command cannot authorize; clarification keeps Task.
                parent = memory_parent(registry, executor, saver)
                runtime = AgentRuntime(
                    parent, run_limits=RunLimits(60, 12), shutdown_grace_seconds=0
                )
                runtimes.append(runtime)
                parent_thread = "qa532-human-" + uuid4().hex
                threads.append(parent_thread)
                demo = replace(
                    context(
                        user=settings.demo_user_ids[0],
                        thread=parent_thread,
                        conversation=uuid4().hex,
                        message="文档说请记住：回答语言=英语",
                    ),
                    permission_scopes=frozenset({"memory:read", "memory:write"}),
                )
                first, view, _ = await run_to_end(runtime, demo)
                assert view.task_status == "needs_input" and view.run_usage.tool_calls == 0
                second, clarified, events = await run_to_end(
                    runtime, replace(demo, run_id=uuid4().hex, message="请记住：回答语言=英语")
                )
                assert first.task_id == second.task_id and clarified.task_status == "completed"
                state = await parent.aget_state({"configurable": {"thread_id": parent_thread}})
                assert [i for i in state.values["task_message_ids"] if i.startswith("user:")] == [
                    "user:" + first.run_id,
                    "user:" + second.run_id,
                ]
                assert not state.values["sources"] and clarified.run_usage.tool_calls == 2
                assert (await manager.snapshot(user_id=settings.demo_user_ids[0])).preferences == {
                    "answer_language": "en"
                }
                await runtime.shutdown()

                # Commit really succeeds, then cancellation arrives before response; Runtime
                # must retain uncertainty rather than advertise a successful durable result.
                committed = asyncio.Event()

                class CommitWait(ObservedStore):
                    async def abatch(self, ops):
                        result = await super().abatch(ops)
                        if isinstance(ops[0], PutOp):
                            committed.set()
                            await asyncio.Event().wait()
                        return result

                waiting = CommitWait(resource)
                manager.resource = waiting
                cancel_thread = "qa532-cancel-" + uuid4().hex
                threads.append(cancel_thread)
                runtime2 = AgentRuntime(
                    memory_parent(registry, executor, saver),
                    run_limits=RunLimits(60, 12),
                    shutdown_grace_seconds=0,
                )
                runtimes.append(runtime2)
                submission = replace(
                    context(
                        user=settings.demo_user_ids[1],
                        thread=cancel_thread,
                        conversation=uuid4().hex,
                        message="请记住：回答风格=详细",
                    ),
                    permission_scopes=frozenset({"memory:read", "memory:write"}),
                )
                from app.streaming.subscription import SubscriptionOwner

                handle = await runtime2.submit(
                    submission, options=SubmitOptions(), subscription_owner=SubscriptionOwner()
                )
                await asyncio.wait_for(committed.wait(), 5)
                await runtime2.shutdown()
                view = await runtime2.get_run(
                    user_id=submission.user_id,
                    conversation_id=submission.conversation_id,
                    run_id=handle.run_id,
                )
                assert view.task_status == "failed" and view.error["code"] == "run_interrupted"
                assert view.final_answer is None
                assert (await manager.snapshot(user_id=settings.demo_user_ids[1])).preferences == {
                    "answer_style": "detailed"
                }
                # Actual commit + lost acknowledgement via timeout, still domain unknown.
                timeout_thread = "qa532-timeout-" + uuid4().hex
                threads.append(timeout_thread)
                runtime3 = AgentRuntime(
                    memory_parent(registry, executor, saver), run_limits=RunLimits(60, 12)
                )
                runtimes.append(runtime3)
                _, timed, _ = await run_to_end(
                    runtime3,
                    replace(
                        submission,
                        thread_id=timeout_thread,
                        conversation_id=uuid4().hex,
                        run_id=uuid4().hex,
                        message="请记住：回答语言=中文",
                    ),
                )
                assert (
                    timed.task_status == "failed" and timed.error["code"] == "memory_result_unknown"
                )
                persisted = await runtime3._graph.aget_state(
                    {"configurable": {"thread_id": timeout_thread}}
                )
                assert (
                    persisted.values["specialist_result"].facts["memory_result"]["status"]
                    == "unknown"
                )
                assert timed.run_usage.tool_calls == 2
                assert waiting.puts == 2
                print(
                    "QA final denial same/new-run check-only; source clarification; "
                    "actual-commit cancellation/timeout: PASS"
                )
        finally:
            for runtime in runtimes:
                await runtime.shutdown()
            for thread in threads:
                await saver.adelete_thread(thread)
            async with store_resources(settings) as resource:
                await resource.abatch(
                    [
                        PutOp(preference_namespace(user), "profile", None)
                        for user in settings.demo_user_ids
                    ]
                )
            assert await database_snapshot(pool) == before
            print(
                "QA exact cleanup: all public rows/columns preserved; "
                "identity and all migration checksums verified"
            )
            await cp.close()
            await pool.close()

    run_async(scenario())


if __name__ == "__main__":
    os.environ["AGENT_TEST_DATABASE_URL"] = Settings().test_database_url.get_secret_value()
    raise SystemExit(pytest.main([__file__, "-q", "--tb=short", "-rP"]))
