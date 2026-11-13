"""Explicit idempotent seed of five simulated orders in the selected Demo database."""

import argparse
from datetime import UTC, datetime
from decimal import Decimal

import psycopg
from psycopg.conninfo import conninfo_to_dict
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.postgres import (
    EXPECTED_SCHEMA_VERSION,
    DatabaseUnavailableError,
    connection_kwargs,
    validate_test_target,
)

SAMPLES = (
    (
        "demo-order-a-001",
        "dev-user",
        Decimal("128.50"),
        "CNY",
        "paid",
        False,
        datetime(2026, 1, 5, tzinfo=UTC),
    ),
    (
        "demo-order-a-002",
        "dev-user",
        Decimal("59.90"),
        "CNY",
        "unpaid",
        False,
        datetime(2026, 1, 4, tzinfo=UTC),
    ),
    (
        "demo-order-a-003",
        "dev-user",
        Decimal("35.00"),
        "CNY",
        "paid",
        True,
        datetime(2026, 1, 3, tzinfo=UTC),
    ),
    (
        "demo-order-b-001",
        "demo-user-b",
        Decimal("888.00"),
        "CNY",
        "paid",
        False,
        datetime(2026, 1, 2, tzinfo=UTC),
    ),
    (
        "demo-order-b-002",
        "demo-user-b",
        Decimal("30.00"),
        "CNY",
        "unpaid",
        False,
        datetime(2026, 1, 1, tzinfo=UTC),
    ),
)


async def seed_orders(url, *, target: str, settings: Settings) -> int:
    info = conninfo_to_dict(url.get_secret_value())
    # Explicitly limited to the previously approved local/VM demo installation.
    if info.get("host") not in ("localhost", "127.0.0.1", "::1", "192.168.150.101"):
        raise DatabaseUnavailableError("Seed target is not the approved demo host")
    if target == "test":
        validate_test_target(url, settings.database_url)
        expected = ("agent_demo_test", "agent_test")
    elif target == "development" and settings.app_env != "production":
        expected = ("agent_demo", "agent_app")
    else:
        raise DatabaseUnavailableError("Invalid seed target")
    if not {"dev-user", "demo-user-b"} <= set(settings.demo_user_ids):
        raise DatabaseUnavailableError("Seed owners must belong to the demo user list")
    async with await psycopg.AsyncConnection.connect(**connection_kwargs(url)) as conn:
        if (
            await (await conn.execute("SELECT current_database(), current_user")).fetchone()
            != expected
        ):
            raise DatabaseUnavailableError("Seed database identity mismatch")
        versions = await (
            await conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        ).fetchall()
        if versions != [(version,) for version in range(1, EXPECTED_SCHEMA_VERSION + 1)]:
            raise DatabaseUnavailableError("Seed requires the expected schema")
        inserted = 0
        for sample in SAMPLES:
            cursor = await conn.execute(
                "INSERT INTO demo_orders "
                "(order_id,owner_id,amount,currency,payment_status,is_refunded,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(order_id) DO NOTHING",
                sample,
            )
            inserted += cursor.rowcount
            cursor = await conn.execute(
                "SELECT owner_id,amount,currency,created_at FROM demo_orders WHERE order_id=%s",
                (sample[0],),
            )
            if await cursor.fetchone() != (sample[1], sample[2], sample[3], sample[6]):
                raise DatabaseUnavailableError("Existing seed facts conflict")
        return inserted


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("development", "test"), required=True)
    args = parser.parse_args()
    try:
        settings = Settings()
        url = settings.database_url if args.target == "development" else settings.test_database_url
        if url is None:
            raise DatabaseUnavailableError("Explicit database URL required")
        count = await seed_orders(url, target=args.target, settings=settings)
        print(f"Seed complete. Inserted {count} simulated orders.")
        return 0
    except (psycopg.Error, DatabaseUnavailableError, ValidationError) as error:
        print(f"Seed failed ({type(error).__name__}). Check target and existing facts.")
        return 1


if __name__ == "__main__":
    from scripts import run_async

    raise SystemExit(run_async(main()))
