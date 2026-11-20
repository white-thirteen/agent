"""Independent, explicitly opted-in V2 03 real V1 OrderGraph cost comparison.

Run only through the independently guarded isolated DB launcher after approval.
The baseline is the exact tracked HEAD OrderGraph source with shared current runtime
and infrastructure; it is not a complete checkout of the older application.
"""
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def emit(event, **data):
    print(json.dumps({"event": event, **data}, ensure_ascii=True, default=str, sort_keys=True), flush=True)


def main():
    if os.environ.get("AGENT_RUN_REAL_MODEL_TESTS") != "1":
        raise RuntimeError("Explicit AGENT_RUN_REAL_MODEL_TESTS=1 required")
    if os.environ.get("AGENT_RUN_V203_INDEPENDENT_COST") != "1":
        raise RuntimeError("Explicit AGENT_RUN_V203_INDEPENDENT_COST=1 required")
    expected_head = "1f3d73643af84fdc55f7f314d6c0db6f0c34560a"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != expected_head:
        raise RuntimeError("Unexpected HEAD; review baseline before running")
    source = subprocess.check_output(
        ["git", "show", expected_head + ":app/graph/specialists/order/builder.py"], cwd=ROOT
    )
    baseline_sha = hashlib.sha256(source).hexdigest()
    legacy = {"__name__": "v203_independent_head_order"}
    exec(compile(source, "<tracked-HEAD-order-builder>", "exec"), legacy)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(legacy["build_order_graph"], head, baseline_sha))


