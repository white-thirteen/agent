"""Checkpoint serialization uses explicit application-type allowlists."""

from dataclasses import dataclass

from app.graph.contracts import ExecutionContext
from app.infrastructure.checkpoint import checkpoint_serializer
from app.runtime.models import RunUsage
from app.tools.models import ParsedToolCall, PreparedToolAttempt, ToolExecutionResult


@dataclass
class UnapprovedType:
    value: str


def test_serializer_roundtrips_required_types_and_blocks_unknown_constructor():
    serializer = checkpoint_serializer()
    values = [
        ExecutionContext(
            user_id="u", conversation_id="c", task_id="t", workflow_id="t", run_id="r"
        ),
        PreparedToolAttempt(
            "a",
            "r",
            "t",
            ParsedToolCall("c", "refund_order", {"order_id": "o"}),
            "1",
            {"order_id": "o"},
            "digest",
            "op",
            0,
            1,
            5,
            {},
            {},
        ),
        ToolExecutionResult(
            "c",
            "refund_order",
            "e",
            "success",
            "ok",
            "done",
            {"operation_id": "op"},
            1,
            RunUsage(1, 50),
            "completed",
        ),
    ]
    for value in values:
        assert serializer.loads_typed(serializer.dumps_typed(value)) == value
    blocked = serializer.loads_typed(serializer.dumps_typed(UnapprovedType("test")))
    assert not isinstance(blocked, UnapprovedType)
