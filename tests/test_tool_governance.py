"""Tool discovery, policies and counted execution at the real governance boundary."""

import asyncio
import subprocess
import sys
from contextlib import asynccontextmanager
from dataclasses import replace

import psycopg
import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict

from app.agents.types import AgentType, TaskType
from app.domain.orders import MockOrderService, OrderRepository
from app.graph.contracts import ExecutionContext
from app.runtime.model_gateway import ModelCallUsage
from app.runtime.models import RunLimits, RunUsage
from app.runtime.run_scope import RunScope
from app.tools.executor import ToolExecutor
from app.tools.implementations.orders import GetOrderArgs, order_tools
from app.tools.messages import parse_tool_calls, to_tool_message
from app.tools.models import (
    HandlerResult,
    ParsedToolCall,
    ToolDefinition,
    ToolExecutionContext,
    ToolMetadata,
    ToolTransientError,
)
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int


def metadata(**updates):
    base = dict(
        name="get_order",
        version="1",
        description="test",
        enabled=True,
        allowed_agents=frozenset({AgentType.ORDER}),
        required_scopes=frozenset({"orders:read"}),
        risk_level="low",
        approval_required=False,
        read_only=True,
        has_business_side_effects=False,
        idempotency="not_applicable",
        timeout_seconds=0.05,
        max_retries=1,
        tags=frozenset(),
    )
    base.update(updates)
    return ToolMetadata(**base)


def setup(handler, *, meta=None, max_tools=12):
    registry = ToolRegistry()
    definition = ToolDefinition(meta or metadata(), GetOrderArgs, Data, handler)
    registry.register(definition)
    registry.freeze()
    scope = RunScope(
        limits=RunLimits(10, max_tools), model_usage=ModelCallUsage(), run_usage=RunUsage()
    )
    scope.start_active_period()
    execution = ExecutionContext(
        user_id="dev-user", conversation_id="conv", task_id="task", workflow_id="task", run_id="run"
    )
    context = ToolExecutionContext(
        execution,
        AgentType.ORDER,
        TaskType.ORDER_QUERY,
        None,
        frozenset({"orders:read"}),
        "model",
        frozenset({("get_order", "1")}),
        {"get_order": {"order_id": "order-1"}},
        RunLimits(10, max_tools),
        scope,
    )
    return registry, ToolExecutor(registry, ToolPolicy()), context


