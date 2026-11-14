"""Real Store/Saver commands and original-operation fault checks, exact UUID cleanup."""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import GetOp, PutOp
from pydantic import SecretStr
from runtime_support import context, run_to_end
from test_memory_manage import memory_parent, memory_resources
from test_memory_postgres import database_snapshot

from app.core.config import Settings
from app.domain.refunds import canonical_digest
from app.infrastructure.checkpoint import checkpoint_serializer, open_checkpoint_pool
from app.infrastructure.postgres import open_pool, validate_test_target
from app.infrastructure.store import store_resources
from app.memory.manager import preference_namespace
from app.memory.models import MemoryCommand
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.models import RunLimits
from app.tools.models import MemoryBusinessContext
from scripts import run_async


def settings_for_test():
    raw = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Explicit test database required")
    secret = SecretStr(raw)
    validate_test_target(secret, Settings().database_url)
    users = tuple("memory532-" + uuid4().hex for _ in range(2))
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=secret,
        test_database_url=secret,
        demo_user_ids=users,
    )


class ObservedStore:
    """Named fault injections wrap actual public Store calls, never fake persistence."""

    def __init__(self, resource):
        self.resource = resource
        self.puts = 0
        self.gets = 0
        self.mode = None

    async def aget(self, *args):
        return await self.resource.aget(*args)

    async def abatch(self, operations):
        assert len(operations) == 1
        if isinstance(operations[0], GetOp):
            self.gets += 1
            if self.mode == "get_failure":
                raise psycopg.OperationalError("Controlled pre-Put read failure")
        else:
            self.puts += 1
            if self.mode == "put_failure":
                raise psycopg.OperationalError("Controlled unconfirmed Put")
        result = await self.resource.abatch(operations)
        if isinstance(operations[0], PutOp) and self.mode == "commit_lost":
            raise psycopg.OperationalError("Controlled lost acknowledgement after real commit")
        return result


