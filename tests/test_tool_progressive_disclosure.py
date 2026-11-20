"""V2 03 ToolRegistry progressive disclosure tests (unit, budget, reuse, and opt-in real chain)."""

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agents.types import AgentType, TaskType
from app.domain.orders import MockOrderService, OrderRecord
from app.graph.contracts import ExecutionContext, SpecialistInput
from app.graph.state import SpecialistState, create_turn_state
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import (
    ModelCallContext,
    ModelCallLimits,
    ModelCallUsage,
    ModelGateway,
)
from app.runtime.models import RunLimits, RunUsage, TaskStatus
from app.runtime.run_scope import RunScope
from app.tools.discovery import (
    PRODUCTION_PURPOSES,
    PurposeSpec,
    filter_discoverable_briefs,
    get_production_purpose,
)
from app.tools.executor import ToolExecutor
from app.tools.implementations.knowledge import knowledge_tools
from app.tools.implementations.memory import read_preferences_tool, write_preferences_tool
from app.tools.implementations.orders import order_tools
from app.tools.implementations.refunds import refund_node_tools, refund_order_tool
from app.tools.messages import execute_tool_calls, parse_tool_calls, to_tool_message
from app.tools.models import (
    ToolBrief,
    ToolExecutionContext,
)
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from app.tools.selector import SelectorOutput, ToolSelector


