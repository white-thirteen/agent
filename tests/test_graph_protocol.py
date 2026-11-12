"""Typed routing, explicit parent/child mapping and ordinary graph settlement."""

from dataclasses import asdict

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from runtime_support import ControlledModel, clarify, compiled, context, route, run_to_end

from app.agents.types import AgentType, TaskType
from app.graph.contracts import (
    ExecutionContext,
    GraphProtocolError,
    SourceReference,
    SpecialistInput,
    SpecialistResult,
)
from app.graph.router import route_after_supervisor
from app.graph.state import create_turn_state
from app.graph.transfers import (
    apply_route_decision,
    apply_specialist_result,
    build_specialist_input,
    create_specialist_state,
)
from app.runtime.agent_runtime import AgentRuntime, RunLimits


def graph_context(**updates):
    return ExecutionContext(
        **{
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "workflow_id": "task-1",
            "task_id": "task-1",
            "run_id": "run-1",
            **updates,
        }
    )


def turn(ctx=None, message="show my orders"):
    return create_turn_state(ctx or graph_context(), message, task_mode="new", saved_task=None)


def routed_state(decision=None):
    state = turn()
    state.update(apply_route_decision(state, (decision or route()).decision))
    return state


def completed_result(state, **updates):
    return SpecialistResult(
        **{
            "workflow_id": state["workflow_id"],
            "task_id": state["task_id"],
            "run_id": state["run_id"],
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
        {"task_goal": " "},
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
        route(**updates)


@pytest.mark.parametrize(
    "task,target",
    [
        (TaskType.ORDER_QUERY, "order"),
        (TaskType.REFUND_APPLY, "refund"),
        (TaskType.KNOWLEDGE_QA, "knowledge"),
        (TaskType.MEMORY_MANAGE, "knowledge"),
        (TaskType.CLARIFICATION, "clarification"),
    ],
)
def test_real_graph_conditional_edge_dispatches_validated_task(task, target):
    state = routed_state(clarify() if task is TaskType.CLARIFICATION else route(task))
    assert route_after_supervisor(state) == target
    if target == "clarification":
        with pytest.raises(GraphProtocolError):
            build_specialist_input(state)


def test_route_revalidates_instances_and_rejects_conflicting_parent_channels():
    invalid = route().decision.model_copy(update={"agent_type": AgentType.KNOWLEDGE})
    with pytest.raises(ValidationError):
        apply_route_decision(turn(), invalid)
    state = routed_state()
    state["task_type"] = TaskType.REFUND_APPLY
    with pytest.raises(GraphProtocolError):
        route_after_supervisor(state)
    with pytest.raises(GraphProtocolError):
        route_after_supervisor(turn())


def test_child_input_filters_private_history_and_copies_nested_data():
    state = routed_state(route(entities={"order_ids": ["order-1"], "user_id": "untrusted"}))
    state["messages"].extend(
        [
            SystemMessage(content="private", id="system"),
            ToolMessage(content="raw", tool_call_id="call", id="tool"),
            AIMessage(
                content="", id="call", tool_calls=[{"name": "lookup", "args": {}, "id": "call"}]
            ),
            AIMessage(
                content="public reply", id="answer", additional_kwargs={"private": "metadata"}
            ),
        ]
    )
    state["task_message_ids"].extend(["system", "tool", "call", "answer"])
    request = build_specialist_input(state)
    child = create_specialist_state(request)
    assert [message.content for message in request.messages] == ["show my orders", "public reply"]
    assert all(not message.additional_kwargs for message in request.messages)
    assert "user_id" not in request.entities
    child["request"].entities["order_ids"].append("order-2")
    child["messages"][0].content = "changed in child"
    assert state["route_decision"].entities["order_ids"] == ["order-1"]
    assert request.entities["order_ids"] == ["order-1"]
    invalid = request.model_dump()
    invalid["messages"] = [SystemMessage(content="private")]
    with pytest.raises(ValidationError):
        SpecialistInput.model_validate(invalid)


def test_contracts_round_trip_json_preserving_message_and_enum_types():
    restored = SpecialistInput.model_validate_json(
        build_specialist_input(routed_state()).model_dump_json()
    )
    assert restored.task_type is TaskType.ORDER_QUERY
    assert isinstance(restored.messages[0], HumanMessage)


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "waiting_approval"},
        {"status": "failed"},
        {"facts": {}},
        {"status": "needs_input"},
        {"error": {"code": "bad_result", "message": "error on success"}},
        {"messages": []},
        {"user_id": "injected"},
        {"agent_type": "supervisor"},
        {"task_type": "order_cancel"},
        {"agent_type": "refund", "task_type": "refund_apply", "operation_id": "operation"},
    ],
)
def test_result_contract_rejects_inconsistent_or_unsubstantiated_results(updates):
    with pytest.raises(ValidationError):
        completed_result(routed_state(), **updates)


