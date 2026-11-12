"""Opt-in tests against the explicitly configured dedicated test database."""

import os

import psycopg
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.domain.orders import MockOrderService, OrderNotAccessible, OrderRepository
from app.infrastructure.postgres import connection_kwargs, open_pool, validate_test_target
from scripts import run_async
from scripts.seed_orders import seed_orders


def test_real_order_constraints_isolation_and_seed_idempotence():
    raw = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Explicit AGENT_TEST_DATABASE_URL required")
    settings = Settings()
    url = SecretStr(raw)
    validate_test_target(url, settings.database_url)

    async def scenario():
        async with await psycopg.AsyncConnection.connect(**connection_kwargs(url)) as conn:
            assert await (
                await conn.execute("SELECT current_database(), current_user")
            ).fetchone() == ("agent_demo_test", "agent_test")
            versions = await (
                await conn.execute("SELECT version FROM schema_migrations ORDER BY version")
            ).fetchall()
            assert versions == [(1,), (2,), (3,)]
            columns = await (
                await conn.execute(
                    "SELECT numeric_precision, numeric_scale FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='demo_orders' "
                    "AND column_name='amount'"
                )
            ).fetchone()
            assert columns == (12, 2)
            with pytest.raises(psycopg.errors.CheckViolation):
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO demo_orders VALUES (%s,%s,%s,%s,%s,%s,now())",
                        ("stage03-constraint-probe", "dev-user", -1, "CNY", "unpaid", False),
                    )
        assert await seed_orders(url, target="test", settings=settings) == 0
        pool = await open_pool(Settings(_env_file=None, app_env="test", database_url=url))
        try:
            service = MockOrderService(OrderRepository(pool))
            first = await service.get_order(user_id="dev-user", order_id="demo-order-a-001")
            assert first.amount == "128.50" and first.simulated is True
            for order_id in ("demo-order-b-001", "absent-stage03"):
                with pytest.raises(OrderNotAccessible):
                    await service.get_order(user_id="dev-user", order_id=order_id)
            page = await service.list_orders(user_id="dev-user", limit=2, offset=0)
            assert [order.order_id for order in page] == ["demo-order-a-001", "demo-order-a-002"]
            assert await service.list_orders(user_id="dev-user", limit=5, offset=99) == []
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE demo_orders SET is_refunded=true WHERE order_id=%s AND owner_id=%s",
                    ("demo-order-a-001", "dev-user"),
                )
            try:
                assert await seed_orders(url, target="test", settings=settings) == 0
                assert (
                    await service.get_order(user_id="dev-user", order_id="demo-order-a-001")
                ).is_refunded
            finally:
                async with pool.connection() as conn:
                    await conn.execute(
                        "UPDATE demo_orders SET is_refunded=%s WHERE order_id=%s AND owner_id=%s",
                        (first.is_refunded, "demo-order-a-001", "dev-user"),
                    )
        finally:
            await pool.close()

    run_async(scenario())
