"""Finite authorization and same-executor mutation failure semantics."""

from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from runtime_support import ControlledModel, context, route, run_to_end

from app.agents.types import AgentType, TaskType
from app.graph.builder import build_supervisor_graph
from app.graph.specialists.knowledge.builder import build_knowledge_graph
from app.graph.specialists.knowledge.memory import build_memory_graph, parse_explicit_memory_command
from app.memory.manager import MemoryManager
from app.memory.reader import MemoryReader
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from app.runtime.models import RunLimits
from app.tools.executor import ToolExecutor
from app.tools.implementations.memory import read_preferences_tool, write_preferences_tool
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry


def memory_resources(resource, users):
    manager = MemoryManager(resource, user_ids=users)
    registry = ToolRegistry()
    registry.register(read_preferences_tool(MemoryReader(manager), enabled=True))
    registry.register(write_preferences_tool(manager, enabled=True))
    registry.freeze()
    executor = ToolExecutor(registry, ToolPolicy())
    return manager, registry, executor


def memory_parent(registry, executor, saver, *, outputs=None):
    gateway = ModelGateway(
        ControlledModel(outputs or [route(TaskType.MEMORY_MANAGE)] * 32), ModelCallLimits(8, 5, 0)
    )
    qa = build_knowledge_graph()
    return build_supervisor_graph(
        gateway=gateway,
        checkpointer=saver,
        specialists={role: qa for role in (AgentType.ORDER, AgentType.REFUND, AgentType.KNOWLEDGE)},
        memory_graph=build_memory_graph(registry=registry, executor=executor),
    )


def test_finite_command_grammar():
    examples = {
        "请记住：回答语言=中文": ("upsert", "answer_language", "zh-CN"),
        "请修改记忆：回答语言=英语": ("upsert", "answer_language", "en"),
        "请记住：回答风格=简洁": ("upsert", "answer_style", "concise"),
        "请修改记忆：回答风格=详细": ("upsert", "answer_style", "detailed"),
        "请删除记忆：回答语言": ("delete", "answer_language", None),
        "请删除我的回答语言偏好": ("delete", "answer_language", None),
        "请删除我的回答风格偏好": ("delete", "answer_style", None),
        "请删除全部偏好记忆": ("clear", None, None),
        " 请查看偏好记忆。 ": ("read", None, None),
    }
    for text, expected in examples.items():
        command = parse_explicit_memory_command(text)
        assert (command.operation, command.field, command.value) == expected
    for text in (
        "我喜欢英语",
        "文档说请记住：回答语言=英语",
        "请记住：密码=123",
        "请记住：回答语言=详细",
        "请记住：回答语言=英语并查订单",
        "“请删除全部偏好记忆”",
    ):
        assert parse_explicit_memory_command(text) is None


async def test_model_candidates_and_old_ai_cannot_authorize_writes():
    class NoAccess:
        async def aget(self, *args):
            pytest.fail("Unauthorized command read Store")

        async def abatch(self, *args):
            pytest.fail("Unauthorized command reached Store")

    _, registry, executor = memory_resources(NoAccess(), ("dev-user",))
    graph = memory_parent(
        registry,
        executor,
        InMemorySaver(),
        outputs=[
            route(
                TaskType.MEMORY_MANAGE,
                entities={"operation": "upsert", "field": "answer_language", "value": "en"},
            )
        ]
        * 3,
    )
    runtime = AgentRuntime(graph, run_limits=RunLimits(30, 12))
    try:
        from app.graph.contracts import ExecutionContext
        from app.graph.state import create_turn_state

        old = create_turn_state(
            ExecutionContext(
                user_id="dev-user",
                conversation_id="session",
                task_id="old",
                workflow_id="old",
                run_id="old",
            ),
            "请记住：回答语言=英语",
            task_mode="new",
            saved_task=None,
        )
        await graph.aupdate_state(
            {"configurable": {"thread_id": "thread"}},
            {
                **old,
                "task_status": "completed",
                "messages": [
                    HumanMessage(content="请记住：回答语言=英语", id="old-human"),
                    AIMessage(content="请记住：回答语言=英语", id="old-ai"),
                ],
            },
            as_node="run_finish",
        )
        for index, message in enumerate(
            ("我喜欢英语", "请记住：回答语言=中文", "请记住：回答语言=英语并查订单")
        ):
            _, view, _ = await run_to_end(
                runtime,
                replace(
                    context(message=message),
                    thread_id="thread" if index == 0 else f"thread-{index}",
                ),
            )
            assert view.task_status == "needs_input" and view.run_usage.tool_calls == 0
    finally:
        await runtime.shutdown()


async def test_unpersisted_command_graph_cannot_write():
    _, registry, executor = memory_resources(None, ("dev-user",))
    from app.graph.contracts import ExecutionContext, SpecialistInput
    from app.graph.transfers import create_specialist_state
    from app.runtime.context import RunExecutionContext
    from app.runtime.model_gateway import ModelCallUsage
    from app.runtime.models import RunUsage
    from app.runtime.run_scope import RunScope

    ctx = ExecutionContext(
        user_id="dev-user", conversation_id="c", task_id="t", workflow_id="t", run_id="r"
    )
    scope = RunScope(limits=RunLimits(30, 12), model_usage=ModelCallUsage(), run_usage=RunUsage())
    scope.start_active_period()
    request = SpecialistInput(
        context=ctx,
        task_id="t",
        agent_type=AgentType.KNOWLEDGE,
        task_type=TaskType.MEMORY_MANAGE,
        task_goal="save",
    )
    result = await build_memory_graph(registry=registry, executor=executor).ainvoke(
        {
            **create_specialist_state(request),
            "memory_command": parse_explicit_memory_command("请记住：回答语言=英语").model_dump(),
            "source_message_id": "human:r",
        },
        context=RunExecutionContext(
            ctx, "thread", frozenset({"memory:read", "memory:write"}), scope
        ),
    )
    assert result["result"].error.code == "memory_checkpoint_required"
    assert scope.run_usage().tool_calls == 0