def test_completed_qa_requires_approved_answer_and_sources_memory_requires_store_facts():
    state = routed_state(route(TaskType.KNOWLEDGE_QA))
    source = SourceReference(
        document_id="policy", document_version="v1", chunk_id="1", title="Policy"
    )
    with pytest.raises(ValidationError):
        completed_result(state, sources=[source])
    result = completed_result(state, sources=[source], approved_answer="Verified answer")
    assert apply_specialist_result(state, result)["sources"] == [source]
    memory = routed_state(route(TaskType.MEMORY_MANAGE))
    with pytest.raises(ValidationError):
        completed_result(memory, sources=[source])
    assert completed_result(memory, facts={"status": "applied", "revision": 1}).sources == []


@pytest.mark.parametrize(
    "updates",
    [
        {"workflow_id": "foreign"},
        {"task_id": "foreign"},
        {"run_id": "foreign"},
        {
            "agent_type": "refund",
            "task_type": "refund_apply",
            "operation_id": "op",
            "approval_id": "approval",
        },
    ],
)
def test_foreign_result_is_rejected_even_when_valid_contract(updates):
    state = routed_state()
    with pytest.raises(GraphProtocolError):
        apply_specialist_result(state, completed_result(state, **updates))
    assert state["specialist_result"] is None


def test_explicit_continuation_keeps_task_usage_and_clears_transient_results():
    state = routed_state(clarify(TaskType.ORDER_QUERY))
    state["model_call_usage"] = {"model_attempts": 3}
    state["run_usage"] = {"tool_calls": 2, "active_elapsed_ms": 20}
    next_turn = create_turn_state(
        graph_context(run_id="run-2"), "order-1", task_mode="continue", saved_task=state
    )
    assert next_turn["task_id"] == state["task_id"]
    assert next_turn["run_usage"] == state["run_usage"]
    assert next_turn["model_call_usage"] == state["model_call_usage"]
    assert next_turn["route_decision"] is None and next_turn["specialist_result"] is None
    assert next_turn["final_answer"] is None and next_turn["sources"] == []
    for updates in (
        {"user_id": "foreign"},
        {"conversation_id": "foreign"},
        {"workflow_id": "foreign", "task_id": "foreign"},
    ):
        with pytest.raises(GraphProtocolError):
            create_turn_state(
                graph_context(**updates), "order", task_mode="continue", saved_task=state
            )


async def test_real_topology_scope_settlement_and_no_post_end_update(monkeypatch):
    saver = InMemorySaver()
    graph = compiled(ControlledModel([clarify()]), saver=saver)

    async def forbidden(*args, **kwargs):
        pytest.fail("Ordinary END must not write another state update")

    monkeypatch.setattr(type(graph), "aupdate_state", forbidden)
    runtime = AgentRuntime(graph, run_limits=RunLimits(10, 12))
    ctx = context()
    handle, view, events = await run_to_end(runtime, ctx)
    snapshot = await graph.aget_state({"configurable": {"thread_id": ctx.thread_id}})
    assert not snapshot.next
    assert snapshot.values["run_usage"] == asdict(view.run_usage)
    assert snapshot.values["model_call_usage"] == asdict(view.model_call_usage)
    assert snapshot.values["task_id"] == handle.task_id == handle.workflow_id
    assert [message.id for message in snapshot.values["messages"]] == [
        f"user:{ctx.run_id}",
        f"assistant:{ctx.run_id}",
    ]
    assert sum(event.kind == "done" for event in events) == 1
    assert view.task_status == "needs_input"
    await runtime.shutdown()