def test_order_domain_import_does_not_load_upper_layers():
    probe = (
        "import sys; import app.domain.orders; "
        "assert not any(n.startswith(('app.tools', 'app.graph', 'app.runtime')) "
        "for n in sys.modules)"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", ["get_order", "list_orders"])
@pytest.mark.parametrize(
    ("error", "attempts"), [(psycopg.OperationalError, 2), (psycopg.ProgrammingError, 1)]
)
async def test_order_data_errors_through_adapters_and_executor(name, error, attempts):
    class FailingPool:
        def __init__(self):
            self.attempts = 0

        @asynccontextmanager
        async def connection(self):
            self.attempts += 1
            raise error("controlled database failure")
            yield

    pool = FailingPool()
    registry = ToolRegistry()
    for definition in order_tools(
        MockOrderService(OrderRepository(pool)), timeout_seconds=1, max_retries=1
    ):
        registry.register(definition)
    registry.freeze()
    _, _, context = setup(definition.handler)
    args = {"order_id": "order-1"} if name == "get_order" else {"limit": 5, "offset": 0}
    context = replace(
        context, allowed_tools=frozenset({(name, "1")}), argument_constraints={name: args}
    )
    result = await ToolExecutor(registry, ToolPolicy()).execute(
        ParsedToolCall("call", name, args), context=context
    )
    assert result.status == "failed" and result.code == "order_query_unavailable"
    assert result.attempts == pool.attempts == context.scope.run_usage().tool_calls == attempts
    assert result.data is None


@pytest.mark.parametrize("error", [ValueError, asyncio.CancelledError])
async def test_order_adapter_propagates_unexpected_errors_and_cancellation(error):
    class FailingRepository:
        async def get_owned(self, **kwargs):
            raise error()

    definition = order_tools(
        MockOrderService(FailingRepository()), timeout_seconds=1, max_retries=1
    )[0]
    _, executor, context = setup(definition.handler)
    with pytest.raises(error):
        await executor.execute(
            ParsedToolCall("call", "get_order", {"order_id": "order-1"}), context=context
        )
    assert context.scope.run_usage().tool_calls == 1


async def test_registry_filters_freezes_and_exposes_complete_schema():
    async def handler(args, context):
        return HandlerResult(data=Data(value=1))

    registry = ToolRegistry()
    definition = ToolDefinition(metadata(), GetOrderArgs, Data, handler)
    registry.register(definition)
    with pytest.raises(ValueError):
        registry.register(definition)
    with pytest.raises(RuntimeError):
        registry.list(agent_type=AgentType.ORDER, permission_scopes=frozenset())
    registry.freeze()
    with pytest.raises(RuntimeError):
        registry.register(definition)
    assert not registry.list(
        agent_type=AgentType.SUPERVISOR, permission_scopes=frozenset({"orders:read"})
    )
    assert not registry.list(agent_type=AgentType.ORDER, permission_scopes=frozenset())
    view = registry.list(agent_type=AgentType.ORDER, permission_scopes=frozenset({"orders:read"}))[
        0
    ]
    assert view.model_schema["function"]["parameters"]["properties"]["order_id"]
    assert not hasattr(view, "handler")


async def test_executor_enforces_scope_schema_target_approval_and_minimal_handler_context():
    seen = []

    async def handler(args, context):
        seen.append((args, context))
        return HandlerResult(data=Data(value=1))

    registry, executor, ctx = setup(handler)
    for call, context in [
        (ParsedToolCall("1", "get_order", {"order_id": "another"}), ctx),
        (ParsedToolCall("2", "get_order", {"order_id": "order-1", "user_id": "other"}), ctx),
        (ParsedToolCall("3", "list_orders", {}), ctx),
        (
            ParsedToolCall("4", "get_order", {"order_id": "order-1"}),
            replace(ctx, permission_scopes=frozenset()),
        ),
    ]:
        assert (await executor.execute(call, context=context)).status == "policy_denied"
    assert not seen and ctx.scope.run_usage().tool_calls == 0
    good = ParsedToolCall("5", "get_order", {"order_id": "order-1"})
    result = await executor.execute(good, context=ctx)
    assert result.status == "success" and result.attempts == 1 and result.run_usage.tool_calls == 1
    assert isinstance(seen[0][0], GetOrderArgs)
    assert set(seen[0][1].__dataclass_fields__) == {"user_id", "task_id", "run_id"}
    high = metadata(risk_level="high", approval_required=True)
    _, executor, ctx = setup(handler, meta=high)
    result = await executor.execute(good, context=ctx)
    assert result.status == "approval_required" and result.code == "approval_not_available"
    assert result.attempts == 0 and ctx.scope.run_usage().tool_calls == 0 and len(seen) == 1


async def test_preflight_then_serial_failure_closes_batch_and_counts_retry():
    seen = []

    async def handler(args, context):
        seen.append(args.order_id)
        if len(seen) == 1:
            raise ToolTransientError()
        return HandlerResult(data=Data(value=1))

    _, executor, ctx = setup(handler)
    calls = [
        ParsedToolCall("a", "get_order", {"order_id": "order-1"}),
        ParsedToolCall("b", "get_order", {"order_id": "other"}),
        ParsedToolCall("c", "get_order", {"order_id": "order-1"}),
    ]
    results = await executor.execute_batch(calls, context=ctx)
    assert [r.status for r in results] == ["success", "policy_denied", "not_executed"]
    assert [r.attempts for r in results] == [2, 0, 0] and ctx.scope.run_usage().tool_calls == 2
    assert [to_tool_message(r, task_id="task").tool_call_id for r in results] == ["a", "b", "c"]
    with pytest.raises(ValueError):
        parse_tool_calls(
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "same", "name": "get_order", "args": {}},
                    {"id": "same", "name": "get_order", "args": {}},
                ],
            ),
            used_ids=set(),
            max_calls=4,
        )
    assert len(seen) == 2


async def test_timeout_and_cancellation_do_not_retry_or_run_next_handler():
    started = asyncio.Event()

    async def handler(args, context):
        started.set()
        await asyncio.Event().wait()

    _, executor, ctx = setup(handler)
    call = ParsedToolCall("a", "get_order", {"order_id": "order-1"})
    result = await executor.execute(call, context=ctx)
    assert result.code == "tool_timeout" and result.attempts == 1
    ctx.scope.start_active_period()
    task = asyncio.create_task(executor.execute(call, context=ctx))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_retry_rechecks_remaining_budget_and_preserves_normalized_arguments():
    attempts = 0

    async def handler(args, context):
        nonlocal attempts
        attempts += 1
        raise ToolTransientError()

    _, executor, ctx = setup(handler, max_tools=1)
    result = await executor.execute(
        ParsedToolCall("a", "get_order", {"order_id": "order-1"}), context=ctx
    )
    assert result.code == "tool_budget_exceeded"
    assert result.attempts == attempts == ctx.scope.run_usage().tool_calls == 1
    assert result.normalized_args == {"order_id": "order-1"}
