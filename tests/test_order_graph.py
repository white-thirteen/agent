from datetime import UTC, datetime
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.types import AgentType, TaskType
from app.domain.orders import MockOrderService, OrderRecord
from app.graph.contracts import ExecutionContext, SpecialistInput
from app.graph.specialists.order.builder import build_order_graph
from app.graph.transfers import create_specialist_state
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import ModelCallLimits, ModelCallUsage, ModelGateway
from app.runtime.models import RunLimits, RunUsage
from app.runtime.run_scope import RunScope
from app.tools.executor import ToolExecutor
from app.tools.implementations.orders import order_tools
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry


class Repository:
    async def get_owned(self, *, owner_id, order_id):
        if owner_id != "dev-user" or order_id != "one":
            return None
        return OrderRecord(
            "one",
            owner_id,
            Decimal("12.50"),
            "CNY",
            "paid",
            False,
            datetime(2026, 1, 1, tzinfo=UTC),
        )

    async def list_owned(self, *, owner_id, limit, offset):
        order = await self.get_owned(owner_id=owner_id, order_id="one")
        return [order] if order and offset == 0 else []


class Model:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.schemas = []
        self.messages = []

    def bind_tools(self, tools):
        self.schemas.append(tools)
        return self

    async def ainvoke(self, messages):
        self.messages.append(messages)
        return next(self.replies)