@pytest.mark.parametrize(
    "task",
    [TaskType.REFUND_APPLY, TaskType.KNOWLEDGE_QA, TaskType.MEMORY_MANAGE],
)
async def test_actual_compiled_skeletons_fail_safely_for_all_professional_tasks(task):
    runtime = AgentRuntime(compiled(ControlledModel([route(task)])), run_limits=RunLimits(10, 12))
    _, view, events = await run_to_end(runtime, context())
    assert view.error["code"] == "capability_unavailable" and view.task_status == "failed"
    assert view.model_call_usage.model_attempts == 1
    assert not any(event.kind == "token" for event in events)
    await runtime.shutdown()


async def test_nested_success_is_approved_once_and_foreign_request_is_rejected():
    from langgraph.graph import END, START, StateGraph
    from langgraph.runtime import Runtime

    from app.graph.specialists.knowledge.builder import build_knowledge_graph
    from app.graph.specialists.refund.builder import build_refund_graph
    from app.graph.state import SpecialistState
    from app.runtime.context import RunExecutionContext

    def success(state: SpecialistState, runtime: Runtime[RunExecutionContext]):
        request = state["request"]
        assert request.context == runtime.context.context
        return {
            "messages": [ToolMessage(content="private raw result", tool_call_id="call")],
            "model_call_usage": {"model_attempts": 0},
            "result": SpecialistResult(
                workflow_id=request.context.workflow_id,
                run_id=request.context.run_id,
                task_id=request.task_id,
                agent_type=request.agent_type,
                task_type=request.task_type,
                status="completed",
                summary="No matching orders",
                facts={"orders": []},
            ),
        }

    child = StateGraph(SpecialistState, context_schema=RunExecutionContext)
    child.add_node("success", success)
    child.add_edge(START, "success")
    child.add_edge("success", END)
    specialists = {
        AgentType.ORDER: child.compile(),
        AgentType.REFUND: build_refund_graph(),
        AgentType.KNOWLEDGE: build_knowledge_graph(),
    }
    runtime = AgentRuntime(
        compiled(ControlledModel([route()]), specialists=specialists), run_limits=RunLimits(10, 12)
    )
    ctx = context()
    handle, view, events = await run_to_end(runtime, ctx)
    assert view.final_answer == "No matching orders" and view.model_call_usage.model_attempts == 1
    snapshot = await runtime._graph.aget_state({"configurable": {"thread_id": ctx.thread_id}})
    assert all(
        "private raw result" not in str(message.content) for message in snapshot.values["messages"]
    )
    assert sum(event.kind == "token" for event in events) == 1
    await runtime.shutdown()

    def foreign(state: SpecialistState, runtime: Runtime[RunExecutionContext]):
        output = success(state, runtime)
        output["request"] = state["request"].model_copy(
            update={"context": state["request"].context.model_copy(update={"user_id": "foreign"})}
        )
        return output

    child = StateGraph(SpecialistState, context_schema=RunExecutionContext)
    child.add_node("foreign", foreign)
    child.add_edge(START, "foreign")
    child.add_edge("foreign", END)
    specialists[AgentType.ORDER] = child.compile()
    runtime = AgentRuntime(
        compiled(ControlledModel([route()]), specialists=specialists), run_limits=RunLimits(10, 12)
    )
    _, view, events = await run_to_end(runtime, context())
    assert not view.usage_complete and not any(event.kind == "token" for event in events)
    await runtime.shutdown()


def test_task_message_window_excludes_other_tasks_reasoning_and_metadata():
    from app.graph.transfers import public_task_messages

    state = turn()
    state["messages"] += [HumanMessage(content=str(i), id=f"public-{i}") for i in range(20)]
    state["task_message_ids"] += [f"public-{i}" for i in range(20)]
    state["messages"].append(AIMessage(content="other task private", id="not-in-this-task"))
    selected = public_task_messages(state)
    assert len(selected) == 12 and selected[0].content == "8"
    assert all(message.content != "other task private" for message in selected)
