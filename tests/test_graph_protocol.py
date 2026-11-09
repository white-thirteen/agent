"""Validate graph boundaries and execute real conditional edges and nested graphs."""

from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agents.types import AgentType, TaskType
from app.graph.contracts import (
    ExecutionContext,
    GraphProtocolError,
    ResultStatus,
    RouteDecision,
    SourceReference,
    SpecialistInput,
    SpecialistResult,
)
from app.graph.router import route_after_supervisor
from app.graph.state import AgentState, SpecialistState, create_turn_state
from app.graph.transfers import (
    apply_route_decision,
    apply_specialist_result,
    build_specialist_input,
    create_specialist_state,
)


def context(**updates) -> ExecutionContext:
    return ExecutionContext(
        **{
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "workflow_id": "workflow-1",
            "run_id": "run-1",
            **updates,
        }
    )


def decision(task=TaskType.ORDER_QUERY, **updates) -> RouteDecision:
    return RouteDecision.model_validate(
        {
            "agent_type": task.target_agent,
            "task_type": task,
            "task_goal": "Find the requested order",
            **updates,
        }
    )


def routed_state(route=None) -> AgentState:
    state = create_turn_state(context(), "show my orders")
    state.update(apply_route_decision(state, route or decision()))
    return state


def completed_result(state: AgentState, **updates) -> SpecialistResult:
    return SpecialistResult.model_validate(
        {
            "workflow_id": state["workflow_id"],
            "run_id": state["run_id"],
            "task_id": state["task_id"],
            "agent_type": state["agent_type"],
            "task_type": state["task_type"],
            "status": "completed",
            "summary": "No matching orders",
            "facts": {"orders": []},
            **updates,
        }
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"agent_type": "knowledge"},
        {"task_type": "unknown"},
        {"user_id": "injected-user"},
        {"node": "execute_refund"},
        {"task_goal": "   "},
        {"needs_clarification": "false"},
        {"missing_fields": ["order_id"]},
        {"needs_clarification": True},
        {
            "needs_clarification": True,
            "missing_fields": ["order_id", "order_id"],
            "clarification_question": "Which order?",
        },
    ],
)
def test_route_contract_rejects_invalid_or_privileged_model_output(updates):
    with pytest.raises(ValidationError):
        decision(**updates)


@pytest.mark.parametrize(
    ("task", "needs_input", "target"),
    [
        (TaskType.ORDER_QUERY, False, "order"),
        (TaskType.ORDER_CANCEL, False, "order"),
        (TaskType.REFUND_REQUEST, False, "after_sales"),
        (TaskType.KNOWLEDGE_QA, False, "knowledge"),
        (TaskType.CLARIFICATION, True, "clarification"),
        (TaskType.ORDER_CANCEL, True, "clarification"),
    ],
)
def test_real_graph_conditional_edge_dispatches_validated_task(task, needs_input, target):
    route = decision(
        task,
        needs_clarification=needs_input,
        missing_fields=["order_id"] if needs_input else [],
        clarification_question="Which order?" if needs_input else None,
    )

    def supervisor(state: AgentState):
        return apply_route_decision(state, route)

    def branch(name):
        def visit(state: AgentState):
            return {"final_answer": name}

        return visit

    builder = StateGraph(AgentState)
    builder.add_node("supervisor", supervisor)
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", route_after_supervisor)
    for name in ("order", "after_sales", "knowledge", "clarification"):
        builder.add_node(name, branch(name))
        builder.add_edge(name, END)
    result = builder.compile().invoke(create_turn_state(context(), "test question"))

    assert result["final_answer"] == target
    assert result["task_type"] == task
    if needs_input:
        assert result["pending_task"].task_type == task
        with pytest.raises(GraphProtocolError):
            build_specialist_input(result)


def test_route_revalidates_instances_and_rejects_conflicting_parent_channels():
    route = decision().model_copy(update={"agent_type": AgentType.KNOWLEDGE})
    with pytest.raises(ValidationError):
        apply_route_decision(create_turn_state(context(), "orders"), route)

    state = routed_state()
    state["task_type"] = TaskType.REFUND_REQUEST
    with pytest.raises(GraphProtocolError, match="task_type"):
        route_after_supervisor(state)

    with pytest.raises(GraphProtocolError):
        route_after_supervisor(create_turn_state(context(), "orders"))


def test_child_input_filters_private_history_and_copies_nested_data():
    state = routed_state(decision(entities={"order_ids": ["order-1"], "user_id": "untrusted"}))
    state["messages"].extend(
        [
            SystemMessage(content="private prompt"),
            AIMessage(
                content="",
                tool_calls=[{"name": "lookup", "args": {}, "id": "call-1"}],
            ),
            ToolMessage(content="private raw tool result", tool_call_id="call-1"),
            AIMessage(content="public reply", additional_kwargs={"private": "metadata"}),
        ]
    )
    request = build_specialist_input(state)
    child = create_specialist_state(request)

    assert [message.content for message in request.messages] == ["show my orders", "public reply"]
    assert all(not message.additional_kwargs for message in request.messages)
    assert request.context.user_id == "user-1"
    child["request"].entities["order_ids"].append("order-2")
    child["messages"][0].content = "changed in child"
    assert state["route_decision"].entities["order_ids"] == ["order-1"]
    assert state["messages"][0].content == "show my orders"
    assert request.entities["order_ids"] == ["order-1"]

    invalid = request.model_dump()
    invalid["messages"] = [SystemMessage(content="private")]
    with pytest.raises(ValidationError):
        SpecialistInput.model_validate(invalid)