def test_real_memory_commands_cross_threads_process_crud_and_exact_cleanup():
    settings = settings_for_test()

    async def scenario():
        pool = await open_pool(settings)
        checkpoint_pool = await open_checkpoint_pool(settings)
        saver = AsyncPostgresSaver(checkpoint_pool, serde=checkpoint_serializer())
        before = await database_snapshot(pool)
        threads = []
        runtime = None
        try:
            async with store_resources(settings) as resource:
                observed = ObservedStore(resource)
                manager, registry, executor = memory_resources(observed, settings.demo_user_ids)
                graph = memory_parent(registry, executor, saver)
                runtime = AgentRuntime(graph, run_limits=RunLimits(30, 12))

                async def command(text, user=None):
                    thread = "memory532-thread-" + uuid4().hex
                    threads.append(thread)
                    ctx = replace(
                        context(
                            user=user or settings.demo_user_ids[0],
                            thread=thread,
                            conversation="memory532-conv-" + uuid4().hex,
                            message=text,
                        ),
                        permission_scopes=frozenset({"memory:read", "memory:write"}),
                    )
                    _, view, _ = await run_to_end(runtime, ctx)
                    saved = await graph.aget_state({"configurable": {"thread_id": thread}})
                    assert view.task_status == "completed", (view.task_status, view.error)
                    assert not saved.values["sources"]
                    assert view.run_usage.tool_calls == (1 if text == "请查看偏好记忆" else 2)
                    return saved.values["specialist_result"]

                first = await command("请记住：回答语言=英语")
                assert first.facts["memory_result"]["revision"] == 1
                cross = await command("请查看偏好记忆")
                assert cross.facts["preferences"] == {"answer_language": "en"}
                other = await command("请查看偏好记忆", settings.demo_user_ids[1])
                assert other.facts["preferences"] == {} and other.facts["revision"] is None
                await command("请修改记忆：回答风格=详细")
                assert (await manager.snapshot(user_id=settings.demo_user_ids[0])).preferences == {
                    "answer_language": "en",
                    "answer_style": "detailed",
                }
                # A completely fresh interpreter opens a new Store/pool, independent of Saver.
                code = """import os
from app.core.config import Settings
from app.infrastructure.store import store_resources
from app.memory.manager import MemoryManager
from scripts import run_async
async def main():
 s=Settings().model_copy(update={"database_url":Settings().test_database_url})
 async with store_resources(s) as r:
  user=os.environ["MEMORY532_USER"]
  print((await MemoryManager(r,user_ids=(user,)).snapshot(user_id=user)).model_dump_json())
run_async(main())"""
                process = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, "-c", code],
                    env={**os.environ, "MEMORY532_USER": settings.demo_user_ids[0]},
                    capture_output=True,
                    timeout=30,
                )
                assert process.returncode == 0, "New-process probe failed (private stderr withheld)"
                assert json.loads(process.stdout)["preferences"] == {
                    "answer_language": "en",
                    "answer_style": "detailed",
                }
                # Controlled Chat/Retriever verifies presentation precedence and budgets;
                # the saved English preference is read from the real Store above.
                from langchain_core.messages import HumanMessage
                from test_knowledge_graph import Provider, Retriever
                from test_knowledge_graph import execution as qa_execution

                from app.agents.types import AgentType, TaskType
                from app.graph.contracts import SpecialistInput
                from app.graph.specialists.knowledge.builder import build_knowledge_graph
                from app.graph.transfers import create_specialist_state
                from app.memory.reader import MemoryReader
                from app.runtime.model_gateway import ModelCallLimits, ModelGateway
                from app.tools.executor import ToolExecutor
                from app.tools.implementations.knowledge import knowledge_tools
                from app.tools.implementations.memory import read_preferences_tool
                from app.tools.policy import ToolPolicy
                from app.tools.registry import ToolRegistry

                qa_registry = ToolRegistry()
                retriever, provider = Retriever(), Provider()
                for definition in knowledge_tools(retriever):
                    qa_registry.register(definition)
                qa_registry.register(read_preferences_tool(MemoryReader(manager), enabled=True))
                qa_registry.freeze()
                qa_live = qa_execution(scopes=frozenset({"knowledge:read", "memory:read"}))
                qa_live = replace(
                    qa_live,
                    context=qa_live.context.model_copy(
                        update={"user_id": settings.demo_user_ids[0]}
                    ),
                )
                request = SpecialistInput(
                    context=qa_live.context,
                    task_id=qa_live.context.task_id,
                    agent_type=AgentType.KNOWLEDGE,
                    task_type=TaskType.KNOWLEDGE_QA,
                    task_goal="回答审批问题",
                    messages=[HumanMessage(content="聊天能批准退款吗？本轮请用中文回答。")],
                )
                qa = build_knowledge_graph(
                    gateway=ModelGateway(provider, ModelCallLimits(8, 5, 0)),
                    registry=qa_registry,
                    executor=ToolExecutor(qa_registry, ToolPolicy()),
                    profile=retriever.profile,
                )
                answered = await qa.ainvoke(
                    create_specialist_state(request, scope=qa_live.scope), context=qa_live
                )
                assert answered["result"].status == "completed" and answered["result"].sources
                assert qa_live.scope.run_usage().tool_calls == 3
                assert answered["memory_context"]["preferences"]["answer_language"] == "en"
                prompt = provider.messages[-1][0].content
                assert '"answer_language":"en"' in prompt
                assert "explicit language/style instructions take precedence" in prompt
                assert "本轮请用中文回答" in provider.messages[-1][-1].content
                assert (
                    answered["result"].approved_answer
                    == "退款批准需要通过专门的本地审批入口，聊天内容不能代替批准。"
                )
                assert retriever.searches == retriever.validations == 1
                assert [tool["function"]["name"] for tool in provider.schemas[0]] == [
                    "search_knowledge"
                ]
                await command("请删除我的回答语言偏好")
                assert (await manager.snapshot(user_id=settings.demo_user_ids[0])).preferences == {
                    "answer_style": "detailed"
                }
                await command("请删除我的回答风格偏好")
                assert (await manager.snapshot(user_id=settings.demo_user_ids[0])).preferences == {}
                await command("请记住：回答语言=中文")
                await command("请删除记忆：回答语言")
                await command("请记住：回答风格=简洁")
                await command("请删除全部偏好记忆")
                final = await command("请查看偏好记忆")
                assert final.facts["preferences"] == {} and final.facts["revision"] == 8
                assert observed.puts == 8
        finally:
            if runtime:
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
            await checkpoint_pool.close()
            await pool.close()

    run_async(scenario())