class _DummyOrderRepo:
    async def get_owned(self, *, owner_id: str, order_id: str):
        return OrderRecord(
            order_id=order_id,
            owner_id=owner_id,
            amount=Decimal("128.50"),
            currency="CNY",
            payment_status="paid",
            is_refunded=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    async def list_owned(self, *, owner_id: str, limit: int, offset: int):
        return [
            OrderRecord(
                order_id="demo-order-a-001",
                owner_id=owner_id,
                amount=Decimal("128.50"),
                currency="CNY",
                payment_status="paid",
                is_refunded=False,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ][:limit]


class _DummyRetriever:
    profile = "qwen3-1024"
    retrieval_profile = "hybrid-v1"

    async def search(self, query: str, *, top_k: int = 3):
        return []

    async def validate_sources(self, evidence):
        return {"valid": True, "evidence": evidence}


class _DummyService:
    pass


def _build_full_registry() -> ToolRegistry:
    registry = ToolRegistry()
    order_svc = MockOrderService(_DummyOrderRepo())
    for d in order_tools(order_svc, timeout_seconds=5, max_retries=1):
        registry.register(d)
    for d in refund_node_tools(_DummyService(), _DummyService(), timeout_seconds=5):
        registry.register(d)
    registry.register(refund_order_tool(_DummyService(), timeout_seconds=5))
    for d in knowledge_tools(_DummyRetriever(), mode="dense", retrieval_timeout=5):
        registry.register(d)
    registry.register(read_preferences_tool(_DummyService(), enabled=True))
    registry.register(write_preferences_tool(_DummyService(), enabled=True))
    registry.freeze()
    return registry


def _execution(task_id="task-1", run_id="run-1") -> ExecutionContext:
    return ExecutionContext(
        user_id="dev-user",
        conversation_id="conv-1",
        workflow_id=task_id,
        task_id=task_id,
        run_id=run_id,
    )


def _scope(*, max_tool_calls=12, active_timeout_seconds=120.0, model_attempts=0) -> RunScope:
    scope = RunScope(
        limits=RunLimits(
            active_timeout_seconds=active_timeout_seconds,
            max_tool_calls=max_tool_calls,
        ),
        model_usage=ModelCallUsage(model_attempts=model_attempts),
        run_usage=RunUsage(),
    )
    scope.start_active_period()
    return scope


class ControlledSelectorAndBusinessModel:
    """Fake ChatModel supporting both with_structured_output and bind_tools."""

    def __init__(self, responses):
        self._responses = iter(responses)
        self.structured_calls = []
        self.tool_bindings = []
        self.invocations = []

    def with_structured_output(self, schema, **kwargs):
        model = self

        class _StructuredRunnable:
            async def ainvoke(self, messages):
                model.structured_calls.append((schema, messages))
                nxt = next(model._responses)
                if isinstance(nxt, BaseException):
                    raise nxt
                return nxt

        return _StructuredRunnable()

    def bind_tools(self, tools):
        model = self
        model.tool_bindings.append(tuple(tools))

        class _ToolRunnable:
            def bind(self, **kwargs):
                return self

            async def ainvoke(self, messages):
                model.invocations.append((tuple(tools), messages))
                nxt = next(model._responses)
                if isinstance(nxt, BaseException):
                    raise nxt
                return nxt

        return _ToolRunnable()

    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        self.invocations.append(((), messages))
        nxt = next(self._responses)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


def _ai_msg(content="done", *, tool_calls=()):
    return AIMessage(
        content=content,
        tool_calls=list(tool_calls),
        usage_metadata={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
    )


def _structured_resp(output: SelectorOutput):
    return {"raw": _ai_msg("selected"), "parsed": output, "parsing_error": None}


# --- 3.1.1 Brief Directory & Version Contract ---


def test_brief_directory_omits_schemas_and_avoids_full_list():
    registry = _build_full_registry()
    with patch.object(registry, "list", side_effect=AssertionError("list() must not be called")):
        briefs = registry.list_brief(
            agent_type=AgentType.ORDER,
            permission_scopes=frozenset({"orders:read"}),
        )
    assert briefs == (
        ToolBrief(name="get_order", version="1", description="查询当前演示用户本人的一个模拟订单"),
        ToolBrief(
            name="list_orders", version="1", description="分页查询当前演示用户本人的模拟订单列表"
        ),
    )
    for brief in briefs:
        assert not hasattr(brief, "model_schema")
        assert not hasattr(brief, "parameters")
        assert not hasattr(brief, "handler")
    assert len(registry.catalog_version) == 16
    assert registry.schema_digest("get_order") is not None


def test_resolve_binding_validates_scope_version_and_catalog():
    registry = _build_full_registry()
    binding = registry.resolve_binding(
        selected=[("get_order", "1")],
        agent_type=AgentType.ORDER,
        permission_scopes=frozenset({"orders:read"}),
        allowed_names=frozenset({"get_order"}),
        expected_catalog_version=registry.catalog_version,
    )
    assert binding.allowed_tools == frozenset({("get_order", "1")})
    assert len(binding.schemas) == 1
    assert binding.schemas[0]["function"]["name"] == "get_order"

    with pytest.raises(ValueError, match="catalog version"):
        registry.resolve_binding(
            selected=[("get_order", "1")],
            agent_type=AgentType.ORDER,
            permission_scopes=frozenset({"orders:read"}),
            expected_catalog_version="wrong-version",
        )
    with pytest.raises(ValueError, match="version mismatch"):
        registry.resolve_binding(
            selected=[("get_order", "999")],
            agent_type=AgentType.ORDER,
            permission_scopes=frozenset({"orders:read"}),
        )


# --- 3.1.2 Agent, Permission & Purpose Filtering ---


def test_internal_and_preference_tools_are_never_model_discoverable():
    registry = _build_full_registry()
    assert set(PRODUCTION_PURPOSES) == {
        "order.get",
        "order.list",
        "knowledge.search",
        "refund.plan",
    }

    all_scopes = frozenset(
        {"orders:read", "knowledge:read", "refunds:request", "memory:read", "memory:write"}
    )
    # Refund planning must NOT discover get_order or internal refund node tools.
    refund_briefs = filter_discoverable_briefs(
        registry,
        purpose_spec=get_production_purpose("refund.plan"),
        permission_scopes=all_scopes,
        agent_type=AgentType.REFUND,
        task_type=TaskType.REFUND_APPLY,
    )
    assert [b.name for b in refund_briefs] == ["refund_order"]

    # Knowledge search must NOT discover validate_knowledge_sources or preference tools.
    knowledge_briefs = filter_discoverable_briefs(
        registry,
        purpose_spec=get_production_purpose("knowledge.search"),
        permission_scopes=all_scopes,
        agent_type=AgentType.KNOWLEDGE,
        task_type=TaskType.KNOWLEDGE_QA,
    )
    assert [b.name for b in knowledge_briefs] == ["search_knowledge"]

    # Even without allowed_names filter, model_discoverable=False hides internal tools.
    for role in (AgentType.ORDER, AgentType.KNOWLEDGE, AgentType.REFUND):
        discoverable = {
            b.name
            for b in registry.list_brief(
                agent_type=role, permission_scopes=all_scopes, discoverable_only=True
            )
        }
        assert discoverable.isdisjoint(
            {
                "validate_knowledge_sources",
                "check_refund_eligibility",
                "prepare_refund_application",
                "register_refund_approval",
                "close_refund_application",
                "read_preferences",
                "write_preferences",
            }
        )


# --- 3.2.1 Structured ToolSelector & Budget Governance ---


async def test_short_circuits_make_zero_selector_calls():
    registry = _build_full_registry()
    model = ControlledSelectorAndBusinessModel([])
    gateway = ModelGateway(
        model, ModelCallLimits(max_attempts=8, timeout_seconds=10, max_retries=1)
    )
    selector = ToolSelector(registry, gateway)

    # Deterministic target
    out_det = await selector.select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=get_production_purpose("order.get"),
        permission_scopes=frozenset({"orders:read"}),
        scope=_scope(),
        need_text="查订单 demo-order-a-001",
        deterministic_target="get_order",
    )
    assert out_det.status == "selected" and out_det.method == "deterministic"
    assert not out_det.selector_called

    # Singleton
    out_single = await selector.select(
        execution=_execution(),
        agent_type=AgentType.KNOWLEDGE,
        task_type=TaskType.KNOWLEDGE_QA,
        purpose_spec=get_production_purpose("knowledge.search"),
        permission_scopes=frozenset({"knowledge:read"}),
        scope=_scope(),
        need_text="退款政策是什么",
    )
    assert out_single.status == "selected" and out_single.method == "singleton"
    assert not out_single.selector_called

    # Zero candidates (missing scope)
    out_zero = await selector.select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=get_production_purpose("order.get"),
        permission_scopes=frozenset(),
        scope=_scope(),
        need_text="查订单",
        deterministic_target="get_order",
    )
    assert out_zero.status == "rejected" and out_zero.error_code == "tool_not_allowed"
    assert model.structured_calls == []


async def test_selector_budget_precheck_and_retry_reservation():
    registry = _build_full_registry()
    test_purpose = PurposeSpec(
        purpose="test.order.multi",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
        max_selected_tools=1,
    )

    # R=1, B=1 -> precheck fails with 0 Selector calls
    model_r1 = ControlledSelectorAndBusinessModel([])
    gw_r1 = ModelGateway(
        model_r1, ModelCallLimits(max_attempts=2, timeout_seconds=10, max_retries=1)
    )
    sel_r1 = ToolSelector(registry, gw_r1, max_selector_attempts=2)
    scope_r1 = _scope(model_attempts=1)
    out_r1 = await sel_r1.select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope_r1,
        need_text="查询我的订单列表",
        business_calls_reserved=1,
    )
    assert out_r1.status == "failed" and out_r1.error_code == "model_limit_exceeded"
    assert not out_r1.selector_called
    assert scope_r1.model_usage().model_attempts == 1
    assert model_r1.structured_calls == []

    # R=2, B=1 -> S_granted=1; even on retryable TimeoutError, Gateway must NOT retry!
    model_r2 = ControlledSelectorAndBusinessModel(
        [
            TimeoutError("timeout"),
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["list_orders"])),
        ]
    )
    gw_r2 = ModelGateway(
        model_r2, ModelCallLimits(max_attempts=3, timeout_seconds=10, max_retries=1)
    )
    sel_r2 = ToolSelector(registry, gw_r2, max_selector_attempts=2)
    scope_r2 = _scope(model_attempts=1)
    out_r2 = await sel_r2.select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope_r2,
        need_text="查询我的订单列表",
        business_calls_reserved=1,
    )
    assert out_r2.status == "failed"
    assert len(model_r2.structured_calls) == 1  # No retry!
    assert (
        scope_r2.model_usage().model_attempts == 2
    )  # Still leaves 1 attempt (max=3) for business!

    # B=2, R=2 -> precheck fails with 0 Selector calls
    scope_b2 = _scope(model_attempts=1)
    out_b2 = await sel_r2.select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope_b2,
        need_text="查询我的订单列表",
        business_calls_reserved=2,
    )
    assert out_b2.status == "failed" and out_b2.error_code == "model_limit_exceeded"
    assert not out_b2.selector_called

    # Insufficient remaining active seconds for business reserve -> 0 Selector calls
    scope_time = _scope(active_timeout_seconds=5.0)
    out_time = await sel_r2.select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope_time,
        need_text="查询我的订单列表",
        business_calls_reserved=1,
        business_timeout_per_call=10.0,
    )
    assert out_time.status == "failed" and out_time.error_code == "model_limit_exceeded"
    assert not out_time.selector_called


