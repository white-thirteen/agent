"""Manual, explicit opt-in paid model validation; invoke this file explicitly."""

import json
import os
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from test_tool_progressive_disclosure import (
    _build_controlled_multi_candidate_order_node,
    _build_full_registry,
    _execution,
    _scope,
)

from app.agents.types import AgentType, TaskType
from app.core.config import Settings
from app.domain.orders import MockOrderService, OrderRepository
from app.graph.contracts import ExecutionContext, SpecialistInput
from app.infrastructure.model import model_resources
from app.infrastructure.postgres import open_pool, validate_test_target
from app.runtime.context import RunExecutionContext
from app.tools.discovery import PurposeSpec
from app.tools.executor import ToolExecutor
from app.tools.implementations.orders import order_tools
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from app.tools.selector import ToolSelector


async def test_opt_in_real_selector_independent():
    """Evaluate all fixed independent-selector cases and preserve provider evidence."""
    import json
    import time
    from dataclasses import asdict
    from pathlib import Path

    from app.runtime.model_gateway import ModelCallError

    settings = Settings().model_copy(
        update={"context_model_window_tokens": 16384, "context_model_output_tokens": 512}
    )
    if not settings.model_configured or os.environ.get("AGENT_RUN_REAL_MODEL_TESTS") != "1":
        pytest.skip("Requires configured model and AGENT_RUN_REAL_MODEL_TESTS=1")
    fixture = json.loads(
        Path("docs/v2/v2-03/evidence/v2-03-selector-quality-fixtures.json").read_text(
            encoding="utf-8"
        )
    )
    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.order.multi_independent",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset(fixture["trusted_candidate_names"]),
        max_selected_tools=fixture["max_selected_tools"],
        require_tool=fixture["require_tool"],
    )
    async with model_resources(settings) as (_, gateway):
        selector = ToolSelector(
            registry,
            gateway,
            max_selector_attempts=settings.tool_selector_max_attempts,
            selector_timeout_seconds=settings.tool_selector_timeout_seconds,
        )
        original = gateway._call_recorded
        usage = []

        async def observed(*args, **kwargs):
            try:
                result = await original(*args, **kwargs)
            except ModelCallError as error:
                usage.append(asdict(error.usage))
                raise
            usage.append(asdict(result.usage))
            return result

        gateway._call_recorded = observed
        evidence = []
        for case in fixture["cases"]:
            scope = _scope()
            start = time.monotonic()
            before = len(usage)
            result = await selector.select(
                execution=_execution(task_id="quality-" + case["id"]),
                agent_type=AgentType.ORDER,
                task_type=TaskType.ORDER_QUERY,
                purpose_spec=purpose,
                permission_scopes=frozenset({"orders:read"}),
                scope=scope,
                need_text=case["need"],
            )
            selected = sorted(result.binding.tool_names) if result.binding else []
            action = "use_tools" if result.status == "selected" else result.status
            evidence.append(
                {
                    "id": case["id"],
                    "need": case["need"],
                    "status": result.status,
                    "error_code": result.error_code,
                    "selected": selected,
                    "expected_action": case["expected_action"],
                    "expected_tools": case["expected_tools"],
                    "legal": set(selected) <= purpose.allowed_tools,
                    "suitable": action == case["expected_action"]
                    and selected == case["expected_tools"],
                    "attempts": scope.model_usage().model_attempts,
                    "usage": usage[before:],
                    "latency_seconds": round(time.monotonic() - start, 3),
                }
            )
        print(json.dumps({"cases": evidence}, ensure_ascii=True))
        assert all(item["legal"] and item["suitable"] for item in evidence)