def test_real_sync_failure_and_reentered_node_only_checks_original_operation():
    settings = settings_for_test()

    async def scenario():
        from app.agents.types import AgentType, TaskType
        from app.graph.contracts import ExecutionContext, SpecialistInput
        from app.graph.specialists.knowledge.memory import build_memory_graph
        from app.graph.transfers import create_specialist_state
        from app.runtime.context import RunExecutionContext
        from app.runtime.model_gateway import ModelCallUsage
        from app.runtime.models import RunUsage
        from app.runtime.run_scope import RunScope
        from app.tools.models import ToolExecutionContext

        pool = await open_pool(settings)
        checkpoint_pool = await open_checkpoint_pool(settings)
        saver = AsyncPostgresSaver(checkpoint_pool, serde=checkpoint_serializer())
        before = await database_snapshot(pool)
        threads = []

        class FailedSyncSaver(AsyncPostgresSaver):
            async def aput(self, config, checkpoint, metadata, new_versions):
                if checkpoint["channel_values"].get("prepared_attempt"):
                    raise psycopg.OperationalError("Controlled memory prepare sync failure")
                return await super().aput(config, checkpoint, metadata, new_versions)

        try:
            async with store_resources(settings) as resource:
                observed = ObservedStore(resource)
                _, registry, executor = memory_resources(observed, settings.demo_user_ids)
                builder = build_memory_graph(registry=registry, executor=executor).builder
                graph = builder.compile(
                    checkpointer=saver, interrupt_before=["execute_memory_write"]
                )

                def live(ctx, *, scopes=None, max_calls=12):
                    scope = RunScope(
                        limits=RunLimits(30, max_calls),
                        model_usage=ModelCallUsage(),
                        run_usage=RunUsage(),
                    )
                    scope.start_active_period()
                    return RunExecutionContext(
                        ctx,
                        threads[-1],
                        scopes
                        if scopes is not None
                        else frozenset({"memory:read", "memory:write"}),
                        scope,
                    )

                def initial():
                    thread = "memory532-sync-" + uuid4().hex
                    threads.append(thread)
                    task = "task-" + uuid4().hex
                    ctx = ExecutionContext(
                        user_id=settings.demo_user_ids[0],
                        conversation_id="c-" + uuid4().hex,
                        task_id=task,
                        workflow_id=task,
                        run_id="r-" + uuid4().hex,
                    )
                    execution = live(ctx)
                    request = SpecialistInput(
                        context=ctx,
                        task_id=task,
                        agent_type=AgentType.KNOWLEDGE,
                        task_type=TaskType.MEMORY_MANAGE,
                        task_goal="save",
                    )
                    return (
                        {
                            **create_specialist_state(request, scope=execution.scope),
                            "memory_command": MemoryCommand(
                                operation="upsert", field="answer_language", value="en"
                            ).model_dump(),
                            "source_message_id": "human:" + ctx.run_id,
                        },
                        {"configurable": {"thread_id": thread}},
                        execution,
                    )

                # Failing the actual saver aput before advancing prevents every write handler.
                failed = builder.compile(
                    checkpointer=FailedSyncSaver(checkpoint_pool, serde=checkpoint_serializer())
                )
                state, config, execution = initial()
                with pytest.raises(psycopg.OperationalError):
                    await failed.ainvoke(state, config, context=execution, durability="sync")
                assert observed.puts == 0 and observed.gets == 0
                assert execution.scope.run_usage().tool_calls == 1  # revision read only

                # Pause after a real synchronous prepared checkpoint, before any handler/Put.
                state, config, execution = initial()
                await graph.ainvoke(state, config, context=execution, durability="sync")
                saved = await graph.aget_state(config)
                marker = saved.values["prepared_attempt"]
                assert saved.next == ("execute_memory_write",)
                assert marker.baseline_tool_calls == 1 and marker.attempted_tool_calls == 2
                assert execution.scope.run_usage().tool_calls == 1 and observed.puts == 0
                assert marker.business_snapshot["expected_revision"] == 0
                # Node-origin/model, wrong node, scope, allowed set and args reject zero handler.
                target = ToolExecutionContext(
                    execution.context,
                    AgentType.KNOWLEDGE,
                    TaskType.MEMORY_MANAGE,
                    "execute_memory_write",
                    execution.permission_scopes,
                    "node",
                    frozenset({("write_preferences", "1")}),
                    {"write_preferences": marker.normalized_args},
                    execution.scope.limits,
                    execution.scope,
                    thread_id=execution.thread_id,
                )
                for wrong in (
                    replace(target, origin="model"),
                    replace(target, node_name="prepare_memory_write"),
                    replace(target, permission_scopes=frozenset()),
                    replace(target, allowed_tools=frozenset()),
                    replace(target, argument_constraints={"write_preferences": {}}),
                ):
                    assert (await executor.execute_prepared(marker, context=wrong)).attempts == 0
                assert observed.gets == 0 and observed.puts == 0
                # New Run and scope must inherit the possible prior attempt and only Get.
                restarted = live(
                    execution.context.model_copy(update={"run_id": "new-" + uuid4().hex})
                )
                result = await graph.ainvoke(None, config, context=restarted, durability="sync")
                assert result["memory_result"]["status"] == "unknown"
                assert result["result"].error.code == "memory_result_unknown"
                assert (
                    result["result"].summary
                    == "本次偏好写入结果未知，请先核对，再提交新的记忆修改。"
                )
                assert restarted.scope.run_usage().tool_calls == 3 and observed.puts == 0
                assert restarted.scope.run_usage().active_elapsed_ms >= 3000
                write_record = result["call_records"][marker.call.call_id]["result"]
                assert write_record["attempts"] == 1 and write_record["effect_status"] == "unknown"

                # A known unknown re-entry blocked by current policy preserves original data.
                reenter = live(
                    restarted.context.model_copy(update={"run_id": "denied-" + uuid4().hex}),
                    scopes=frozenset(),
                )
                await graph.aupdate_state(config, {"outcome": None}, as_node="prepare_memory_write")
                blocked = await graph.ainvoke(None, config, context=reenter, durability="sync")
                assert blocked["memory_result"] == result["memory_result"] and observed.puts == 0
                assert reenter.scope.run_usage().tool_calls == 3
                refused = blocked["call_records"][marker.call.call_id]["result"]
                assert refused["status"] == "policy_denied" and refused["attempts"] == 0
                # A second new Run with exhausted budget also retains domain unknown.
                await graph.aupdate_state(config, {"outcome": None}, as_node="prepare_memory_write")
                exhausted = live(
                    reenter.context.model_copy(update={"run_id": "budget-" + uuid4().hex}),
                    max_calls=3,
                )
                no_budget = await graph.ainvoke(None, config, context=exhausted, durability="sync")
                assert no_budget["memory_result"] == result["memory_result"]
                assert exhausted.scope.run_usage().tool_calls == 3 and observed.puts == 0

                # A real Get failure enters the first handler once, without Put.
                state, config, execution = initial()
                await graph.ainvoke(state, config, context=execution, durability="sync")
                observed.mode = "get_failure"
                not_started = await graph.ainvoke(
                    None, config, context=execution, durability="sync"
                )
                record = next(
                    v["result"]
                    for v in not_started["call_records"].values()
                    if v["call"]["name"] == "write_preferences"
                )
                assert record["attempts"] == 1 and record["effect_status"] == "not_started"
                assert record["status"] == "failed" and record["data"] is None
                assert execution.scope.run_usage().tool_calls == 2 and observed.puts == 0
                observed.mode = None

                # Lost acknowledgement after real commit: unknown, then check-only reuse.
                state, config, execution = initial()
                await graph.ainvoke(state, config, context=execution, durability="sync")
                observed.mode = "commit_lost"
                uncertain = await graph.ainvoke(None, config, context=execution, durability="sync")
                assert uncertain["memory_result"]["status"] == "unknown" and observed.puts == 1
                observed.mode = None
                await graph.aupdate_state(config, {"outcome": None}, as_node="prepare_memory_write")
                replay = live(
                    execution.context.model_copy(update={"run_id": "replay-" + uuid4().hex})
                )
                reused = await graph.ainvoke(None, config, context=replay, durability="sync")
                assert reused["memory_result"]["status"] == "reused" and observed.puts == 1
                # Saved successful call record is reused without another handler.
                prior_gets = observed.gets
                await graph.aupdate_state(config, {"outcome": None}, as_node="prepare_memory_write")
                reused_again = await graph.ainvoke(None, config, context=replay, durability="sync")
                assert reused_again["memory_result"]["status"] == "reused"
                assert replay.scope.run_usage().tool_calls == 3 and observed.gets == prior_gets
        finally:
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
            await checkpoint_pool.close()
            await pool.close()

    run_async(scenario())


