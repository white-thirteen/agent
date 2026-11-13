"""Refund application preparation on isolated real PostgreSQL data."""

import os
from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.domain.refunds import (
    MockRefundService,
    OriginalRefundCall,
    RefundBusinessContext,
    RefundRejected,
)
from app.infrastructure.postgres import open_pool, validate_test_target
from scripts import run_async


def test_refund_preparation_is_scoped_idempotent_and_has_no_refund_effect():
    raw = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Explicit test database required")
    url = SecretStr(raw)
    validate_test_target(url, Settings().database_url)

    async def scenario():
        pool = await open_pool(Settings(_env_file=None, app_env="test", database_url=url))
        owner = "refund-prep-" + uuid4().hex
        order = owner
        thread = str(uuid4())
        call = OriginalRefundCall(
            "call", "refund_order", "1", {"order_id": order}, {"order_id": order}
        )
        ctx = RefundBusinessContext(
            owner,
            "task",
            "run",
            "conversation",
            thread,
            "task",
            str(uuid4()),
            str(uuid4()),
            None,
            call.call_digest(),
        )
        try:
            async with pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO sessions (user_id,conversation_id,thread_id) VALUES (%s,%s,%s)",
                    (owner, "conversation", thread),
                )
                await conn.execute(
                    "INSERT INTO demo_orders VALUES (%s,%s,42.50,'CNY','paid',false,now())",
                    (order, owner),
                )
            service = MockRefundService(pool)
            first = await service.prepare_application(context=ctx, original_call=call)
            assert first["status"] == "PENDING" and first["amount"] == "42.50"
            status = await service.get_application_status(
                user_id=owner, conversation_id="conversation", application_id=ctx.application_id
            )
            assert status["status"] == "PENDING" and status["simulated"] is True
            assert status["thread_id"] == thread and status["execution_result"] is None
            assert (
                await service.get_application_status(
                    user_id=owner + "-other",
                    conversation_id="conversation",
                    application_id=ctx.application_id,
                )
                is None
            )
            assert (
                await service.prepare_application(
                    context=replace(ctx, run_id="run2"), original_call=call
                )
                == first
            )
            with pytest.raises(RefundRejected):
                await service.prepare_application(
                    context=replace(ctx, user_id=owner + "-other"), original_call=call
                )
            async with pool.connection() as conn:
                assert await (
                    await conn.execute(
                        "SELECT is_refunded FROM demo_orders WHERE order_id=%s", (order,)
                    )
                ).fetchone() == (False,)
                assert await (
                    await conn.execute(
                        "SELECT count(*) FROM refund_requests WHERE user_id=%s", (owner,)
                    )
                ).fetchone() == (1,)
        finally:
            async with pool.connection() as conn:
                await conn.execute(
                    "DELETE FROM refund_requests WHERE user_id=%s AND application_id=%s",
                    (owner, ctx.application_id),
                )
                await conn.execute(
                    "DELETE FROM demo_orders WHERE owner_id=%s AND order_id=%s", (owner, order)
                )
                await conn.execute(
                    "DELETE FROM sessions WHERE user_id=%s AND conversation_id=%s",
                    (owner, "conversation"),
                )
            await pool.close()

    run_async(scenario())