async def run(legacy_builder, head, baseline_sha):
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.messages.utils import count_tokens_approximately
    from psycopg.conninfo import conninfo_to_dict
    from pydantic import SecretStr

    from app.agents.types import AgentType, TaskType
    from app.core.config import Settings
    from app.domain.orders import MockOrderService, OrderRepository
    from app.graph.contracts import ExecutionContext, SpecialistInput
    from app.graph.specialists.order.builder import build_order_graph
    from app.graph.transfers import create_specialist_state
    from app.infrastructure.model import model_resources
    from app.infrastructure.postgres import open_pool, validate_test_target
    from app.runtime.context import RunExecutionContext
    from app.runtime.model_gateway import ModelCallError, ModelCallUsage
    from app.runtime.models import RunLimits, RunUsage
    from app.runtime.run_scope import RunScope
    from app.tools.executor import ToolExecutor
    from app.tools.implementations.orders import order_tools
    from app.tools.policy import ToolPolicy
    from app.tools.registry import ToolRegistry
    from app.tools.selector import ToolSelector

    raw = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not raw:
        raise RuntimeError("Explicit isolated test DSN required")
    settings = Settings().model_copy(update={
        "model_max_retries": 0,
        "context_model_window_tokens": 16384,
        "context_model_output_tokens": 512,
    })
    if not settings.model_configured:
        raise RuntimeError("Configured model required")
    url = SecretStr(raw)
    validate_test_target(url, settings.database_url)
    info = conninfo_to_dict(raw)
    if tuple(info.get(k) for k in ("host", "port", "dbname", "user")) != (
        "127.0.0.1", "56431", "agent_demo_test", "agent_test"
    ):
        raise RuntimeError("Unexpected isolated endpoint")
    token = uuid4().hex
    owner = "v203-independent-owner-" + token
    order_id = "v203-independent-order-" + token
    pool = await open_pool(Settings(_env_file=None, app_env="test", database_url=url))
    guard_ok = False
    try:
        async with pool.connection() as conn:
            guard = await (await conn.execute(
                "SELECT current_database(), current_user, current_setting('server_version_num'), "
                "shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
            )).fetchone()
            if guard != ("agent_demo_test", "agent_test", "170012", "codex-task131-0e62"):
                raise RuntimeError("Online database identity mismatch")
            guard_ok = True
            await conn.execute(
                "INSERT INTO demo_orders VALUES (%s,%s,%s,'CNY','paid',false,now())",
                (order_id, owner, Decimal("128.50")),
            )
        emit("baseline", head=head, head_order_source_sha256=baseline_sha,
             current_order_source_sha256=hashlib.sha256((ROOT / "app/graph/specialists/order/builder.py").read_bytes()).hexdigest(),
             baseline_scope="tracked HEAD order builder with shared current dependencies", model=settings.model_name,
             model_retries=0, context_window=16384, output_tokens=512, database_guard="passed")
        registry = ToolRegistry()
        for tool in order_tools(MockOrderService(OrderRepository(pool)), timeout_seconds=5, max_retries=1):
            registry.register(tool)
        registry.freeze()
        calls = []
        bindings = []
        decisions = []
        selector_calls = []
        async with model_resources(settings) as (_, gateway):
            original_call = gateway._call_recorded
            original_model = gateway._model

            class ObservedModel:
                def __getattr__(self, name):
                    return getattr(original_model, name)

                def bind_tools(self, schemas):
                    payload = json.dumps(schemas, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    bindings.append({
                        "names": [item["function"]["name"] for item in schemas],
                        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                        "schema_tokens_approx": count_tokens_approximately([SystemMessage(content=payload)]),
                        "token_method": "langchain_approximate",
                    })
                    return original_model.bind_tools(schemas)

            class ObservedPolicy(ToolPolicy):
                def evaluate(self, **kwargs):
                    decision = super().evaluate(**kwargs)
                    decisions.append({"name": kwargs["call"].name, "call_id": kwargs["call"].call_id,
                                      "decision": decision.decision.value, "code": decision.code})
                    return decision

            class ObservedSelector(ToolSelector):
                async def select(self, **kwargs):
                    selected = await super().select(**kwargs)
                    selector_calls.append(bool(selected.selector_called))
                    return selected

            gateway._model = ObservedModel()

            async def observed(*args, **kwargs):
                if len(calls) >= 4:
                    raise RuntimeError("Independent provider-call cap reached")
                entry = {"structured": kwargs["structured"], "usage": None, "status": "started"}
                calls.append(entry)
                started = time.monotonic()
                try:
                    result = await original_call(*args, **kwargs)
                    entry.update(status="completed", usage=asdict(result.usage))
                    return result
                except ModelCallError as error:
                    entry.update(status="failed", code=error.code, usage=asdict(error.usage))
                    raise
                finally:
                    entry["seconds"] = round(time.monotonic() - started, 3)
                    emit("model_call", **entry)

            gateway._call_recorded = observed
            for label, builder, current in (("head", legacy_builder, False), ("current", build_order_graph, True)):
                call_start, binding_start, decision_start, selector_start = len(calls), len(bindings), len(decisions), len(selector_calls)
                task = "v203-cost-" + label + "-" + token
                execution = ExecutionContext(user_id=owner, conversation_id="v203-cost-" + token,
                                             workflow_id=task, task_id=task, run_id=task)
                scope = RunScope(limits=RunLimits(180, 5), model_usage=ModelCallUsage(), run_usage=RunUsage())
                scope.start_active_period()
                text = f"查询订单 {order_id} 的详细信息"
                request = SpecialistInput(context=execution, task_id=task, agent_type=AgentType.ORDER,
                                          task_type=TaskType.ORDER_QUERY, task_goal=text,
                                          entities={"query_kind": "get", "order_id": order_id},
                                          messages=[HumanMessage(content=text)])
                executor = ToolExecutor(registry, ObservedPolicy())
                kwargs = {"selector": ObservedSelector(registry, gateway)} if current else {}
                graph = builder(gateway=gateway, registry=registry, executor=executor, **kwargs)
                started = time.monotonic()
                result = await graph.ainvoke(create_specialist_state(request, scope=scope),
                    context=RunExecutionContext(execution, "thread-" + task, frozenset({"orders:read"}), scope))
                elapsed = round(time.monotonic() - started, 3)
                async with pool.connection() as conn:
                    row = await (await conn.execute(
                        "SELECT order_id,amount,currency,payment_status,is_refunded FROM demo_orders "
                        "WHERE owner_id=%s AND order_id=%s", (owner, order_id)
                    )).fetchone()
                facts = result["result"].facts
                order = facts.get("order", {})
                observed_order = (order.get("order_id"), str(order.get("amount")), order.get("currency"),
                                  order.get("payment_status"), order.get("is_refunded"))
                sql_order = (row[0], f"{row[1]:.2f}", *row[2:]) if row else None
                report = {"case": label, "result_status": str(result["result"].status),
                          "model_calls": calls[call_start:], "bindings": bindings[binding_start:],
                          "policy_decisions": decisions[decision_start:],
                          "selector_model_calls": sum(selector_calls[selector_start:]),
                          "model_attempts": scope.model_usage().model_attempts,
                          "tool_calls": scope.run_usage().tool_calls, "sql_fact_match": observed_order == sql_order,
                          "elapsed_seconds": elapsed}
                emit("order_run", **report)
                assert result["result"].status == "completed" and observed_order == sql_order
                assert scope.model_usage().model_attempts == 2 and scope.run_usage().tool_calls == 1
                assert len(calls[call_start:]) == 2 and not any(selector_calls[selector_start:])
                assert all(item["names"] == ["get_order"] for item in bindings[binding_start:])
                assert len(bindings[binding_start:]) == 2
    finally:
        try:
            if guard_ok:
                async with pool.connection() as conn:
                    await conn.execute("DELETE FROM demo_orders WHERE owner_id=%s AND order_id=%s", (owner, order_id))
                    row = await (await conn.execute("SELECT count(*) FROM demo_orders WHERE owner_id=%s AND order_id=%s", (owner, order_id))).fetchone()
                    emit("cleanup", remaining=row[0])
                    if row[0] != 0:
                        raise RuntimeError("Precise cleanup failed")
        finally:
            await pool.close()


if __name__ == "__main__":
    main()
