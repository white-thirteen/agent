"""Shared preference read behavior, policy boundaries and resource cleanup."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import psycopg
import pytest
from langchain_core.messages import HumanMessage

from app.agents.types import AgentType, TaskType
from app.core.config import Settings
from app.graph.contracts import ExecutionContext, SpecialistInput
from app.graph.specialists.preferences import read_optional_preferences
from app.memory.manager import MemoryManager
from app.memory.reader import MemoryReader
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import ModelCallUsage
from app.runtime.models import RunLimits, RunUsage
from app.runtime.run_scope import RunScope
from app.tools.executor import ToolExecutor
from app.tools.implementations.memory import read_preferences_tool
from app.tools.models import ParsedToolCall, ToolExecutionContext, ToolUnavailableError
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry


class Resource:
    def __init__(self, value=None, failure=None):
        self.value, self.failure, self.calls = value, failure, []

    async def aget(self, namespace, key):
        self.calls.append((namespace, key))
        if self.failure:
            raise self.failure
        return None if self.value is None else SimpleNamespace(value=self.value)


def profile(**preferences):
    return {
        "schema_version": 1,
        "revision": 3,
        "preferences": preferences,
        "last_mutation": {"operation_id": "private-metadata"},
    }


def setup(resource, *, scopes=frozenset({"memory:read"}), max_calls=12):
    manager = MemoryManager(resource, user_ids=("a", "b"))
    registry = ToolRegistry()
    registry.register(read_preferences_tool(MemoryReader(manager), enabled=True))
    registry.freeze()
    executor = ToolExecutor(registry, ToolPolicy())
    ctx = ExecutionContext(
        user_id="a", conversation_id="conv", task_id="task", workflow_id="task", run_id="run"
    )
    scope = RunScope(
        limits=RunLimits(30, max_calls), model_usage=ModelCallUsage(), run_usage=RunUsage()
    )
    scope.start_active_period()
    execution = RunExecutionContext(ctx, "thread", scopes, scope)
    request = SpecialistInput(
        context=ctx,
        task_id=ctx.task_id,
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        task_goal="query",
        messages=[HumanMessage(content="query")],
    )
    return manager, registry, executor, SimpleNamespace(context=execution), {"request": request}


@pytest.mark.parametrize(
    ("value", "status", "preferences"),
    [
        (None, "empty", {}),
        (
            profile(answer_language="en", answer_style="concise"),
            "available",
            {"answer_language": "en", "answer_style": "concise"},
        ),
        (
            profile(answer_language="en", answer_style="SECRET"),
            "partial",
            {"answer_language": "en"},
        ),
        (profile(SECRET="bad"), "partial", {}),
    ],
)
async def test_snapshot_is_exact_safe_projection(value, status, preferences):
    resource = Resource(value)
    manager, *_ = setup(resource)
    result = await manager.snapshot(user_id="a")
    assert result.status == status and result.preferences == preferences
    assert resource.calls == [(("users", "a", "preferences"), "profile")]
    assert (
        "SECRET" not in result.model_dump_json()
        and "private-metadata" not in result.model_dump_json()
    )
    with pytest.raises(ValueError):
        await manager.snapshot(user_id="unlisted")
    assert len(resource.calls) == 1


@pytest.mark.parametrize(
    "value",
    [
        {**profile(), "schema_version": 2},
        {**profile(), "revision": True},
        {**profile(), "revision": -1},
        {**profile(), "preferences": []},
        {**profile(), "last_mutation": "x" * 2048},
    ],
)
async def test_corrupt_profile_fails_without_adopting_data(value):
    manager, *_ = setup(Resource(value))
    with pytest.raises(ToolUnavailableError, match="invalid"):
        await manager.snapshot(user_id="a")


async def test_optional_read_policy_budget_cancel_and_reentry():
    resource = Resource(profile(answer_language="en"))
    _, registry, executor, runtime, state = setup(resource)
    first = await read_optional_preferences(
        state, runtime, registry=registry, executor=executor, node="prepare_query"
    )
    assert first["memory_read_status"] == "available"
    assert "messages" not in first and first["run_usage"]["tool_calls"] == 1
    record = first["memory_read_record"]
    assert record["origin"] == "node" and record["node_name"] == "prepare_query"
    assert record["result"]["execution_id"] and record["result"]["attempts"] == 1
    replay = await read_optional_preferences(
        {**state, **first}, runtime, registry=registry, executor=executor, node="prepare_query"
    )
    assert replay["memory_read_record"] == record and len(resource.calls) == 1
    runtime.context = replace(runtime.context, permission_scopes=frozenset())
    denied = await read_optional_preferences(
        {**state, **first}, runtime, registry=registry, executor=executor, node="prepare_query"
    )
    assert denied["memory_read_status"] == "denied"
    assert denied["memory_read_record"]["result"]["code"] == "memory_scope_denied"
    assert denied["memory_read_record"]["result"]["attempts"] == 0
    assert len(resource.calls) == 1
    # Policy independently rejects forged origin/node/argument/allowed-set changes.
    ctx = ToolExecutionContext(
        runtime.context.context,
        AgentType.ORDER,
        TaskType.ORDER_QUERY,
        "prepare_query",
        frozenset({"memory:read"}),
        "node",
        frozenset({("read_preferences", "1")}),
        {"read_preferences": {}},
        runtime.context.scope.limits,
        runtime.context.scope,
    )
    call = ParsedToolCall("forged", "read_preferences", {})
    for forged in [
        replace(ctx, origin="model", node_name=None),
        replace(ctx, node_name="other"),
        replace(ctx, allowed_tools=ctx.allowed_tools | {("get_order", "1")}),
        replace(ctx, argument_constraints={}),
    ]:
        result = await executor.execute(call, context=forged)
        assert result.status == "policy_denied" and result.attempts == 0
    assert len(resource.calls) == 1
    _, registry, executor, runtime, state = setup(Resource(failure=psycopg.OperationalError()))
    unavailable = await read_optional_preferences(
        state, runtime, registry=registry, executor=executor, node="prepare_query"
    )
    assert unavailable["memory_read_status"] == "unavailable" and not unavailable.get("outcome")
    _, registry, executor, runtime, state = setup(Resource(), max_calls=1)
    exhausted = await read_optional_preferences(
        state, runtime, registry=registry, executor=executor, node="prepare_query"
    )
    assert exhausted["outcome"] == "failed" and exhausted["error_code"] == "tool_budget_exceeded"
    _, registry, executor, runtime, state = setup(Resource(failure=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await read_optional_preferences(
            state, runtime, registry=registry, executor=executor, node="prepare_query"
        )


async def test_store_owns_cleanup_on_success_exception_and_startup_failure(monkeypatch):
    import app.infrastructure.store as module

    events = []
    tasks = []

    class Pool:
        async def open(self):
            events.append("open")

        async def wait(self, **kwargs):
            if fail_start:
                raise TypeError("startup")

        async def close(self):
            events.append("pool_closed")

    class Store:
        def __init__(self, **kwargs):
            assert kwargs["index"] is None and kwargs["ttl"] is None
            self._task = asyncio.create_task(asyncio.Event().wait())
            tasks.append(self._task)

        async def __aenter__(self):
            events.append("store_enter")
            return self

        async def __aexit__(self, *args):
            assert self._task.done()
            events.append("store_exit")

    def pool(**kwargs):
        assert kwargs["min_size"] == 1 and kwargs["max_size"] == 3
        assert kwargs["kwargs"]["autocommit"] and kwargs["kwargs"]["prepare_threshold"] == 0
        return Pool()

    monkeypatch.setattr(module, "AsyncConnectionPool", pool)
    monkeypatch.setattr(module, "AsyncPostgresStore", Store)
    settings = Settings(_env_file=None, database_url="postgresql://app:unused@localhost/agent_demo")
    fail_start = False
    for fail_body in (False, True):
        events.clear()
        try:
            async with module.store_resources(settings, verify_setup=False):
                if fail_body:
                    raise ValueError("body")
        except ValueError:
            assert fail_body
        assert events == ["open", "store_enter", "store_exit", "pool_closed"]
        assert tasks[-1].done()
    fail_start = True
    events.clear()
    with pytest.raises(TypeError):
        async with module.store_resources(settings, verify_setup=False):
            pass
    assert events == ["open", "pool_closed"]


@pytest.mark.parametrize(
    ("agent", "task", "node"),
    [
        (AgentType.ORDER, TaskType.ORDER_QUERY, "prepare_query"),
        (AgentType.REFUND, TaskType.REFUND_APPLY, "prepare_refund"),
        (AgentType.KNOWLEDGE, TaskType.KNOWLEDGE_QA, "prepare_query"),
    ],
)
async def test_three_preparation_nodes_share_reader_without_tool_messages(agent, task, node):
    from app.graph.specialists.knowledge.builder import build_knowledge_graph
    from app.graph.specialists.order.builder import build_order_graph
    from app.graph.specialists.refund.builder import build_refund_graph
    from app.graph.transfers import create_specialist_state

    resource = Resource(profile(answer_style="detailed"))
    _, registry, executor, runtime, state = setup(
        resource, scopes=frozenset({"memory:read", "knowledge:read"})
    )
    request = state["request"].model_copy(
        update={"agent_type": agent, "task_type": task, "messages": []}
    )
    if agent is AgentType.ORDER:
        graph = build_order_graph(gateway=None, registry=registry, executor=executor)
    elif agent is AgentType.REFUND:
        graph = build_refund_graph(
            gateway=None,
            registry=registry,
            executor=executor,
            approval_service=None,
            refund_service=None,
        )
    else:
        graph = build_knowledge_graph(
            gateway=object(), registry=registry, executor=executor, profile="test"
        )
    result = await graph.ainvoke(
        create_specialist_state(request, scope=runtime.context.scope), context=runtime.context
    )
    assert result["result"].status == "needs_input"
    assert result["memory_read_status"] == "available"
    assert result["memory_context"]["preferences"] == {"answer_style": "detailed"}
    assert len(resource.calls) == 1 and result["run_usage"]["tool_calls"] == 1
    assert not result["messages"]
    assert result["memory_read_record"]["node_name"] == node


async def test_order_preferences_do_not_change_facts_or_bound_tool_schema():
    from langchain_core.messages import AIMessage, ToolMessage
    from test_order_graph import Model, Repository, tool_call

    from app.domain.orders import MockOrderService
    from app.graph.specialists.order.builder import build_order_graph
    from app.graph.transfers import create_specialist_state
    from app.runtime.model_gateway import ModelCallLimits, ModelGateway
    from app.tools.implementations.orders import order_tools

    resource = Resource(profile(answer_language="en", answer_style="concise"))
    manager = MemoryManager(resource, user_ids=("dev-user",))
    registry = ToolRegistry()
    registry.register(read_preferences_tool(MemoryReader(manager), enabled=True))
    for definition in order_tools(MockOrderService(Repository()), timeout_seconds=1, max_retries=0):
        registry.register(definition)
    registry.freeze()
    _, _, _, runtime, state = setup(resource, scopes=frozenset({"memory:read", "orders:read"}))
    ctx = runtime.context.context.model_copy(update={"user_id": "dev-user"})
    runtime.context = replace(runtime.context, context=ctx)
    request = state["request"].model_copy(
        update={"context": ctx, "entities": {"query_kind": "get", "order_id": "one"}}
    )
    model = Model([tool_call("get_order", {"order_id": "one"}), AIMessage(content="invented")])
    graph = build_order_graph(
        gateway=ModelGateway(model, ModelCallLimits(5, 2, 0)),
        registry=registry,
        executor=ToolExecutor(registry, ToolPolicy()),
    )
    result = await graph.ainvoke(
        create_specialist_state(request, scope=runtime.context.scope), context=runtime.context
    )
    assert result["result"].status == "completed"
    assert result["result"].facts["order"]["amount"] == "12.50"
    assert "12.50 CNY" in result["result"].summary and "invented" not in result["result"].summary
    assert [s["function"]["name"] for s in model.schemas[0]] == ["get_order"]
    assert '"answer_language":"en"' in model.messages[0][0].content
    assert result["run_usage"]["tool_calls"] == 2
    assert [m.tool_call_id for m in result["messages"] if isinstance(m, ToolMessage)] == ["call-1"]


async def test_snapshot_does_not_swallow_unexpected_value_error():
    failure = ValueError("programming error")
    manager, *_ = setup(Resource(failure=failure))
    with pytest.raises(ValueError) as raised:
        await manager.snapshot(user_id="a")
    assert raised.value is failure
