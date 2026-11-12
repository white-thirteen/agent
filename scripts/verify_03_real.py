"""Opt-in stage 03 real model and test database acceptance; emits safe categories only."""

import logging

from langchain_core.messages import HumanMessage, ToolMessage

from app.agents.types import AgentType, TaskType
from app.core.config import Settings
from app.domain.orders import MockOrderService, OrderNotAccessible, OrderRepository
from app.graph.contracts import ExecutionContext, SpecialistInput
from app.graph.specialists.order.builder import build_order_graph
from app.graph.transfers import create_specialist_state
from app.infrastructure.model import model_resources
from app.infrastructure.postgres import open_pool, validate_test_target
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import ModelCallUsage
from app.runtime.models import RunLimits, RunUsage
from app.runtime.run_scope import RunScope
from app.tools.executor import ToolExecutor
from app.tools.implementations.orders import order_tools
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from scripts import run_async


async def main():
    logging.disable(logging.CRITICAL)
    settings = Settings()
    assert settings.test_database_url and settings.model_configured
    validate_test_target(settings.test_database_url, settings.database_url)
    test_settings = settings.model_copy(update={"database_url": settings.test_database_url})
    pool = await open_pool(test_settings)
    try:
        async with pool.connection() as conn:
            identity = await (
                await conn.execute("SELECT current_database(), current_user")
            ).fetchone()
            assert identity == ("agent_demo_test", "agent_test")
            versions = await (
                await conn.execute("SELECT version FROM schema_migrations ORDER BY version")
            ).fetchall()
            assert versions == [(1,), (2,), (3,)]
        service = MockOrderService(OrderRepository(pool))
        for order in ("demo-order-b-001", "missing-order-03"):
            try:
                await service.get_order(user_id="dev-user", order_id=order)
            except OrderNotAccessible:
                pass
            else:
                raise AssertionError("Owner isolation failure")
        assert not await service.list_orders(user_id="dev-user", limit=5, offset=100)
        print("PG_IDENTITY_SCHEMA_OWNER_EMPTY_PAGE_OK", flush=True)
        registry = ToolRegistry()
        for definition in order_tools(service, timeout_seconds=5, max_retries=1):
            registry.register(definition)
        registry.freeze()
        async with model_resources(settings) as (_, gateway):
            graph = build_order_graph(
                gateway=gateway, registry=registry, executor=ToolExecutor(registry, ToolPolicy())
            )
            for kind, entities in [
                ("get", {"query_kind": "get", "order_id": "demo-order-a-001"}),
                ("list", {"query_kind": "list", "limit": 5, "offset": 0}),
            ]:
                context = ExecutionContext(
                    user_id="dev-user",
                    conversation_id="real-03",
                    task_id="real-" + kind,
                    workflow_id="real-" + kind,
                    run_id="run-" + kind,
                )
                scope = RunScope(
                    limits=RunLimits(120, 12), model_usage=ModelCallUsage(), run_usage=RunUsage()
                )
                scope.start_active_period()
                text = "查询我的模拟订单"
                request = SpecialistInput(
                    context=context,
                    task_id=context.task_id,
                    agent_type=AgentType.ORDER,
                    task_type=TaskType.ORDER_QUERY,
                    task_goal=text,
                    entities=entities,
                    messages=[HumanMessage(content=text)],
                )
                state = await graph.ainvoke(
                    create_specialist_state(request, scope=scope),
                    context=RunExecutionContext(
                        context, "real-" + kind, frozenset({"orders:read"}), scope
                    ),
                )
                result = state["result"]
                assert result.status == "completed", (
                    kind,
                    result.status,
                    result.error.code if result.error else None,
                )
                assert result.facts["kind"] == kind
                assert any(isinstance(m, ToolMessage) for m in state["messages"])
                if kind == "get":
                    expected = await service.get_order(
                        user_id="dev-user", order_id="demo-order-a-001"
                    )
                    assert result.facts["order"] == expected.model_dump(mode="json")
                else:
                    expected = await service.list_orders(user_id="dev-user", limit=5, offset=0)
                    assert result.facts["orders"] == [o.model_dump(mode="json") for o in expected]
                print(
                    "REAL_MODEL_PG_" + kind.upper() + "_OK",
                    "model_attempts=" + str(scope.model_usage().model_attempts),
                    "tool_attempts=" + str(scope.run_usage().tool_calls),
                    flush=True,
                )
    finally:
        await pool.close()


if __name__ == "__main__":
    try:
        run_async(main())
    except Exception as exc:
        print("REAL_ACCEPTANCE_FAILED", type(exc).__name__, flush=True)
        raise SystemExit(1) from None