async def test_selector_rejects_invalid_and_excess_outputs_without_filtering():
    registry = _build_full_registry()
    test_purpose = PurposeSpec(
        purpose="test.order.multi",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
        max_selected_tools=1,
    )
    # 1) Unknown tool name
    model1 = ControlledSelectorAndBusinessModel(
        [_structured_resp(SelectorOutput(action="use_tools", tool_names=["refund_order"]))]
    )
    gw1 = ModelGateway(model1, ModelCallLimits(max_attempts=8, timeout_seconds=10, max_retries=0))
    out1 = await ToolSelector(registry, gw1).select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=_scope(),
        need_text="查订单",
    )
    assert out1.status == "failed" and out1.error_code == "selector_output_invalid"

    # 2) Exceeds max_selected_tools=1
    model2 = ControlledSelectorAndBusinessModel(
        [
            _structured_resp(
                SelectorOutput(action="use_tools", tool_names=["get_order", "list_orders"])
            )
        ]
    )
    gw2 = ModelGateway(model2, ModelCallLimits(max_attempts=8, timeout_seconds=10, max_retries=0))
    out2 = await ToolSelector(registry, gw2).select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=_scope(),
        need_text="查订单",
    )
    assert out2.status == "failed" and out2.error_code == "selector_output_invalid"


async def test_selector_directory_overflow_fails_without_truncation_or_compaction():
    registry = _build_full_registry()
    test_purpose = PurposeSpec(
        purpose="test.order.multi",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
        max_selected_tools=1,
    )
    model = ControlledSelectorAndBusinessModel([])
    # Tiny context window so candidate directory does not fit
    gw = ModelGateway(
        model,
        ModelCallLimits(max_attempts=8, timeout_seconds=10, max_retries=0),
        context_window=60,
        output_reserve=20,
    )
    out = await ToolSelector(registry, gw).select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=_scope(),
        need_text="请查询我的订单信息 " * 20,
    )
    assert out.status == "failed" and out.error_code == "context_budget_exceeded"
    assert model.structured_calls == []


# --- 3.3.1 Loop Reuse, Bounded Rediscovery & Recovery ---


async def test_reuse_bounded_rediscovery_clarification_persistence_and_pending_lock():
    registry = _build_full_registry()
    test_purpose = PurposeSpec(
        purpose="test.order.multi",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
        max_selected_tools=1,
    )
    model = ControlledSelectorAndBusinessModel(
        [
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["get_order"])),
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["list_orders"])),
        ]
    )
    gw = ModelGateway(model, ModelCallLimits(max_attempts=8, timeout_seconds=10, max_retries=0))
    selector = ToolSelector(registry, gw, max_rediscoveries=1)
    scope = _scope()

    # Initial selection
    first = await selector.select(
        execution=_execution(run_id="run-1"),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
        need_text="查订单 demo-order-a-001",
    )
    assert first.status == "selected" and first.selector_called
    assert first.record.generation == 1 and first.record.rediscovery_count == 0

    # Loop reuse (same task, need, scope) -> 0 new Selector calls
    reused = await selector.select(
        execution=_execution(run_id="run-1"),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
        need_text="查订单 demo-order-a-001",
        existing_record=first.record.model_dump(mode="json"),
    )
    assert reused.status == "selected" and reused.reused and not reused.selector_called

    # Pending call / waiting approval -> forbids rediscovery even if need_text changed
    locked = await selector.select(
        execution=_execution(run_id="run-1"),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
        need_text="改成查列表",
        existing_record=first.record.model_dump(mode="json"),
        has_pending_calls=True,
    )
    assert locked.status == "selected" and locked.reused
    assert locked.binding.tool_names == frozenset({"get_order"})

    # Safe boundary change (e.g. clarification continue with new run_id) -> 1st rediscovery allowed
    turn = create_turn_state(
        _execution(run_id="run-2"),
        "其实是查我的订单列表",
        task_mode="continue",
        saved_task={
            "task_status": TaskStatus.NEEDS_INPUT,
            "pending_task": {
                "user_id": "dev-user",
                "conversation_id": "conv-1",
                "workflow_id": "task-1",
                "task_id": "task-1",
                "task_type": TaskType.ORDER_QUERY,
                "task_goal": "查订单",
                "entities": {},
                "missing_fields": ["query_kind"],
                "clarification_question": "请问查单个还是列表？",
                "task_message_ids": ["user:run-1"],
            },
            "task_message_ids": ["user:run-1"],
            "model_call_usage": {"model_attempts": 1},
            "run_usage": {"tool_calls": 0, "active_elapsed_ms": 10},
            "tool_selection_record": first.record.model_dump(mode="json"),
        },
    )
    assert turn["tool_selection_record"]["rediscovery_count"] == 0

    rediscovered = await selector.select(
        execution=_execution(run_id="run-2"),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
        need_text="其实是查我的订单列表",
        existing_record=turn["tool_selection_record"],
    )
    assert rediscovered.status == "selected" and rediscovered.selector_called
    assert rediscovered.record.generation == 2 and rediscovered.record.rediscovery_count == 1
    assert rediscovered.binding.tool_names == frozenset({"list_orders"})

    # Second rediscovery in same Task -> rejected
    exhausted = await selector.select(
        execution=_execution(run_id="run-3"),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=test_purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
        need_text="又改需求",
        existing_record=rediscovered.record.model_dump(mode="json"),
    )
    assert exhausted.status == "failed" and exhausted.error_code == "rediscovery_limit_exceeded"
    assert len(model.structured_calls) == 2


# --- 3.3.2 Controlled Multi-Candidate Full-Chain Helper & Tests ---


