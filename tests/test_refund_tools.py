"""Refund definitions stay unregistered until the trusted approval path exists."""

import psycopg
import pytest
from pydantic import ValidationError

from app.tools.implementations.refunds import RefundOrderArgs, refund_node_tools, refund_order_tool
from app.tools.models import BusinessExecutionContext, ToolTransientError
from app.tools.registry import ToolRegistry


def test_refund_definitions_have_safe_metadata_and_reject_identity_in_args():
    with pytest.raises(ValidationError):
        RefundOrderArgs(order_id="order", user_id="forged")
    registry = ToolRegistry()
    for definition in (
        *refund_node_tools(None, None, timeout_seconds=5),
        refund_order_tool(None, timeout_seconds=5),
    ):
        registry.register(definition)
    registry.freeze()
    refund = registry.get("refund_order")
    assert refund.metadata.approval_required and refund.metadata.risk_level == "high"
    assert refund.metadata.has_business_side_effects and refund.metadata.max_retries == 0
    assert registry.get("prepare_refund_application").metadata.max_retries == 0
    assert registry.get("check_refund_eligibility").metadata.read_only


async def test_refund_adapter_classifies_read_failure_without_exposing_database_error():
    class FailedService:
        async def check_eligibility(self, *, context, order_id):
            raise psycopg.OperationalError("sensitive detail")

    definition = refund_node_tools(FailedService(), None, timeout_seconds=5)[0]
    with pytest.raises(ToolTransientError, match="Refund eligibility unavailable"):
        await definition.handler(
            RefundOrderArgs(order_id="order"), BusinessExecutionContext("user", "task", "run")
        )
