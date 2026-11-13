"""Refund tool contract; registration waits for the trusted approval executor path."""

from typing import Literal

import psycopg
from psycopg_pool import PoolClosed, PoolTimeout
from pydantic import BaseModel, ConfigDict, Field

from app.agents.types import AgentType
from app.domain.refunds import MockRefundService, RefundBusinessContext, RefundRejected
from app.tools.models import (
    BusinessRejection,
    HandlerResult,
    ToolDefinition,
    ToolMetadata,
    ToolTransientError,
    ToolUnavailableError,
)


class RefundOrderArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)
    order_id: str = Field(min_length=1, max_length=128, pattern=r"^[^\x00]+$")


class RefundOrderData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: str
    order_id: str
    amount: str
    currency: str
    simulated: Literal[True]


def refund_order_tool(service: MockRefundService, *, timeout_seconds: float) -> ToolDefinition:
    """Build the single high-risk tool; callers must not expose it before 04 approval wiring."""

    async def refund_order(args: RefundOrderArgs, context):
        if not isinstance(context, RefundBusinessContext):
            raise TypeError("Trusted refund business context is required")
        try:
            result = await service.execute_original(context=context, order_id=args.order_id)
        except RefundRejected as error:
            return HandlerResult(
                rejection=BusinessRejection(error.code, "Refund cannot be executed.")
            )
        except (psycopg.Error, PoolClosed, PoolTimeout):
            raise ToolUnavailableError("Refund execution unavailable") from None
        return HandlerResult(data=RefundOrderData.model_validate(result))

    metadata = ToolMetadata(
        name="refund_order",
        version="1",
        description="提交已审批的模拟订单退款",
        enabled=True,
        allowed_agents=frozenset({AgentType.REFUND}),
        required_scopes=frozenset({"refunds:request"}),
        risk_level="high",
        approval_required=True,
        read_only=False,
        has_business_side_effects=True,
        idempotency="operation_id_required",
        timeout_seconds=timeout_seconds,
        max_retries=0,
        tags=frozenset({"refund", "demo"}),
    )
    return ToolDefinition(metadata, RefundOrderArgs, RefundOrderData, refund_order)


class EligibilityData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    order_id: str | None = None
    amount: str | None = None
    currency: str | None = None
    simulated: Literal[True] | None = None
    status: Literal["SUCCEEDED"] | None = None
    execution_result: RefundOrderData | None = None


class PrepareRefundArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    call_id: str
    tool_name: Literal["refund_order"]
    tool_version: str
    raw_args: dict
    canonical_args: dict


class ApplicationData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    application_id: str
    operation_id: str
    order_id: str
    amount: str
    currency: str
    status: Literal["PENDING", "SUCCEEDED", "REJECTED"]


class ApprovalRegistrationArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject: dict


class ApprovalRegistrationData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    approval_id: str
    subject_digest: str


class CloseApplicationArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reason_code: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")


def refund_node_tools(service, approval_service, *, timeout_seconds: float):
    """Prepare node-only definitions; Policy must enforce node and argument constraints."""
    from app.domain.refunds import OriginalRefundCall
    from app.workflows.approvals import ApprovalError

    async def eligibility(args: RefundOrderArgs, context):
        try:
            return HandlerResult(
                data=EligibilityData.model_validate(
                    await service.check_eligibility(context=context, order_id=args.order_id)
                )
            )
        except RefundRejected as error:
            return HandlerResult(rejection=BusinessRejection(error.code, "Refund is not eligible."))
        except (psycopg.OperationalError, PoolClosed, PoolTimeout):
            raise ToolTransientError("Refund eligibility unavailable") from None
        except psycopg.Error:
            raise ToolUnavailableError("Refund eligibility unavailable") from None

    async def prepare(args: PrepareRefundArgs, context):
        if not isinstance(context, RefundBusinessContext):
            raise TypeError("Trusted refund business context is required")
        try:
            call = OriginalRefundCall(**args.model_dump())
            result = await service.prepare_application(context=context, original_call=call)
            return HandlerResult(data=ApplicationData.model_validate(result))
        except RefundRejected as error:
            return HandlerResult(
                rejection=BusinessRejection(error.code, "Refund cannot be prepared.")
            )
        except (psycopg.Error, PoolClosed, PoolTimeout):
            raise ToolUnavailableError("Refund preparation unavailable") from None

    async def register(args: ApprovalRegistrationArgs, context):
        if not isinstance(context, RefundBusinessContext) or not context.approval_id:
            raise TypeError("Trusted refund approval context is required")
        expected = {
            "application_id": context.application_id,
            "operation_id": context.operation_id,
            "user_id": context.user_id,
            "conversation_id": context.conversation_id,
            "thread_id": context.thread_id,
            "task_id": context.task_id,
            "workflow_id": context.workflow_id,
        }
        if any(args.subject.get(key) != value for key, value in expected.items()):
            return HandlerResult(
                rejection=BusinessRejection("approval_subject_mismatch", "Approval does not match.")
            )
        try:
            row = await approval_service.register_pending(
                approval_id=context.approval_id, subject=args.subject
            )
            return HandlerResult(
                data=ApprovalRegistrationData(
                    approval_id=str(row["approval_id"]), subject_digest=row["subject_digest"]
                )
            )
        except ApprovalError as error:
            return HandlerResult(
                rejection=BusinessRejection(error.code, "Approval cannot be registered.")
            )
        except (psycopg.Error, PoolClosed, PoolTimeout):
            raise ToolUnavailableError("Approval registration unavailable") from None

    async def close(args: CloseApplicationArgs, context):
        if not isinstance(context, RefundBusinessContext):
            raise TypeError("Trusted refund business context is required")
        try:
            result = await service.reject_application(context=context, reason_code=args.reason_code)
            return HandlerResult(data=ApplicationData.model_validate(result))
        except RefundRejected as error:
            return HandlerResult(
                rejection=BusinessRejection(error.code, "Refund cannot be closed.")
            )
        except (psycopg.Error, PoolClosed, PoolTimeout):
            raise ToolUnavailableError("Refund close unavailable") from None

    def definition(name, description, args, result, handler, *, read_only):
        return ToolDefinition(
            ToolMetadata(
                name=name,
                version="1",
                description=description,
                enabled=True,
                allowed_agents=frozenset({AgentType.REFUND}),
                required_scopes=frozenset({"refunds:request"}),
                risk_level="low",
                approval_required=False,
                read_only=read_only,
                has_business_side_effects=not read_only,
                idempotency="not_applicable" if read_only else "operation_id_required",
                timeout_seconds=timeout_seconds,
                max_retries=1 if read_only else 0,
                tags=frozenset({"refund", "node", "demo"}),
            ),
            args,
            result,
            handler,
        )

    return (
        definition(
            "check_refund_eligibility",
            "检查模拟退款资格",
            RefundOrderArgs,
            EligibilityData,
            eligibility,
            read_only=True,
        ),
        definition(
            "prepare_refund_application",
            "登记模拟退款申请",
            PrepareRefundArgs,
            ApplicationData,
            prepare,
            read_only=False,
        ),
        definition(
            "register_refund_approval",
            "登记模拟审批主体",
            ApprovalRegistrationArgs,
            ApprovalRegistrationData,
            register,
            read_only=False,
        ),
        definition(
            "close_refund_application",
            "关闭模拟退款申请",
            CloseApplicationArgs,
            ApplicationData,
            close,
            read_only=False,
        ),
    )
