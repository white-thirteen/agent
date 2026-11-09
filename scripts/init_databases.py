"""Explicit, idempotent local bootstrap for two non-superuser database owners."""

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings

from app.core.config import Settings
from app.infrastructure.postgres import DatabaseUnavailableError, connection_kwargs


class BootstrapSettings(BaseSettings):
    """Admin credentials belong to this explicit command and never to Web Settings."""

    model_config = Settings.model_config
    database_admin_url: SecretStr | None = None
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT", ge=1, le=65535)


async def initialize_databases(
    admin_url: SecretStr,
    *,
    development_url: SecretStr,
    test_url: SecretStr,
) -> None:
    admin = conninfo_to_dict(admin_url.get_secret_value())
    targets = [
        (conninfo_to_dict(development_url.get_secret_value()), "agent_demo", "agent_app"),
        (conninfo_to_dict(test_url.get_secret_value()), "agent_demo_test", "agent_test"),
    ]
    port = str(BootstrapSettings().postgres_port)
    for info in [admin, *(item[0] for item in targets)]:
        if info.get("host") not in ("localhost", "127.0.0.1", "::1"):
            raise DatabaseUnavailableError("Bootstrap only accepts local Compose targets")
        if info.get("port", "5432") != port or info.get("hostaddr"):
            raise DatabaseUnavailableError("Bootstrap target differs from local Compose")
        if info.get("service"):
            raise DatabaseUnavailableError("Bootstrap service indirection is unsupported")
    for info, database, owner in targets:
        if info.get("dbname") != database or info.get("user") != owner or not info.get("password"):
            raise DatabaseUnavailableError("Bootstrap requires fixed database owners and passwords")
    if admin.get("user") in ("agent_app", "agent_test"):
        raise DatabaseUnavailableError("Bootstrap requires a separate administrative account")

    async with await psycopg.AsyncConnection.connect(
        **connection_kwargs(admin_url),
        autocommit=True,
    ) as connection:
        for info, database, owner in targets:
            cursor = await connection.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolcanlogin "
                "FROM pg_roles WHERE rolname = %s",
                (owner,),
            )
            role = await cursor.fetchone()
            if role is None:
                await connection.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}"
                    ).format(sql.Identifier(owner), sql.Literal(info["password"]))
                )
            elif role != (False, False, False, True):
                raise DatabaseUnavailableError("Existing application role privileges differ")
            cursor = await connection.execute(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s",
                (database,),
            )
            existing = await cursor.fetchone()
            if existing is None:
                await connection.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(database),
                        sql.Identifier(owner),
                    )
                )
            elif existing[0] != owner:
                raise DatabaseUnavailableError("Existing database owner differs")
    # Verify existing passwords without ever resetting them.
    for url in (development_url, test_url):
        async with await psycopg.AsyncConnection.connect(**connection_kwargs(url)) as connection:
            await connection.execute("SELECT 1")


async def main() -> int:
    try:
        settings = Settings()
        admin_url = BootstrapSettings().database_admin_url
        if not admin_url or not settings.database_url or not settings.test_database_url:
            raise DatabaseUnavailableError("Explicit admin/development/test URLs required")
        await initialize_databases(
            admin_url,
            development_url=settings.database_url,
            test_url=settings.test_database_url,
        )
        print("Local development and test databases initialized and connected.")
        return 0
    except (psycopg.Error, DatabaseUnavailableError, ValidationError) as error:
        print(f"Database initialization failed ({type(error).__name__}). Check local settings.")
        return 1


if __name__ == "__main__":
    from scripts import run_async

    raise SystemExit(run_async(main()))
