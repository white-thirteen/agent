"""Seven-node order agent. All database access goes through the governed executor."""

from dataclasses import asdict

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.agents.types import AgentType, TaskType
from app.graph.contracts import (
    FailureDetails,
    GraphProtocolError,
    SpecialistInput,
    SpecialistResult,
)
from app.graph.specialists.preferences import preference_instructions, read_optional_preferences
from app.graph.state import SpecialistState
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import ModelCallContext, ModelCallError
from app.runtime.models import RunUsage
from app.tools.implementations.orders import (
    GetOrderArgs,
    GetOrderData,
    ListOrdersArgs,
    ListOrdersData,
)
from app.tools.messages import execute_tool_calls, parse_tool_calls, to_tool_message
from app.tools.models import ParsedToolCall, ToolExecutionContext, ToolExecutionResult


class OrderState(SpecialistState, total=False):
    query_spec: dict | None
    pending_calls: list[dict]
    batch_results: list[dict]
    call_records: dict
    verified_order_facts: dict | None
    candidate_answer: str | None
    outcome: str | None
    error_code: str | None
    question: str | None
    missing_fields: list[str]
    selected_tools: list[tuple[str, str]]


def build_order_graph(*, gateway, registry, executor):
    """Construct the bounded model/tool loop with one target-specific tool."""

    def check_request(state: OrderState, runtime: Runtime[RunExecutionContext]):
        request = SpecialistInput.model_validate(state["request"])
        if (
            request.context != runtime.context.context
            or request.agent_type is not AgentType.ORDER
            or request.task_type is not TaskType.ORDER_QUERY
        ):
            raise GraphProtocolError("Order request association mismatch")
        return {
            "query_spec": None,
            "pending_calls": [],
            "batch_results": [],
            "call_records": {},
            "verified_order_facts": None,
            "candidate_answer": None,
            "outcome": None,
            "error_code": None,
            "question": None,
            "missing_fields": [],
            "selected_tools": [],
        }

    def prepare_query_core(state: OrderState):
        request = state["request"]
        entities = request.entities
        goal = request.task_goal.lower()
        if any(
            term in goal
            for term in (
                "取消订单",
                "申请退款",
                "发起退款",
                "修改物流",
                "cancel order",
                "request refund",
            )
        ):
            return {"outcome": "rejected", "error_code": "unsupported_order_action"}
        kind = entities.get("query_kind")
        order_id = entities.get("order_id")
        if kind == "list" and order_id:
            return {
                "outcome": "needs_input",
                "question": "请确认是查询单个订单还是订单列表。",
                "missing_fields": ["query_kind"],
            }
        if kind is None and order_id:
            kind = "get"
        if kind is None:
            text = " ".join(
                [request.task_goal]
                + [m.content for m in request.messages if isinstance(m.content, str)]
            ).lower()
            if any(
                word in text
                for word in (
                    "列表",
                    "全部订单",
                    "所有订单",
                    "我的订单",
                    "list orders",
                    "order list",
                )
            ):
                kind = "list"
            elif any(word in text for word in ("订单号", "单个订单", "order id", "specific order")):
                kind = "get"
        if kind not in ("get", "list"):
            return {
                "outcome": "needs_input",
                "question": "请问要查询单个订单还是订单列表？",
                "missing_fields": ["query_kind"],
            }
        if kind == "get" and not order_id:
            return {
                "outcome": "needs_input",
                "query_spec": {"kind": "get"},
                "question": "请提供要查询的订单号。",
                "missing_fields": ["order_id"],
            }
        try:
            if kind == "get":
                args = GetOrderArgs.model_validate({"order_id": order_id}).model_dump(mode="json")
            else:
                values = {key: entities[key] for key in ("limit", "offset") if key in entities}
                args = ListOrdersArgs.model_validate(values).model_dump(mode="json")
        except ValidationError:
            return {"outcome": "rejected", "error_code": "invalid_order_query"}
        return {"query_spec": {"kind": kind, **args}}

    async def prepare_query(state, runtime):
        update = await read_optional_preferences(
            state, runtime, registry=registry, executor=executor, node="prepare_query"
        )
        if update.get("outcome"):
            return update
        return {**update, **prepare_query_core(state)}

    def select_tools(state: OrderState, runtime: Runtime[RunExecutionContext]):
        target = "get_order" if state["query_spec"]["kind"] == "get" else "list_orders"
        views = registry.list(
            agent_type=AgentType.ORDER, permission_scopes=runtime.context.permission_scopes
        )
        allowed = [view for view in views if view.metadata.name == target]
        if not allowed:
            definition = registry.get(target)
            return {
                "outcome": "rejected" if definition and definition.metadata.enabled else "failed",
                "error_code": "tool_not_allowed"
                if definition and definition.metadata.enabled
                else "capability_unavailable",
            }
        return {"selected_tools": [(target, allowed[0].metadata.version)]}

    async def plan_query(state: OrderState, runtime: Runtime[RunExecutionContext]):
        scope = runtime.context.scope
        spec = state["query_spec"]
        selected = state["selected_tools"]
        views = registry.list(
            agent_type=AgentType.ORDER, permission_scopes=runtime.context.permission_scopes
        )
        schemas = [
            view.model_schema
            for view in views
            if (view.metadata.name, view.metadata.version) in selected
        ]
        if len(schemas) != 1:
            return {"outcome": "failed", "error_code": "tool_not_allowed"}
        instructions = (
            "You are an order query planner. Use only the supplied tool and exact target. "
            "Do not invent order facts. If a tool result is already present, finish briefly. "
            f"Target: {spec}." + preference_instructions(state)
        )
        try:
            result = await gateway.invoke(
                [SystemMessage(content=instructions), *state["messages"]],
                context=ModelCallContext(
                    state["request"].context.run_id, state["request"].task_id, AgentType.ORDER
                ),
                model_usage=scope.model_usage(),
                tools=schemas,
            )
            scope.adopt_model_usage(result.model_usage)
        except ModelCallError as error:
            scope.adopt_model_usage(error.model_usage)
            return {
                "outcome": "failed",
                "error_code": error.code,
                "model_call_usage": asdict(scope.model_usage()),
            }
        message = result.message
        try:
            calls = parse_tool_calls(
                message,
                used_ids=set(state.get("call_records", {})),
                max_calls=executor.max_calls_per_message,
            )
        except ValueError:
            return {
                "outcome": "failed",
                "error_code": "invalid_tool_call",
                "model_call_usage": asdict(scope.model_usage()),
            }
        if calls:
            return {
                "messages": [message],
                "pending_calls": [asdict(call) for call in calls],
                "model_call_usage": asdict(scope.model_usage()),
            }
        if not state.get("verified_order_facts"):
            return {
                "outcome": "failed",
                "error_code": "model_answer_without_facts",
                "model_call_usage": asdict(scope.model_usage()),
            }
        return {
            "outcome": "completed",
            "candidate_answer": str(message.content),
            "model_call_usage": asdict(scope.model_usage()),
        }

    async def execute_query(state: OrderState, runtime: Runtime[RunExecutionContext]):
        spec = state["query_spec"]
        name = "get_order" if spec["kind"] == "get" else "list_orders"
        definition = registry.get(name)
        if definition is None or state["selected_tools"] != [(name, definition.metadata.version)]:
            raise GraphProtocolError("Order tool selection does not match query target")
        constraints = {key: value for key, value in spec.items() if key != "kind"}
        execution = runtime.context
        tool_context = ToolExecutionContext(
            execution.context,
            AgentType.ORDER,
            TaskType.ORDER_QUERY,
            None,
            execution.permission_scopes,
            "model",
            frozenset({(name, definition.metadata.version)}),
            {name: constraints},
            execution.scope.limits,
            execution.scope,
        )
        calls = [ParsedToolCall(**call) for call in state["pending_calls"]]
        results = await execute_tool_calls(calls, executor=executor, context=tool_context)
        records = dict(state.get("call_records", {}))
        for call, result in zip(calls, results, strict=True):
            records[call.call_id] = {
                "call": asdict(call),
                "normalized_args": result.normalized_args,
                "result": asdict(result),
                "origin": tool_context.origin,
                "run_id": tool_context.execution.run_id,
            }
        return {
            "batch_results": [asdict(result) for result in results],
            "call_records": records,
            "run_usage": asdict(execution.scope.run_usage()),
        }

    def observe_order(state: OrderState, runtime: Runtime[RunExecutionContext]):
        results = []
        for raw in state["batch_results"]:
            results.append(
                ToolExecutionResult(**{**raw, "run_usage": RunUsage(**raw["run_usage"])})
            )
        messages = [to_tool_message(result, task_id=state["request"].task_id) for result in results]
        for result in results:
            if result.status != "success":
                status = (
                    "rejected"
                    if result.status in ("business_rejected", "policy_denied")
                    and result.code != "tool_budget_exceeded"
                    else "failed"
                )
                return {
                    "messages": messages,
                    "outcome": status,
                    "error_code": result.code,
                    "run_usage": asdict(runtime.context.scope.run_usage()),
                }
        spec = state["query_spec"]
        last = results[-1]
        try:
            if spec["kind"] == "get":
                data = GetOrderData.model_validate(last.data)
                if data.order.order_id != spec["order_id"]:
                    raise GraphProtocolError("Order result target mismatch")
                facts = {
                    "kind": "get",
                    "order": data.order.model_dump(mode="json"),
                    "simulated": True,
                }
            else:
                data = ListOrdersData.model_validate(last.data)
                if (
                    data.limit != spec["limit"]
                    or data.offset != spec["offset"]
                    or data.returned_count != len(data.orders)
                    or data.returned_count > spec["limit"]
                ):
                    raise GraphProtocolError("Order list result target mismatch")
                facts = {"kind": "list", **data.model_dump(mode="json"), "simulated": True}
        except ValidationError:
            return {"messages": messages, "outcome": "failed", "error_code": "tool_result_invalid"}
        return {
            "messages": messages,
            "verified_order_facts": facts,
            "pending_calls": [],
            "run_usage": asdict(runtime.context.scope.run_usage()),
        }

    def map_result(state: OrderState, runtime: Runtime[RunExecutionContext]):
        request = state["request"]
        outcome = state["outcome"]
        facts = state.get("verified_order_facts")
        data = {
            "workflow_id": request.context.workflow_id,
            "run_id": request.context.run_id,
            "task_id": request.task_id,
            "agent_type": AgentType.ORDER,
            "task_type": TaskType.ORDER_QUERY,
            "status": outcome,
            "summary": "模拟订单查询未完成。",
        }
        if outcome == "needs_input":
            data.update(
                summary=state["question"],
                clarification_question=state["question"],
                missing_fields=state["missing_fields"],
                entities={"query_kind": state["query_spec"]["kind"]}
                if state.get("query_spec")
                else {},
            )
        elif outcome == "completed":

            def render(order):
                payment = "已付款" if order["payment_status"] == "paid" else "未付款"
                refunded = "已模拟退款" if order["is_refunded"] else "未模拟退款"
                return (
                    f"{order['order_id']}，{order['amount']} {order['currency']}，"
                    f"{payment}，{refunded}"
                )

            if facts["kind"] == "get":
                summary = "模拟订单：" + render(facts["order"])
            elif not facts["orders"]:
                summary = "本次范围内没有模拟订单。"
            else:
                summary = f"模拟订单列表（本页 {facts['returned_count']} 条）：" + "；".join(
                    render(order) for order in facts["orders"]
                )
            data.update(summary=summary, facts=facts)
        elif outcome == "rejected":
            data.update(summary="订单不可访问或查询条件不被允许。")
        else:
            data.update(
                status="failed",
                error=FailureDetails(
                    code=state.get("error_code") or "order_query_unavailable",
                    message="Order query could not be completed.",
                ),
            )
        return {
            "result": SpecialistResult(**data),
            "model_call_usage": asdict(runtime.context.scope.model_usage()),
            "run_usage": asdict(runtime.context.scope.run_usage()),
        }

    def next_after_prepare(state):
        return "map_result" if state.get("outcome") else "select_tools"

    def next_after_select(state):
        return "map_result" if state.get("outcome") else "plan_query"

    def next_after_plan(state):
        return "map_result" if state.get("outcome") else "execute_query"

    def next_after_observe(state):
        return "map_result" if state.get("outcome") else "plan_query"

    graph = StateGraph(OrderState, context_schema=RunExecutionContext)
    for name, node in [
        ("check_request", check_request),
        ("prepare_query", prepare_query),
        ("select_tools", select_tools),
        ("plan_query", plan_query),
        ("execute_query", execute_query),
        ("observe_order", observe_order),
        ("map_result", map_result),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "check_request")
    graph.add_edge("check_request", "prepare_query")
    graph.add_conditional_edges(
        "prepare_query",
        next_after_prepare,
        {"map_result": "map_result", "select_tools": "select_tools"},
    )
    graph.add_conditional_edges(
        "select_tools", next_after_select, {"map_result": "map_result", "plan_query": "plan_query"}
    )
    graph.add_conditional_edges(
        "plan_query",
        next_after_plan,
        {"map_result": "map_result", "execute_query": "execute_query"},
    )
    graph.add_edge("execute_query", "observe_order")
    graph.add_conditional_edges(
        "observe_order",
        next_after_observe,
        {"map_result": "map_result", "plan_query": "plan_query"},
    )
    graph.add_edge("map_result", END)
    return graph.compile()