def _build_controlled_multi_candidate_order_node(
    *, gateway, registry, executor, selector, observer=None
):
    """Test-only multi-candidate node reusing production Selector/Registry/Gateway/Policy."""
    test_purpose = PurposeSpec(
        purpose="test.order.multi_candidate",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
        max_selected_tools=1,
        require_tool=True,
    )

    class _MultiOrderState(SpecialistState, total=False):
        selection_method: str | None
        candidate_count: int
        tool_calls_made: list[dict]
        tool_results: list[dict]
        final_facts: dict | None
        outcome: str | None
        error_code: str | None

    async def multi_order_node(state: _MultiOrderState, runtime: Runtime[RunExecutionContext]):
        exec_ctx = runtime.context.context
        scope = runtime.context.scope
        need_text = state["request"].task_goal
        candidates = filter_discoverable_briefs(
            registry,
            purpose_spec=test_purpose,
            permission_scopes=runtime.context.permission_scopes,
            agent_type=AgentType.ORDER,
            task_type=TaskType.ORDER_QUERY,
        )
        # One selected tool is necessary; reserve its configured attempts and timeout.
        processing = max(
            (
                registry.get(brief.name).metadata.timeout_seconds
                * (registry.get(brief.name).metadata.max_retries + 1)
                for brief in candidates
            ),
            default=0,
        )
        outcome = await selector.select(
            execution=exec_ctx,
            agent_type=AgentType.ORDER,
            task_type=TaskType.ORDER_QUERY,
            purpose_spec=test_purpose,
            permission_scopes=runtime.context.permission_scopes,
            scope=scope,
            need_text=need_text,
            existing_record=state.get("tool_selection_record"),
            business_calls_reserved=1,
            required_processing_seconds=processing,
        )
        if outcome.status != "selected" or outcome.binding is None or outcome.record is None:
            return {"outcome": outcome.status, "error_code": outcome.error_code}

        if observer is not None:
            briefs = filter_discoverable_briefs(
                registry,
                purpose_spec=test_purpose,
                permission_scopes=runtime.context.permission_scopes,
                agent_type=AgentType.ORDER,
                task_type=TaskType.ORDER_QUERY,
            )
            observer.append(
                {
                    "candidates": [brief.name for brief in briefs],
                    "allowed_tools": sorted(outcome.binding.allowed_tools),
                    "schema_digests": outcome.binding.schema_digests,
                }
            )

        # Business model receives ONLY the selected tool's full schema
        biz_result = await gateway.invoke(
            [
                SystemMessage(
                    content=(
                        "You are an order assistant. Call the provided tool to fulfill "
                        "the request. For list_orders, use limit=2, offset=0 unless specified."
                    )
                ),
                *state["messages"],
            ],
            context=asdict_model_ctx(exec_ctx, scope),
            model_usage=scope.model_usage(),
            tools=list(outcome.binding.schemas),
        )
        scope.adopt_model_usage(biz_result.model_usage)
        calls = parse_tool_calls(biz_result.message, used_ids=set(), max_calls=1)
        if not calls or any(c.name not in outcome.binding.tool_names for c in calls):
            return {"outcome": "failed", "error_code": "tool_not_allowed"}

        tool_ctx = ToolExecutionContext(
            exec_ctx,
            AgentType.ORDER,
            TaskType.ORDER_QUERY,
            None,
            runtime.context.permission_scopes,
            "model",
            outcome.binding.allowed_tools,
            {name: state["request"].entities for name in outcome.binding.tool_names},
            scope.limits,
            scope,
        )
        results = await execute_tool_calls(calls, executor=executor, context=tool_ctx)
        tool_msgs = [to_tool_message(r, task_id=exec_ctx.task_id) for r in results]
        return {
            "messages": [biz_result.message, *tool_msgs],
            "selected_tools": outcome.record.selected_tools,
            "tool_selection_record": outcome.record.model_dump(mode="json"),
            "selection_method": outcome.method,
            "tool_results": [asdict(r) for r in results],
            "final_facts": results[0].data if results[0].status == "success" else None,
            "outcome": "completed" if results[0].status == "success" else "failed",
            "error_code": None if results[0].status == "success" else results[0].code,
        }

    def asdict_model_ctx(exec_ctx, scope):
        from app.runtime.model_gateway import ModelCallContext

        return ModelCallContext(
            run_id=exec_ctx.run_id,
            task_id=exec_ctx.task_id,
            agent_type=AgentType.ORDER,
            on_attempt=scope.adopt_model_usage,
            current_usage=scope.model_usage,
        )

    graph = StateGraph(_MultiOrderState, context_schema=RunExecutionContext)
    graph.add_node("multi_order", multi_order_node)
    graph.add_edge(START, "multi_order")
    graph.add_edge("multi_order", END)
    return graph.compile()


async def test_controlled_multi_candidate_full_chain_offline():
    registry = _build_full_registry()
    executor = ToolExecutor(registry, ToolPolicy())
    model = ControlledSelectorAndBusinessModel(
        [
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["get_order"])),
            _ai_msg(
                "",
                tool_calls=[
                    {
                        "id": "call-get-1",
                        "name": "get_order",
                        "args": {"order_id": "demo-order-a-001"},
                    }
                ],
            ),
        ]
    )
    gateway = ModelGateway(
        model, ModelCallLimits(max_attempts=8, timeout_seconds=10, max_retries=0)
    )
    selector = ToolSelector(registry, gateway)
    graph = _build_controlled_multi_candidate_order_node(
        gateway=gateway, registry=registry, executor=executor, selector=selector
    )
    exec_ctx = _execution()
    scope = _scope()
    req = SpecialistInput(
        context=exec_ctx,
        task_id=exec_ctx.task_id,
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        task_goal="请帮我查询订单 demo-order-a-001 的详情",
        entities={"order_id": "demo-order-a-001"},
        messages=[HumanMessage(content="请帮我查询订单 demo-order-a-001 的详情", id="u-1")],
    )
    out = await graph.ainvoke(
        {
            "request": req,
            "messages": list(req.messages),
            "selected_tools": [],
            "tool_selection_record": None,
        },
        context=RunExecutionContext(
            context=exec_ctx,
            thread_id="thread-1",
            permission_scopes=frozenset({"orders:read"}),
            scope=scope,
        ),
    )
    assert out["outcome"] == "completed"
    assert out["selection_method"] == "model"
    assert out["selected_tools"] == [("get_order", "1")]
    assert len(model.tool_bindings) == 1
    assert [t["function"]["name"] for t in model.tool_bindings[0]] == ["get_order"]
    assert out["final_facts"]["order"]["order_id"] == "demo-order-a-001"
    assert scope.run_usage().tool_calls == 1
    assert scope.model_usage().model_attempts == 2


