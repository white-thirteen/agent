"""Owner-scoped simulated order facts and exact-money projection."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

import psycopg
from psycopg_pool import PoolClosed, PoolTimeout
from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True, slots=True)
class OrderRecord:
    order_id: str
    owner_id: str
    amount: Decimal
    currency: str
    payment_status: Literal["unpaid", "paid"]
    is_refunded: bool
    created_at: datetime


class OrderView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    order_id: str
    amount: str
    currency: str
    payment_status: Literal["unpaid", "paid"]
    is_refunded: bool
    created_at: str
    simulated: Literal[True] = True


class OrderNotAccessible(Exception):
    """The same rejection covers absent and other users' orders."""


class OrderReadTransientError(RuntimeError):
    """An order read failed transiently and may be retried by the caller."""


class OrderReadUnavailableError(RuntimeError):
    """An order read failed with a non-retryable data access error."""


class OrderRepository:
    def __init__(self, pool):
        self._pool = pool

    async def get_owned(self, *, owner_id: str, order_id: str) -> OrderRecord | None:
        rows = await self._query(
            "SELECT order_id, owner_id, amount, currency, payment_status, is_refunded, created_at "
            "FROM demo_orders WHERE owner_id=%s AND order_id=%s",
            (owner_id, order_id),
        )
        return OrderRecord(*rows[0]) if rows else None

    async def list_owned(self, *, owner_id: str, limit: int, offset: int) -> list[OrderRecord]:
        rows = await self._query(
            "SELECT order_id, owner_id, amount, currency, payment_status, is_refunded, created_at "
            "FROM demo_orders WHERE owner_id=%s ORDER BY created_at DESC, order_id DESC "
            "LIMIT %s OFFSET %s",
            (owner_id, limit, offset),
        )
        return [OrderRecord(*row) for row in rows]

    async def _query(self, sql, parameters):
        try:
            async with self._pool.connection() as connection:
                cursor = await connection.execute(sql, parameters)
                return await cursor.fetchall()
        except (
            psycopg.OperationalError,
            PoolTimeout,
            PoolClosed,
            psycopg.errors.SerializationFailure,
            psycopg.errors.DeadlockDetected,
        ):
            raise OrderReadTransientError("Order read unavailable") from None
        except psycopg.Error:
            raise OrderReadUnavailableError("Order read unavailable") from None


class MockOrderService:
    def __init__(self, repository: OrderRepository):
        self._repository = repository

    def _view(self, record: OrderRecord, user_id: str) -> OrderView:
        if record.owner_id != user_id:
            raise RuntimeError("Order ownership contract violated")
        if record.created_at.utcoffset() is None:
            raise RuntimeError("Order timestamp must be timezone-aware")
        return OrderView(
            order_id=record.order_id,
            amount=f"{record.amount:.2f}",
            currency=record.currency,
            payment_status=record.payment_status,
            is_refunded=record.is_refunded,
            created_at=record.created_at.isoformat(),
        )

    async def get_order(self, *, user_id: str, order_id: str) -> OrderView:
        record = await self._repository.get_owned(owner_id=user_id, order_id=order_id)
        if record is None:
            raise OrderNotAccessible()
        return self._view(record, user_id)

    async def list_orders(self, *, user_id: str, limit: int, offset: int) -> list[OrderView]:
        records = await self._repository.list_owned(owner_id=user_id, limit=limit, offset=offset)
        return [self._view(record, user_id) for record in records]