def test_contracts_round_trip_json_without_losing_enum_or_message_types():
    request = build_specialist_input(routed_state())
    restored = SpecialistInput.model_validate_json(request.model_dump_json())
    assert restored.task_type is TaskType.ORDER_QUERY
    assert restored.agent_type is AgentType.ORDER
    assert isinstance(restored.messages[0], HumanMessage)


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "waiting_approval"},
        {"status": "failed"},
        {"facts": {}},
        {"status": "needs_input"},
        {"error": {"code": "bad_result", "message": "error on successful result"}},
        {"messages": []},
        {"user_id": "injected-user"},
        {"agent_type": "supervisor"},
        {"task_type": "order_cancel"},
        {
            "agent_type": "after_sales",
            "task_type": "refund_request",
            "operation_id": "refund-operation",
        },
    ],
)
def test_result_contract_rejects_inconsistent_or_unsubstantiated_results(updates):
    with pytest.raises(ValidationError):
        completed_result(routed_state(), **updates)


def test_completed_knowledge_answer_requires_sources_and_preserves_them():
    state = routed_state(decision(TaskType.KNOWLEDGE_QA))
    with pytest.raises(ValidationError):
        completed_result(state)
    source = SourceReference(
        document_id="refund-policy", document_version="v1", chunk_id="chunk-1", title="退款政策"
    )
    result = completed_result(state, sources=[source])
    update = apply_specialist_result(state, result)
    assert update["sources"] == [source]
    assert update["final_answer"] is None


@pytest.mark.parametrize(
    "updates",
    [
        {"workflow_id": "another-workflow"},
        {"run_id": "another-run"},
        {"task_id": "another-task"},
        {"task_type": "order_cancel", "operation_id": "cancel-operation"},
        {
            "agent_type": "after_sales",
            "task_type": "refund_request",
            "operation_id": "refund-operation",
            "approval_id": "refund-approval",
        },
    ],
)
def test_foreign_result_is_rejected_even_when_it_is_a_valid_contract(updates):
    state = routed_state()
    result = completed_result(state, **updates)
    with pytest.raises(GraphProtocolError):
        apply_specialist_result(state, result)
    assert state["specialist_result"] is None


def test_needs_input_preserves_business_task_and_new_turn_changes_only_run_association():
    state = routed_state(decision(TaskType.ORDER_CANCEL, entities={"reason": "ordered by mistake"}))
    result = completed_result(
        state,
        status="needs_input",
        facts={},
        missing_fields=["order_id"],
        clarification_question="Which order should be cancelled?",
        entities={"candidate_order_ids": ["order-1", "order-2"]},
    )
    update = apply_specialist_result(state, result)
    pending = update["pending_task"]
    next_turn = create_turn_state(context(run_id="run-2"), "order-1", pending_task=pending)

    assert next_turn["task_id"] == state["task_id"]
    assert next_turn["task_type"] is TaskType.ORDER_CANCEL
    assert next_turn["task_goal"] == state["task_goal"]
    assert next_turn["run_id"] == "run-2"
    assert next_turn["pending_task"].entities == {
        "reason": "ordered by mistake",
        "candidate_order_ids": ["order-1", "order-2"],
    }
    assert next_turn["route_decision"] is None
    assert next_turn["specialist_result"] is None
    assert next_turn["final_answer"] is None

    for field in ("user_id", "conversation_id", "workflow_id"):
        with pytest.raises(GraphProtocolError):
            create_turn_state(context(**{field: "another"}), "order-1", pending_task=pending)


def test_nested_graph_whitelists_result_and_resets_transient_fields_on_next_turn():
    def lookup(state: SpecialistState):
        request = state["request"]
        return {
            "messages": [AIMessage(content="private specialist reasoning")],
            "result": SpecialistResult(
                workflow_id=request.context.workflow_id,
                run_id=request.context.run_id,
                task_id=request.task_id,
                agent_type=request.agent_type,
                task_type=request.task_type,
                status=ResultStatus.COMPLETED,
                summary="No matching orders",
                facts={"orders": []},
            ),
        }

    child_builder = StateGraph(SpecialistState)
    child_builder.add_node("lookup", lookup)
    child_builder.add_edge(START, "lookup")
    child_builder.add_edge("lookup", END)
    child = child_builder.compile()

    def supervisor(state: AgentState):
        return apply_route_decision(state, decision())

    def call_order(state: AgentState):
        output = child.invoke(create_specialist_state(build_specialist_input(state)))
        return apply_specialist_result(state, output["result"])

    def respond(state: AgentState):
        return {"final_answer": state["specialist_result"].summary}

    parent = StateGraph(AgentState)
    parent.add_node("supervisor", supervisor)
    parent.add_node("order", call_order)
    parent.add_node("response", respond)
    parent.add_edge(START, "supervisor")
    parent.add_conditional_edges("supervisor", route_after_supervisor, {"order": "order"})
    parent.add_edge("order", "response")
    parent.add_edge("response", END)
    graph = parent.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "conversation-1"}}
    first = graph.invoke(create_turn_state(context(), "orders"), config)
    assert [message.content for message in first["messages"]] == ["orders"]
    assert first["specialist_result"].facts == {"orders": []}

    new_turn = create_turn_state(context(run_id="run-2"), "orders again")
    second = graph.invoke(new_turn, config)
    assert second["task_id"] != first["task_id"]
    assert [message.content for message in second["messages"]] == ["orders", "orders again"]

    # Inspect the new-turn reset independently of later nodes overwriting it.
    assert new_turn["sources"] == []
    assert new_turn["specialist_result"] is None
    original = deepcopy(first)
    update = apply_specialist_result(first, completed_result(first))
    assert set(update) == {"specialist_result", "pending_task", "final_answer", "sources"}
    assert first == original
