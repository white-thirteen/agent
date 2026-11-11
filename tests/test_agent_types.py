"""Public task values must resolve to one owner and reject unsupported actions."""

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from app.agents.types import AgentType, TaskType


@pytest.mark.parametrize(
    ("task_value", "agent_value"),
    [
        ("order_query", "order"),
        ("memory_manage", "knowledge"),
        ("refund_apply", "refund"),
        ("knowledge_qa", "knowledge"),
        ("clarification", "supervisor"),
    ],
)
def test_json_task_resolves_to_owner_and_serializes_as_public_value(task_value, agent_value):
    adapter = TypeAdapter(TaskType)
    task = adapter.validate_json(json.dumps(task_value))

    assert task.target_agent is AgentType(agent_value)
    assert json.loads(adapter.dump_json(task)) == task_value
    assert json.loads(json.dumps({"agent_type": task.target_agent})) == {"agent_type": agent_value}


@pytest.mark.parametrize(
    ("enum_type", "value"),
    [
        (AgentType, "general"),
        (AgentType, "after_sales"),
        (TaskType, "order_cancel"),
        (TaskType, "refund_request"),
        (AgentType, "unknown_agent"),
        (TaskType, "unknown_task"),
        (TaskType, "approve_refund"),
    ],
)
def test_unsupported_json_values_are_rejected_without_fallback(enum_type, value):
    with pytest.raises(ValidationError):
        TypeAdapter(enum_type).validate_json(json.dumps(value))


def test_every_task_has_one_owner_and_only_clarification_belongs_to_supervisor():
    owners = {task: task.target_agent for task in TaskType}

    assert set(owners.values()) == set(AgentType)
    assert {task for task, owner in owners.items() if owner is AgentType.SUPERVISOR} == {
        TaskType.CLARIFICATION
    }
