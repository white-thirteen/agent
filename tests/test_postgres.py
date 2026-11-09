"""Opt-in real PostgreSQL tests. Only explicitly supplied test URLs are accepted."""

import asyncio
import os
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.postgres import (
    DatabaseUnavailableError,
    connection_kwargs,
    open_pool,
    validate_test_target,
)
from app.infrastructure.sessions import SessionRepository
from scripts import migrate, run_async


def test_wrong_test_target_is_rejected_before_connecting():
    with pytest.raises(DatabaseUnavailableError):
        validate_test_target(SecretStr("postgresql://app:unused@localhost/agent_demo"))
    with pytest.raises(DatabaseUnavailableError):
        validate_test_target(
            SecretStr("postgresql://app:unused@localhost/agent_demo_test"),
            SecretStr("postgresql://app:unused@127.0.0.1/agent_demo_test"),
        )


@pytest.fixture
def database_settings():
    url = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Explicit AGENT_TEST_DATABASE_URL required for real PostgreSQL")
    secret = SecretStr(url)
    validate_test_target(secret, Settings().database_url)
    return Settings(_env_file=None, database_url=secret, app_env="test")


def test_real_migrations_reentry_checksum_and_rollback(database_settings, tmp_path, monkeypatch):
    async def scenario():
        url = database_settings.database_url
        await migrate.apply_migrations(url, target="test")
        assert await migrate.apply_migrations(url, target="test") == []
        for path in migrate.MIGRATIONS_DIR.glob("*.sql"):
            (tmp_path / path.name).write_bytes(path.read_bytes())
        first = (tmp_path / "001_sessions.sql").read_bytes()
        failed_version = max(migrate.migration_files(tmp_path)) + 1
        probe = "migration_probe_" + uuid4().hex
        (tmp_path / f"{failed_version:03}_failed.sql").write_text(
            f"CREATE TABLE {probe} (value integer); SELECT missing_probe_column;", encoding="utf-8"
        )
        monkeypatch.setattr(migrate, "MIGRATIONS_DIR", tmp_path)
        with pytest.raises(psycopg.errors.UndefinedColumn):
            await migrate.apply_migrations(url, target="test")
        async with await psycopg.AsyncConnection.connect(**connection_kwargs(url)) as connection:
            cursor = await connection.execute("SELECT to_regclass(%s)", (probe,))
            assert (await cursor.fetchone())[0] is None
            cursor = await connection.execute(
                "SELECT count(*) FROM schema_migrations WHERE version=%s", (failed_version,)
            )
            assert (await cursor.fetchone())[0] == 0
        (tmp_path / "001_sessions.sql").write_bytes(first + b"\n-- changed\n")
        with pytest.raises(DatabaseUnavailableError, match="changed"):
            await migrate.apply_migrations(url, target="test")
        (tmp_path / "001_sessions.sql").unlink()
        with pytest.raises(DatabaseUnavailableError, match="Unknown"):
            await migrate.apply_migrations(url, target="test")

    run_async(scenario())


def test_real_session_concurrency_isolation_and_reopen(database_settings, monkeypatch):
    async def scenario():
        pool = await open_pool(database_settings)
        repository = SessionRepository(pool)
        user = "pg-test-" + uuid4().hex
        conversation = uuid4().hex
        try:
            # Fresh keys in each round exercise simultaneous first insertion.
            for _ in range(5):
                conversation = uuid4().hex
                bindings = await asyncio.gather(
                    *(
                        repository.get_or_create(user_id=user, conversation_id=conversation)
                        for _ in range(12)
                    )
                )
                assert len({binding.thread_id for binding in bindings}) == 1
            other = await repository.get_or_create(
                user_id=user + "-b", conversation_id=conversation
            )
            assert other.thread_id != bindings[0].thread_id
            import app.infrastructure.sessions as sessions_module

            with monkeypatch.context() as patch:
                patch.setattr(sessions_module, "uuid5", lambda *args: bindings[0].thread_id)
                with pytest.raises(psycopg.errors.UniqueViolation):
                    await repository.get_or_create(
                        user_id=user,
                        conversation_id="collision-" + conversation,
                    )
            assert (
                await repository.get(
                    user_id=user,
                    conversation_id="collision-" + conversation,
                )
                is None
            )
            assert (
                await repository.get(user_id=user + "-missing", conversation_id=conversation)
                is None
            )
            await pool.close()
            assert pool.closed
            pool = await open_pool(database_settings)
            saved = await SessionRepository(pool).get(user_id=user, conversation_id=conversation)
            assert saved == bindings[0]
        finally:
            if pool.closed:
                pool = await open_pool(database_settings)
            async with pool.connection() as connection:
                await connection.execute(
                    "DELETE FROM sessions WHERE user_id IN (%s, %s)", (user, user + "-b")
                )
            await pool.close()
            assert pool.closed

    run_async(scenario())