async def test_opt_in_real_selector_and_controlled_multi_candidate_pg_chain():
    """Real model and isolated PG; every inserted order has a unique owner and ID."""
    from uuid import uuid4

    from langchain_core.messages import ToolMessage
    from psycopg.conninfo import conninfo_to_dict
    from pydantic import SecretStr

    raw_test_db = os.environ.get("AGENT_TEST_DATABASE_URL")
    settings = Settings().model_copy(
        update={"context_model_window_tokens": 16384, "context_model_output_tokens": 512}
    )
    if (
        not raw_test_db
        or not settings.model_configured
        or os.environ.get("AGENT_RUN_REAL_MODEL_TESTS") != "1"
    ):
        pytest.skip("Requires explicit model opt-in and isolated test database")
    test_url = SecretStr(raw_test_db)
    validate_test_target(test_url, settings.database_url)
    info = conninfo_to_dict(raw_test_db)
    assert (info.get("host"), info.get("port"), info.get("dbname"), info.get("user")) == (
        "127.0.0.1",
        "56431",
        "agent_demo_test",
        "agent_test",
    )
    token = uuid4().hex
    owner = "v203-owner-" + token
    order_id = "v203-order-" + token + "-a"
    order_ids = [order_id, "v203-order-" + token + "-b", "v203-order-" + token + "-c"]
    foreign_owner = "v203-other-" + token
    foreign_id = "v203-order-" + token + "-foreign"
    guard_passed = False
    pool = await open_pool(Settings(_env_file=None, app_env="test", database_url=test_url))
    try:
        async with pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT current_database(), current_user, "
                    "current_setting('server_version_num'), shobj_description(oid,'pg_database') "
                    "FROM pg_database WHERE datname=current_database()"
                )
            ).fetchone()
            assert row == ("agent_demo_test", "agent_test", "170012", "codex-task131-0e62")
            guard_passed = True
            for index, identifier in enumerate(order_ids):
                await conn.execute(
                    "INSERT INTO demo_orders VALUES (%s,%s,%s,'CNY','paid',false,now())",
                    (identifier, owner, Decimal("128.50") + index),
                )
            await conn.execute(
                "INSERT INTO demo_orders VALUES (%s,%s,%s,'CNY','paid',false,now())",
                (foreign_id, foreign_owner, Decimal("999.00")),
            )
        async with model_resources(settings) as (_, gateway):
            import time
            from dataclasses import asdict

            from app.runtime.model_gateway import ModelCallError

            evidence = []
            bindings = []
            decisions = []
            original = gateway._call_recorded
            original_model = gateway._model

            class ObservedModel:
                def __getattr__(self, name):
                    return getattr(original_model, name)

                def bind_tools(self, schemas):
                    bindings.append([schema["function"]["name"] for schema in schemas])
                    return original_model.bind_tools(schemas)

            class ObservedPolicy(ToolPolicy):
                def evaluate(self, **kwargs):
                    result = super().evaluate(**kwargs)
                    decisions.append(
                        {
                            "tool": kwargs["call"].name,
                            "call_id": kwargs["call"].call_id,
                            "decision": result.decision.value,
                            "code": result.code,
                        }
                    )
                    return result

            gateway._model = ObservedModel()

            async def observed(*args, **kwargs):
                started = time.monotonic()
                try:
                    result = await original(*args, **kwargs)
                except ModelCallError as error:
                    evidence.append(
                        {
                            "stage": "selector" if kwargs["structured"] else "business",
                            "error": error.code,
                            "usage": asdict(error.usage),
                            "attempts": error.model_usage.model_attempts,
                            "seconds": round(time.monotonic() - started, 3),
                        }
                    )
                    raise
                evidence.append(
                    {
                        "stage": "selector" if kwargs["structured"] else "business",
                        "usage": asdict(result.usage),
                        "attempts": result.model_usage.model_attempts,
                        "seconds": round(time.monotonic() - started, 3),
                    }
                )
                return result

            gateway._call_recorded = observed
            registry = ToolRegistry()
            for definition in order_tools(
                MockOrderService(OrderRepository(pool)), timeout_seconds=5, max_retries=1
            ):
                registry.register(definition)
            registry.freeze()
            executor = ToolExecutor(registry, ObservedPolicy())
            selection_observations = []
            graph = _build_controlled_multi_candidate_order_node(
                gateway=gateway,
                registry=registry,
                executor=executor,
                selector=ToolSelector(registry, gateway),
                observer=selection_observations,
            )
            for kind, entities, text in (
                ("get_order", {"order_id": order_id}, f"查询订单号 {order_id} 的详细信息"),
                (
                    "list_orders",
                    {"limit": 2, "offset": 1},
                    "分页查看我的模拟订单列表，跳过第一条，接着查看两条",
                ),
            ):
                evidence.clear()
                bindings.clear()
                decisions.clear()
                selection_observations.clear()
                task_id = f"v203-{kind}-{token}"
                ctx = ExecutionContext(
                    user_id=owner,
                    conversation_id="v203-" + token,
                    workflow_id=task_id,
                    task_id=task_id,
                    run_id=task_id,
                )
                scope = _scope()
                req = SpecialistInput(
                    context=ctx,
                    task_id=task_id,
                    agent_type=AgentType.ORDER,
                    task_type=TaskType.ORDER_QUERY,
                    task_goal=text,
                    entities=entities,
                    messages=[HumanMessage(content=text, id="u-" + task_id)],
                )
                try:
                    out = await graph.ainvoke(
                        {
                            "request": req,
                            "messages": list(req.messages),
                            "selected_tools": [],
                            "tool_selection_record": None,
                        },
                        context=RunExecutionContext(
                            context=ctx,
                            thread_id="thread-" + task_id,
                            permission_scopes=frozenset({"orders:read"}),
                            scope=scope,
                        ),
                    )
                except Exception:
                    print(
                        json.dumps({"case": kind, "provider_calls": evidence}, ensure_ascii=True)
                    )
                    raise
                print(
                    json.dumps(
                        {
                            "case": kind,
                            "status": out.get("outcome"),
                            "error": out.get("error_code"),
                            "provider_calls": evidence,
                            "selection_observations": selection_observations,
                            "bindings": bindings,
                            "decisions": decisions,
                        },
                        ensure_ascii=True,
                        default=str,
                    )
                )
                assert out["outcome"] == "completed" and out["selection_method"] == "model"
                assert out["selected_tools"] == [(kind, "1")]
                ai = next(m for m in out["messages"] if isinstance(m, AIMessage) and m.tool_calls)
                tool = next(m for m in out["messages"] if isinstance(m, ToolMessage))
                assert len(ai.tool_calls) == 1 and ai.tool_calls[0]["id"] == tool.tool_call_id
                print(
                    json.dumps(
                        {
                            "case": kind,
                            "candidate_count": len(selection_observations[0]["candidates"]),
                            "candidates": selection_observations[0]["candidates"],
                            "binding_record": selection_observations[0],
                            "actual_bound_tools": bindings,
                            "policy_decisions": decisions,
                            "tool_call": ai.tool_calls[0],
                            "tool_message": {
                                "call_id": tool.tool_call_id,
                                "status": tool.status,
                                "name": tool.name,
                            },
                            "selected": out["selected_tools"],
                            "selection": out["tool_selection_record"],
                            "call_id": ai.tool_calls[0]["id"],
                            "tool_message_id": tool.tool_call_id,
                            "policy_executor_result": out["tool_results"][0],
                            "provider_calls": evidence,
                            "context_window": 16384,
                            "output_reserve": 512,
                        },
                        ensure_ascii=True,
                        default=str,
                    )
                )
                assert ai.tool_calls[0]["args"] == entities
                assert scope.model_usage().model_attempts >= 2 and scope.run_usage().tool_calls == 1
                async with pool.connection() as conn:
                    if kind == "get_order":
                        rows = await (
                            await conn.execute(
                                "SELECT order_id, amount, currency, payment_status, is_refunded "
                                "FROM demo_orders WHERE owner_id=%s AND order_id=%s",
                                (owner, order_id),
                            )
                        ).fetchall()
                    else:
                        rows = await (
                            await conn.execute(
                                "SELECT order_id, amount, currency, payment_status, is_refunded "
                                "FROM demo_orders WHERE owner_id=%s "
                                "ORDER BY created_at DESC, order_id DESC LIMIT %s OFFSET %s",
                                (owner, 2, 1),
                            )
                        ).fetchall()
                print(
                    json.dumps(
                        {
                            "case": kind,
                            "sql_rows": rows,
                            "limit": 2 if kind == "list_orders" else None,
                            "offset": 1 if kind == "list_orders" else None,
                            "foreign_order_excluded": all(row[0] != foreign_id for row in rows),
                        },
                        default=str,
                    )
                )
                assert len(rows) == (1 if kind == "get_order" else 2)
                assert all(row[0] in order_ids and row[0] != foreign_id for row in rows)
                facts = out["final_facts"]
                observed = [facts["order"]] if kind == "get_order" else facts["orders"]
                assert [
                    (
                        r["order_id"],
                        r["amount"],
                        r["currency"],
                        r["payment_status"],
                        r["is_refunded"],
                    )
                    for r in observed
                ] == [(r[0], f"{r[1]:.2f}", *r[2:]) for r in rows]
                if kind == "list_orders":
                    assert (facts["limit"], facts["offset"], facts["returned_count"]) == (2, 1, 2)
    finally:
        try:
            if guard_passed:
                async with pool.connection() as conn:
                    for identifier in order_ids:
                        await conn.execute(
                            "DELETE FROM demo_orders WHERE owner_id=%s AND order_id=%s",
                            (owner, identifier),
                        )
                    await conn.execute(
                        "DELETE FROM demo_orders WHERE owner_id=%s AND order_id=%s",
                        (foreign_owner, foreign_id),
                    )
                    remaining = await (
                        await conn.execute(
                            "SELECT count(*) FROM demo_orders WHERE owner_id IN (%s,%s)",
                            (owner, foreign_owner),
                        )
                    ).fetchone()
                    print(json.dumps({"cleanup_remaining": remaining[0]}, ensure_ascii=True))
                    assert remaining == (0,)
        finally:
            await pool.close()