async def test_pending_without_selection_never_calls_selector():
    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.order.multi",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    model = ControlledSelectorAndBusinessModel([])
    selector = ToolSelector(registry, ModelGateway(model, ModelCallLimits(8, 10, 0)))
    for flags in ({"has_pending_calls": True}, {"waiting_approval_or_unknown": True}):
        result = await selector.select(
            execution=_execution(),
            agent_type=AgentType.ORDER,
            task_type=TaskType.ORDER_QUERY,
            purpose_spec=purpose,
            permission_scopes=frozenset({"orders:read"}),
            scope=_scope(),
            need_text="order",
            **flags,
        )
        assert result.error_code == "tool_selection_missing"
    assert not model.structured_calls


async def test_failed_rediscovery_retains_consumed_count():
    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.order.multi",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    model = ControlledSelectorAndBusinessModel(
        [
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["get_order"])),
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["refund_order"])),
        ]
    )
    selector = ToolSelector(registry, ModelGateway(model, ModelCallLimits(8, 10, 0)))
    scope = _scope()
    args = dict(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
    )
    first = await selector.select(**args, need_text="first")
    failed = await selector.select(**args, need_text="second", existing_record=first.record)
    assert failed.error_code == "selector_output_invalid"
    assert failed.record.rediscovery_count == 1
    retried = await selector.select(**args, need_text="second", existing_record=failed.record)
    assert retried.error_code == "rediscovery_limit_exceeded"
    assert len(model.structured_calls) == 2


@pytest.mark.parametrize(
    "maximum,attempts,reserved,seconds", [(1, 0, 0, 120), (2, 0, 1, 120), (8, 0, 1, 19)]
)
async def test_run_compaction_preserves_business_budget_before_source(
    maximum, attempts, reserved, seconds
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.runtime.agent_runtime import AgentRuntime
    from app.runtime.model_gateway import ModelCallContext, ModelCallError

    scope = _scope(active_timeout_seconds=seconds, model_attempts=attempts)
    maintenance = SimpleNamespace(
        gateway=ModelGateway(None, ModelCallLimits(maximum, 10, 0)), _source=AsyncMock()
    )
    fake_runtime = SimpleNamespace(_maintenance=maintenance, _stopping=False)
    compact = AgentRuntime._run_compactor(fake_runtime, _execution(), None, scope)
    with pytest.raises(ModelCallError) as exc:
        await compact(ModelCallContext("run", "task", AgentType.ORDER, reserved_attempts=reserved))
    assert exc.value.code == "model_limit_exceeded"
    assert scope.model_usage().model_attempts == attempts
    maintenance._source.assert_not_awaited()


async def test_selection_reservation_only_confirms_matching_committed_result():
    from types import SimpleNamespace

    from langgraph.checkpoint.memory import InMemorySaver

    from app.runtime.selection_reservation import SelectionReservation

    owner = {"user_id": "user", "conversation_id": "conversation", "task_id": "task"}
    saver = InMemorySaver()
    reservation = SelectionReservation(
        saver, thread_id="thread", owner=owner, run_id="run", source_checkpoint_id="source"
    )
    await reservation.begin(1, 1)
    await reservation.reserve_attempt(2)

    class Record:
        def model_dump(self, **kwargs):
            return {"rediscovery_count": 1, "selected": [{"name": "get_order"}]}

    await reservation.record_outcome(Record(), "selected")
    state = {
        **owner,
        "run_id": "run",
        "task_status": "completed",
        "model_call_usage": {"model_attempts": 2},
        "tool_selection_record": Record().model_dump(),
    }
    config = {"configurable": {"thread_id": "thread", "checkpoint_id": "committed"}}
    for invalid in (
        SimpleNamespace(values=state, config=config, next=("still_running",)),
        SimpleNamespace(values={**state, "run_id": "other"}, config=config, next=()),
        SimpleNamespace(values={**state, "tool_selection_record": None}, config=config, next=()),
    ):
        with pytest.raises(ValueError, match="not committed"):
            await reservation.confirm(invalid)
    snapshot = SimpleNamespace(values=state, config=config, next=())
    restarted = SelectionReservation(
        saver, thread_id="thread", owner=owner, run_id="next", source_checkpoint_id="committed"
    )
    await restarted.load(snapshot)
    assert restarted.value["inflight"] is False and restarted.value["attempts"] == 2
    with pytest.raises(ValueError, match="cannot decrease"):
        await restarted.begin(1, 0)
    wrong_source = SelectionReservation(
        saver, thread_id="thread", owner=owner, run_id="next", source_checkpoint_id="old"
    )
    with pytest.raises(ValueError, match="checkpoint mismatch"):
        await wrong_source.load(snapshot)


async def test_single_optional_candidate_short_circuits_without_model():
    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.order.single",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order"}),
        require_tool=False,
    )
    model = ControlledSelectorAndBusinessModel([])
    result = await ToolSelector(registry, ModelGateway(model, ModelCallLimits(8, 10, 0))).select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=_scope(),
        need_text="query an order",
    )
    assert result.status == "selected" and result.method == "singleton"
    assert result.record.selected_tools == [("get_order", "1")]
    assert not model.structured_calls


