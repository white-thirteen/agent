"""Validated read-only order tool adapters, with no access to execution policy state."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.agents.types import AgentType
from app.domain.orders import (
    MockOrderService,
    OrderNotAccessible,
    OrderReadTransientError,
    OrderReadUnavailableError,
    OrderView,
)
from app.tools.models import (
    BusinessRejection,
    HandlerResult,
    ToolDefinition,
    ToolMetadata,
    ToolTransientError,
    ToolUnavailableError,
)


class GetOrderArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)
    order_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^\x00]+$")]


class ListOrdersArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 5
    offset: Annotated[int, Field(strict=True, ge=0)] = 0


class GetOrderData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    order: OrderView


class ListOrdersData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    orders: list[OrderView]
    returned_count: int
    limit: int
    offset: int


def order_tools(service: MockOrderService, *, timeout_seconds: float, max_retries: int):
    async def get_order(args: GetOrderArgs, context):
        try:
            order = await service.get_order(user_id=context.user_id, order_id=args.order_id)
        except OrderNotAccessible:
            return HandlerResult(
                rejection=BusinessRejection("order_not_accessible", "Order is not accessible.")
            )
        except OrderReadTransientError:
            raise ToolTransientError("Order read unavailable") from None
        except OrderReadUnavailableError:
            raise ToolUnavailableError("Order read unavailable") from None
        return HandlerResult(data=GetOrderData(order=order))

    async def list_orders(args: ListOrdersArgs, context):
        try:
            orders = await service.list_orders(
                user_id=context.user_id, limit=args.limit, offset=args.offset
            )
        except OrderReadTransientError:
            raise ToolTransientError("Order read unavailable") from None
        except OrderReadUnavailableError:
            raise ToolUnavailableError("Order read unavailable") from None
        return HandlerResult(
            data=ListOrdersData(
                orders=orders, returned_count=len(orders), limit=args.limit, offset=args.offset
            )
        )

    def metadata(name, description, agents):
        return ToolMetadata(
            name=name,
            version="1",
            description=description,
            enabled=True,
            allowed_agents=frozenset(agents),
            required_scopes=frozenset({"orders:read"}),
            risk_level="low",
            approval_required=False,
            read_only=True,
            has_business_side_effects=False,
            idempotency="not_applicable",
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            tags=frozenset({"order", "read", "demo"}),
        )

    return (
        ToolDefinition(
            metadata(
                "get_order",
                "查询当前演示用户本人的一个模拟订单",
                {AgentType.ORDER, AgentType.REFUND},
            ),
            GetOrderArgs,
            GetOrderData,
            get_order,
        ),
        ToolDefinition(
            metadata("list_orders", "分页查询当前演示用户本人的模拟订单列表", {AgentType.ORDER}),
            ListOrdersArgs,
            ListOrdersData,
            list_orders,
        ),
    )