def tool_call(name, args, id="call-1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id}])


async def execute_order(entities, replies, message="查询订单", run_id="run"):
    model = Model(replies)
    registry = ToolRegistry()
    for item in order_tools(MockOrderService(Repository()), timeout_seconds=1, max_retries=1):
        registry.register(item)
    registry.freeze()
    gateway = ModelGateway(model, ModelCallLimits(5, 2, 0))
    graph = build_order_graph(
        gateway=gateway, registry=registry, executor=ToolExecutor(registry, ToolPolicy())
    )
    context = ExecutionContext(
        user_id="dev-user",
        conversation_id="conv",
        task_id="task",
        workflow_id="task",
        run_id=run_id,
    )
    scope = RunScope(limits=RunLimits(10, 5), model_usage=ModelCallUsage(), run_usage=RunUsage())
    scope.start_active_period()
    request = SpecialistInput(
        context=context,
        task_id="task",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        task_goal=message,
        entities=entities,
        messages=[HumanMessage(content=message)],
    )
    result = await graph.ainvoke(
        create_specialist_state(request, scope=scope),
        context=RunExecutionContext(context, "thread", frozenset({"orders:read"}), scope),
    )
    return result, model, scope


@pytest.mark.parametrize(
    ("entities", "call", "kind"),
    [
        (
            {"query_kind": "get", "order_id": "one"},
            tool_call("get_order", {"order_id": "one"}),
            "get",
        ),
        (
            {"query_kind": "list", "limit": 5, "offset": 0},
            tool_call("list_orders", {"limit": 5, "offset": 0}),
            "list",
        ),
        (
            {"query_kind": "list", "limit": 5, "offset": 10},
            tool_call("list_orders", {"limit": 5, "offset": 10}),
            "list",
        ),
    ],
)
async def test_native_tool_round_trip_returns_verified_facts(entities, call, kind):
    result, model, scope = await execute_order(
        entities, [call, AIMessage(content="Invented answer")]
    )
    assert result["result"].status == "completed"
    assert result["result"].facts["kind"] == kind
    assert "Invented answer" not in result["result"].summary
    assert len(model.schemas[0]) == 1
    assert model.schemas[0][0]["function"]["name"] == (
        "get_order" if kind == "get" else "list_orders"
    )
    assert any(
        isinstance(message, ToolMessage) and message.tool_call_id == "call-1"
        for message in model.messages[1]
    )
    assert scope.run_usage().tool_calls == 1 and scope.model_usage().model_attempts == 2
    record = result["call_records"]["call-1"]
    assert record["origin"] == "model" and record["run_id"] == "run"
    assert record["call"] == {
        "call_id": "call-1",
        "name": call.tool_calls[0]["name"],
        "raw_args": call.tool_calls[0]["args"],
    }
    assert record["result"]["attempts"] == 1 and record["result"]["execution_id"]


async def test_model_cannot_broaden_target_or_invent_facts():
    result, _, scope = await execute_order(
        {"query_kind": "get", "order_id": "one"}, [tool_call("get_order", {"order_id": "other"})]
    )
    assert result["result"].status == "rejected" and scope.run_usage().tool_calls == 0
    result, _, scope = await execute_order(
        {"query_kind": "get", "order_id": "one"}, [AIMessage(content="invented")]
    )
    assert result["result"].status == "failed" and scope.run_usage().tool_calls == 0
    result, model, _ = await execute_order({"query_kind": "list", "order_id": "one"}, [])
    assert result["result"].status == "needs_input" and not model.schemas


async def test_parent_runtime_clarification_continues_budget_and_hides_tool_history():
    from langgraph.checkpoint.memory import InMemorySaver
    from refund_skeleton import build_refund_graph
    from runtime_support import ControlledModel, route, run_to_end
    from runtime_support import context as demo_context

    from app.graph.builder import build_supervisor_graph
    from app.graph.specialists.knowledge.builder import build_knowledge_graph
    from app.runtime.agent_runtime import AgentRuntime

    class Provider(ControlledModel):
        def __init__(self):
            super().__init__(
                [
                    route(entities={"query_kind": "get"}),
                    route(entities={"query_kind": "get", "order_id": "one"}),
                ]
            )
            self.order = Model(
                [
                    tool_call("get_order", {"order_id": "one"}),
                    AIMessage(content="untrusted candidate"),
                ]
            )

        def bind_tools(self, tools):
            return self.order.bind_tools(tools)

    model = Provider()
    gateway = ModelGateway(model, ModelCallLimits(8, 2, 0))
    registry = ToolRegistry()
    for definition in order_tools(MockOrderService(Repository()), timeout_seconds=1, max_retries=1):
        registry.register(definition)
    registry.freeze()
    order_graph = build_order_graph(
        gateway=gateway, registry=registry, executor=ToolExecutor(registry, ToolPolicy())
    )
    graph = build_supervisor_graph(
        gateway=gateway,
        checkpointer=InMemorySaver(),
        specialists={
            AgentType.ORDER: order_graph,
            AgentType.REFUND: build_refund_graph(),
            AgentType.KNOWLEDGE: build_knowledge_graph(),
        },
    )
    runtime = AgentRuntime(graph, run_limits=RunLimits(10, 5))
    try:
        first, pending, _ = await run_to_end(runtime, demo_context(message="查询单个订单"))
        assert pending.task_status == "needs_input"
        second, completed, events = await run_to_end(runtime, demo_context(message="one"))
        assert first.task_id == second.task_id and first.run_id != second.run_id
        assert completed.task_status == "completed"
        assert (
            completed.model_call_usage.model_attempts == 4 and completed.run_usage.tool_calls == 1
        )
        assert (
            "12.50" in completed.final_answer
            and "untrusted candidate" not in completed.final_answer
        )
        assert not any("call-1" in str(event.data) for event in events)
        assert not any("call_records" in str(event.data) for event in events)
        snapshot = await graph.aget_state({"configurable": {"thread_id": "thread"}})
        assert "call_records" not in snapshot.values
        assert not any(isinstance(message, ToolMessage) for message in snapshot.values["messages"])
    finally:
        await runtime.shutdown()


async def test_observe_reentry_reuses_saved_results_without_new_attempts():
    from copy import deepcopy
    from types import SimpleNamespace

    state, _, scope = await execute_order(
        {"query_kind": "get", "order_id": "one"},
        [tool_call("get_order", {"order_id": "one"}), AIMessage(content="done")],
    )
    other_state, _, other_scope = await execute_order(
        {"query_kind": "get", "order_id": "one"},
        [tool_call("get_order", {"order_id": "one"}), AIMessage(content="done")],
        run_id="another-run",
    )
    assert state["call_records"]["call-1"]["run_id"] == "run"
    assert other_state["call_records"]["call-1"]["run_id"] == "another-run"
    assert other_scope.run_usage().tool_calls == 1
    registry = ToolRegistry()
    registry.freeze()
    graph = build_order_graph(
        gateway=None, registry=registry, executor=ToolExecutor(registry, ToolPolicy())
    )
    observe = graph.nodes["observe_order"].node.steps[0].func
    before = scope.run_usage().tool_calls
    records = deepcopy(state["call_records"])
    runtime = SimpleNamespace(context=SimpleNamespace(scope=scope))
    first = observe(state, runtime)
    second = observe(state, runtime)
    assert scope.run_usage().tool_calls == before == 1
    assert first["messages"][0].id == second["messages"][0].id
    assert first["messages"][0].content == second["messages"][0].content
    assert first["verified_order_facts"] == second["verified_order_facts"]
    assert state["call_records"] == records
    assert records["call-1"]["origin"] == "model"