async def test_compaction_reserves_current_and_following_business_calls():
    from dataclasses import replace
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.runtime.agent_runtime import AgentRuntime
    from app.runtime.model_gateway import ModelCallContext

    class Model:
        def __init__(self):
            self.calls = 0

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            self.calls += 1
            return AIMessage(content="controlled")

    model = Model()
    gateway = ModelGateway(model, ModelCallLimits(3, 10, 0))
    scope = _scope()
    source = {
        "checkpoint": "cp",
        "parts": [],
        "archive_ref": "archive",
        "base": None,
        "parent": None,
        "refs": ["archive"],
        "selected": [],
    }

    async def summarize(*args, run_context, run_scope, **kwargs):
        result = await gateway.invoke(
            [HumanMessage(content="summary")],
            context=replace(run_context, on_attempt=run_scope.adopt_model_usage),
            model_usage=run_scope.model_usage(),
        )
        return SimpleNamespace(text=result.message.content, summary_id="summary"), None

    manager = SimpleNamespace(
        publish=AsyncMock(return_value=SimpleNamespace(archive_ref="archive")), compact=summarize
    )
    settings = SimpleNamespace(
        context_archive_segment_messages=10,
        model_name="controlled",
        context_archive_read_bytes=1000,
        context_archive_read_tokens=1000,
        context_summary_output_tokens=64,
    )
    fake_runtime = SimpleNamespace(
        _maintenance=SimpleNamespace(gateway=gateway, _source=AsyncMock(return_value=source)),
        _stopping=False,
        _context_manager=manager,
        _context_settings=settings,
    )
    compact = AgentRuntime._run_compactor(fake_runtime, _execution(), None, scope)
    context = ModelCallContext("run", "task", AgentType.ORDER, reserved_attempts=1)
    await compact(context)
    first = await gateway.invoke(
        [HumanMessage(content="first business")], context=context, model_usage=scope.model_usage()
    )
    scope.adopt_model_usage(first.model_usage)
    second = await gateway.invoke(
        [HumanMessage(content="second business")],
        context=replace(context, reserved_attempts=0),
        model_usage=scope.model_usage(),
    )
    assert second.model_usage.model_attempts == 3 and model.calls == 3


async def test_order_selection_scope_uses_validated_target_not_context_history():
    from app.graph.specialists.order.builder import build_order_graph
    from app.graph.transfers import create_specialist_state

    registry = _build_full_registry()
    model = ControlledSelectorAndBusinessModel([_ai_msg("no facts")] * 3)
    gateway = ModelGateway(model, ModelCallLimits(8, 10, 0))
    graph = build_order_graph(
        gateway=gateway, registry=registry, executor=ToolExecutor(registry, ToolPolicy())
    )
    execution = _execution()

    async def run(order_id, record, history):
        scope = _scope()
        request = SpecialistInput(
            context=execution,
            task_id=execution.task_id,
            agent_type=AgentType.ORDER,
            task_type=TaskType.ORDER_QUERY,
            task_goal="query my order",
            entities={"query_kind": "get", "order_id": order_id},
            messages=[HumanMessage(content="query my order")],
        )
        state = create_specialist_state(request, scope=scope)
        state["tool_selection_record"] = record
        state["context_history"] = history
        return await graph.ainvoke(
            state,
            context=RunExecutionContext(execution, "thread", frozenset({"orders:read"}), scope),
        )

    first = await run("order-1", None, [])
    record = first["tool_selection_record"]
    same = await run("order-1", record, [[HumanMessage(content="changed historical summary")]])
    assert same["tool_selection_record"]["generation"] == record["generation"]
    changed = await run("order-2", record, [])
    assert changed["tool_selection_record"]["generation"] == 2
    assert changed["tool_selection_record"]["rediscovery_count"] == 1


async def test_failed_rediscovery_timeout_keeps_unknown_usage_and_count():
    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.order.multi",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    model = ControlledSelectorAndBusinessModel(
        [
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["get_order"])),
            TimeoutError(),
        ]
    )
    selector = ToolSelector(registry, ModelGateway(model, ModelCallLimits(8, 10, 0)))
    scope = _scope()
    args = dict(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
    )
    first = await selector.select(**args, need_text="first")
    failed = await selector.select(**args, need_text="second", existing_record=first.record)
    assert failed.error_code == "model_timeout" and failed.record.rediscovery_count == 1
    assert scope.model_usage().model_attempts == 2
    receipt = scope.selector_receipts[-1]["usage"]
    assert receipt["status"] == "unknown" and receipt["total_tokens"] is None
    retry = await selector.select(**args, need_text="second", existing_record=failed.record)
    assert retry.error_code == "rediscovery_limit_exceeded" and len(model.structured_calls) == 2


async def test_selection_reservation_storage_failure_never_invokes_provider():
    from app.runtime.selection_reservation import SelectionReservation

    class BrokenSaver:
        async def aput(self, *args, **kwargs):
            raise RuntimeError("storage unavailable")

    registry = _build_full_registry()
    model = ControlledSelectorAndBusinessModel([])
    selector = ToolSelector(registry, ModelGateway(model, ModelCallLimits(8, 10, 0)))
    scope = _scope()
    scope.selection_reservation = SelectionReservation(
        BrokenSaver(),
        thread_id="thread",
        owner={"user_id": "dev-user", "conversation_id": "conv-1", "task_id": "task-1"},
        run_id="run-1",
        source_checkpoint_id=None,
    )
    purpose = PurposeSpec(
        purpose="test.multi",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await selector.select(
            execution=_execution(),
            agent_type=AgentType.ORDER,
            task_type=TaskType.ORDER_QUERY,
            purpose_spec=purpose,
            permission_scopes=frozenset({"orders:read"}),
            scope=scope,
            need_text="query",
        )
    assert not model.structured_calls and scope.model_usage().model_attempts == 0


@pytest.mark.parametrize("slow_stage", ["begin", "attempt", "retry"])
async def test_selector_rechecks_scope_after_each_persistent_write(slow_stage):
    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.clock",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    responses = [
        TimeoutError("controlled"),
        _structured_resp(SelectorOutput(action="use_tools", tool_names=["get_order"])),
    ]
    model = ControlledSelectorAndBusinessModel(responses)
    selector = ToolSelector(
        registry, ModelGateway(model, ModelCallLimits(8, 10, 1)), max_selector_attempts=2
    )
    scope = _scope()
    remaining = [30.0]
    writes = [0]
    scope.remaining_active_seconds = lambda: remaining[0]

    async def begin(count):
        if slow_stage == "begin":
            remaining[0] = 24.0

    async def reserve(usage):
        writes[0] += 1
        if slow_stage == "attempt" or slow_stage == "retry" and writes[0] == 2:
            remaining[0] = 24.0

    scope.begin_selection = begin
    scope.reserve_model_attempt = reserve
    result = await selector.select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
        need_text="order",
        business_calls_reserved=2,
        required_processing_seconds=5,
    )
    assert result.error_code == "model_limit_exceeded"
    assert len(model.structured_calls) == (1 if slow_stage == "retry" else 0)
    assert result.selector_called is (slow_stage == "retry")
    assert scope.model_usage().model_attempts == (2 if slow_stage == "retry" else 1)
    assert remaining[0] == 24.0


