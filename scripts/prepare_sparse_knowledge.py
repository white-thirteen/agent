"""Explicit maintenance-window sparse backfill, activation or readiness check."""

import argparse

from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from app.knowledge.sparse import activate, backfill, check_sparse_ready
from scripts import run_async


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=["development", "test"])
    parser.add_argument("action", choices=["backfill", "activate", "check"])
    args = parser.parse_args()
    settings = Settings()
    if args.action != "check" and settings.app_env not in ("development", "test"):
        raise ValueError("Sparse maintenance requires development or test environment")
    if args.target == "test":
        if settings.test_database_url is None:
            raise ValueError("Test database URL required")
        validate_test_target(settings.test_database_url, settings.database_url)
        settings = settings.model_copy(update={"database_url": settings.test_database_url})
    pool = await open_pool(settings)
    try:
        if args.action == "backfill":
            print(f"Derived inputs updated: {await backfill(pool)}")
        elif args.action == "activate":
            print(f"Sparse index activated at watermark {await activate(pool)}")
        else:
            async with pool.connection() as connection, connection.transaction():
                await connection.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                print(f"Sparse index ready at watermark {await check_sparse_ready(connection)}")
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(run_async(main()))