def test_real_manager_revision_idempotency_unknown_and_no_put_on_replay():
    settings = settings_for_test()

    async def scenario():
        pool = await open_pool(settings)
        before = await database_snapshot(pool)
        try:
            async with store_resources(settings) as resource:
                observed = ObservedStore(resource)
                manager, _, _ = memory_resources(observed, settings.demo_user_ids)
                user = settings.demo_user_ids[0]
                en = MemoryCommand(operation="upsert", field="answer_language", value="en")
                style = MemoryCommand(operation="upsert", field="answer_style", value="detailed")

                def business(command, revision=0):
                    return MemoryBusinessContext(
                        user,
                        "task-" + uuid4().hex,
                        "run-" + uuid4().hex,
                        "op-" + uuid4().hex,
                        canonical_digest(command.model_dump()),
                        revision,
                        False,
                    )

                first, second = business(en), business(style)
                results = await asyncio.gather(
                    manager.apply(en, context=first), manager.apply(style, context=second)
                )
                assert [r.status for r in results] == ["applied", "conflict"]
                assert observed.puts == 1
                assert (await manager.apply(en, context=first)).status == "reused"
                assert observed.puts == 1
                wrong = replace(first, command_digest=canonical_digest(style.model_dump()))
                assert (await manager.apply(style, context=wrong)).status == "conflict"
                clear = MemoryCommand(operation="clear")
                assert (await manager.apply(clear, context=business(clear, 1))).status == "applied"
                assert (await manager.apply(en, context=first)).status == "conflict"
                assert (
                    await manager.apply(en, context=replace(first, replay_check_only=True))
                ).status == "unknown"
                assert (await manager.snapshot(user_id=user)).preferences == {}
                assert observed.puts == 2
                # A failed Put with unchanged revision is still unknown and check-only never writes.
                original = business(en, 2)
                observed.mode = "put_failure"
                assert (await manager.apply(en, context=original)).status == "unknown"
                observed.mode = None
                count = observed.puts
                assert (
                    await manager.apply(en, context=replace(original, replay_check_only=True))
                ).status == "unknown"
                assert observed.puts == count
                observed.mode = "commit_lost"
                committed = business(en, 2)
                assert (await manager.apply(en, context=committed)).status == "unknown"
                observed.mode = None
                assert (
                    await manager.apply(en, context=replace(committed, replay_check_only=True))
                ).status == "reused"
                assert observed.puts == count + 1
                observed.mode = "get_failure"
                assert (
                    await manager.apply(en, context=replace(committed, replay_check_only=True))
                ).status == "unknown"
                from app.tools.models import ToolNotStartedError

                with pytest.raises(ToolNotStartedError):
                    await manager.apply(style, context=business(style, 3))
                observed.mode = None
                assert observed.puts == count + 1

                # Cancellation is never converted into a normal durable result.
                class CancelledStore(ObservedStore):
                    async def abatch(self, operations):
                        raise asyncio.CancelledError()

                manager.resource = CancelledStore(resource)
                with pytest.raises(asyncio.CancelledError):
                    await manager.apply(style, context=business(style, 3))
        finally:
            async with store_resources(settings) as resource:
                await resource.abatch(
                    [
                        PutOp(preference_namespace(user), "profile", None)
                        for user in settings.demo_user_ids
                    ]
                )
            assert await database_snapshot(pool) == before
            await pool.close()

    run_async(scenario())