async def test_selector_processing_allowance_leaves_room_for_business():
    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.clock",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    model = ControlledSelectorAndBusinessModel(
        [
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["get_order"])),
            _ai_msg("business"),
        ]
    )
    gateway = ModelGateway(model, ModelCallLimits(3, 10, 0))
    scope = _scope(active_timeout_seconds=40)
    out = await ToolSelector(registry, gateway).select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
        need_text="order",
        business_calls_reserved=1,
        required_processing_seconds=5,
    )
    assert out.status == "selected" and out.selector_called
    result = await gateway.invoke(
        [HumanMessage(content="business")],
        context=ModelCallContext("run", "task", AgentType.ORDER),
        model_usage=scope.model_usage(),
    )
    assert result.model_usage.model_attempts == 2


async def test_selector_receipts_survive_business_context_and_multiple_calls():
    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.receipts",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    model = ControlledSelectorAndBusinessModel(
        [
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["get_order"])),
            _ai_msg("business"),
            TimeoutError("controlled"),
        ]
    )
    gateway = ModelGateway(
        model, ModelCallLimits(8, 10, 0), context_window=4096, output_reserve=128
    )
    selector = ToolSelector(registry, gateway)
    scope = _scope()
    args = dict(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
    )
    first = await selector.select(**args, need_text="first")
    business = await gateway.invoke(
        [HumanMessage(content="business")],
        context=ModelCallContext(
            "run-1",
            "task-1",
            AgentType.ORDER,
            on_context_view=scope.record_context_view,
            on_context_usage=scope.record_context_usage,
        ),
        model_usage=scope.model_usage(),
    )
    scope.adopt_model_usage(business.model_usage)
    failed = await selector.select(**args, need_text="second", existing_record=first.record)
    assert failed.error_code == "model_timeout"
    receipts = scope.selector_receipts
    assert len(receipts) == 2 and receipts[0]["id"] != receipts[1]["id"]
    assert receipts[0]["status"] == "selected" and receipts[0]["usage"]["status"] == "known"
    assert receipts[1]["status"] == "failed" and receipts[1]["usage"]["status"] == "unknown"
    assert [r["provider_calls"] for r in receipts] == [1, 1]
    assert scope.context_view["provider_usage"]["status"] == "known"
    assert "selector_usage" not in scope.context_view
    new_scope = _scope(model_attempts=scope.model_usage().model_attempts)
    new_scope.adopt_selector_receipts(receipts)
    new_scope.adopt_selector_receipts(receipts)
    assert new_scope.selector_receipts == receipts


async def test_selector_receipt_not_started_does_not_claim_provider_usage():
    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.receipts",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    model = ControlledSelectorAndBusinessModel([])
    scope = _scope()
    remaining = [20.0]
    scope.remaining_active_seconds = lambda: remaining[0]

    async def reserve(_):
        remaining[0] = 10.0

    scope.reserve_model_attempt = reserve
    result = await ToolSelector(registry, ModelGateway(model, ModelCallLimits(8, 10, 0))).select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
        need_text="order",
    )
    assert not result.selector_called and result.error_code == "model_limit_exceeded"
    receipt = scope.selector_receipts[0]
    assert receipt["status"] == "not_started" and receipt["reserved_attempts"] == 1
    assert receipt["provider_calls"] == 0 and receipt["usage"] is None


async def test_selector_retry_receipt_preserves_unknown_and_actual_provider_count():
    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.receipts",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    model = ControlledSelectorAndBusinessModel(
        [
            TimeoutError("first attempt"),
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["get_order"])),
        ]
    )
    scope = _scope()
    result = await ToolSelector(registry, ModelGateway(model, ModelCallLimits(8, 10, 1))).select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
        need_text="query",
    )
    assert result.status == "selected"
    receipt = scope.selector_receipts[0]
    assert (receipt["task_id"], receipt["run_id"]) == ("task-1", "run-1")
    assert receipt["provider_calls"] == 2 and receipt["reserved_attempts"] == 2
    assert receipt["usage"]["status"] == "unknown" and receipt["usage"]["total_tokens"] is None
    assert "query" not in str(receipt)


def test_selector_receipts_follow_task_continuation_not_new_task():
    from app.graph.transfers import create_specialist_state

    execution = _execution(run_id="run-2")
    receipt = {
        "id": "receipt-1",
        "task_id": "task-1",
        "run_id": "run-1",
        "status": "selected",
        "provider_calls": 1,
        "reserved_attempts": 1,
        "usage": {"status": "known"},
        "error_code": None,
    }
    saved = {
        "task_status": TaskStatus.NEEDS_INPUT,
        "pending_task": {
            "user_id": execution.user_id,
            "conversation_id": execution.conversation_id,
            "workflow_id": execution.workflow_id,
            "task_id": execution.task_id,
            "task_type": TaskType.ORDER_QUERY,
            "task_goal": "order",
            "entities": {},
            "missing_fields": ["order_id"],
            "clarification_question": "Which order?",
            "task_message_ids": [],
        },
        "task_message_ids": [],
        "model_call_usage": {"model_attempts": 1},
        "run_usage": {"tool_calls": 0, "active_elapsed_ms": 0},
        "selector_receipts": [receipt],
    }
    continued = create_turn_state(execution, "order-1", task_mode="continue", saved_task=saved)
    assert continued["selector_receipts"] == [receipt]
    old = {key: value for key, value in saved.items() if key != "selector_receipts"}
    assert (
        create_turn_state(execution, "order-1", task_mode="continue", saved_task=old)[
            "selector_receipts"
        ]
        == []
    )
    assert (
        create_turn_state(execution, "new", task_mode="new", saved_task=saved)["selector_receipts"]
        == []
    )
    scope = _scope()
    scope.adopt_selector_receipts(continued["selector_receipts"])
    req = SpecialistInput(
        context=execution,
        task_id=execution.task_id,
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        task_goal="order",
    )
    assert create_specialist_state(req, scope=scope)["selector_receipts"] == [receipt]


async def test_interrupted_selector_receipt_remains_unknown_in_saver():
    import asyncio

    from langgraph.checkpoint.memory import InMemorySaver

    from app.runtime.selection_reservation import SelectionReservation

    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.receipts",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    saver = InMemorySaver()
    scope = _scope()
    scope.selection_reservation = SelectionReservation(
        saver,
        thread_id="thread",
        owner={"user_id": "dev-user", "conversation_id": "conv-1", "task_id": "task-1"},
        run_id="run-1",
        source_checkpoint_id=None,
    )
    model = ControlledSelectorAndBusinessModel([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await ToolSelector(registry, ModelGateway(model, ModelCallLimits(8, 10, 0))).select(
            execution=_execution(),
            agent_type=AgentType.ORDER,
            task_type=TaskType.ORDER_QUERY,
            purpose_spec=purpose,
            permission_scopes=frozenset({"orders:read"}),
            scope=scope,
            need_text="sensitive need",
        )
    saved = await saver.aget_tuple(
        {"configurable": {"thread_id": "thread", "checkpoint_ns": "v203-reservation:task-1"}}
    )
    receipt = saved.checkpoint["channel_values"]["selector_receipts"][0]
    assert receipt["status"] == "pending_unknown" and receipt["provider_calls"] is None
    assert receipt["usage"] is None and "sensitive need" not in str(receipt)
    assert saved.checkpoint["channel_values"]["attempts"] == 1


async def test_selector_deadline_does_not_restart_after_slow_begin():
    import asyncio

    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.deadline",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    model = ControlledSelectorAndBusinessModel([])
    scope = _scope()

    async def slow_begin(count):
        await asyncio.sleep(0.03)

    scope.begin_selection = slow_begin
    result = await ToolSelector(
        registry, ModelGateway(model, ModelCallLimits(8, 10, 0)), selector_timeout_seconds=0.01
    ).select(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
        need_text="order",
    )
    assert result.error_code == "model_limit_exceeded" and not result.selector_called
    assert not model.structured_calls


async def test_selector_receipts_survive_reservation_and_new_run_without_duplicates():
    from types import SimpleNamespace

    from langgraph.checkpoint.memory import InMemorySaver

    from app.runtime.selection_reservation import SelectionReservation

    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.receipts",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    saver = InMemorySaver()
    owner = {"user_id": "dev-user", "conversation_id": "conv-1", "task_id": "task-1"}
    model = ControlledSelectorAndBusinessModel(
        [
            _structured_resp(SelectorOutput(action="use_tools", tool_names=["get_order"])),
            TimeoutError("rediscovery timeout"),
        ]
    )
    selector = ToolSelector(registry, ModelGateway(model, ModelCallLimits(8, 10, 0)))
    scope1 = _scope()
    reservation1 = SelectionReservation(
        saver, thread_id="thread", owner=owner, run_id="run-1", source_checkpoint_id=None
    )
    scope1.selection_reservation = reservation1

    def args(scope, run_id):
        return dict(
            execution=_execution(run_id=run_id),
            agent_type=AgentType.ORDER,
            task_type=TaskType.ORDER_QUERY,
            purpose_spec=purpose,
            permission_scopes=frozenset({"orders:read"}),
            scope=scope,
        )

    first = await selector.select(**args(scope1, "run-1"), need_text="first")
    state1 = {
        **owner,
        "run_id": "run-1",
        "task_status": "needs_input",
        "model_call_usage": {"model_attempts": 1},
        "tool_selection_record": first.record.model_dump(mode="json"),
        "selector_receipts": scope1.selector_receipts,
    }
    snapshot1 = SimpleNamespace(
        values=state1, config={"configurable": {"checkpoint_id": "cp1"}}, next=()
    )
    await reservation1.confirm(snapshot1)
    scope2 = _scope(model_attempts=1)
    scope2.adopt_selector_receipts(state1["selector_receipts"])
    reservation2 = SelectionReservation(
        saver, thread_id="thread", owner=owner, run_id="run-2", source_checkpoint_id="cp1"
    )
    await reservation2.load(snapshot1)
    scope2.adopt_selector_receipts(reservation2.value["selector_receipts"])
    scope2.selection_reservation = reservation2
    reused = await selector.select(
        **args(scope2, "run-2"), need_text="first", existing_record=first.record
    )
    assert reused.reused and len(scope2.selector_receipts) == 1
    failed = await selector.select(
        **args(scope2, "run-2"), need_text="second", existing_record=reused.record
    )
    assert failed.error_code == "model_timeout" and len(scope2.selector_receipts) == 2
    state2 = {
        **owner,
        "run_id": "run-2",
        "task_status": "failed",
        "model_call_usage": {"model_attempts": 2},
        "tool_selection_record": failed.record.model_dump(mode="json"),
        "selector_receipts": scope2.selector_receipts,
    }
    snapshot2 = SimpleNamespace(
        values=state2, config={"configurable": {"checkpoint_id": "cp2"}}, next=()
    )
    await reservation2.confirm(snapshot2)
    reservation3 = SelectionReservation(
        saver, thread_id="thread", owner=owner, run_id="run-3", source_checkpoint_id="cp2"
    )
    await reservation3.load(snapshot2)
    scope3 = _scope(model_attempts=2)
    scope3.adopt_selector_receipts(state2["selector_receipts"])
    scope3.adopt_selector_receipts(reservation3.value["selector_receipts"])
    assert len(scope3.selector_receipts) == 2
    assert scope3.selector_receipts[0]["usage"]["status"] == "known"
    assert scope3.selector_receipts[1]["usage"]["status"] == "unknown"


async def test_rediscovery_deadline_starts_before_its_first_reservation():
    import asyncio

    registry = _build_full_registry()
    purpose = PurposeSpec(
        purpose="test.rediscovery-clock",
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        allowed_tools=frozenset({"get_order", "list_orders"}),
    )
    model = ControlledSelectorAndBusinessModel([])
    selector = ToolSelector(
        registry, ModelGateway(model, ModelCallLimits(8, 10, 0)), selector_timeout_seconds=0.01
    )
    scope = _scope()
    args = dict(
        execution=_execution(),
        agent_type=AgentType.ORDER,
        task_type=TaskType.ORDER_QUERY,
        purpose_spec=purpose,
        permission_scopes=frozenset({"orders:read"}),
        scope=scope,
    )
    first = await selector.select(**args, need_text="first", deterministic_target="get_order")

    async def slow_begin(count):
        await asyncio.sleep(0.03)

    scope.begin_selection = slow_begin
    changed = await selector.select(**args, need_text="changed", existing_record=first.record)
    assert changed.error_code == "model_limit_exceeded" and not changed.selector_called
    assert changed.record.rediscovery_count == 1 and not model.structured_calls
