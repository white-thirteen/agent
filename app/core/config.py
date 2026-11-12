"""Environment settings, with secrets excluded from normal representations."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "Agent Engine Demo"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    model_name: str | None = None
    model_base_url: str | None = None
    model_api_key: SecretStr | None = None
    database_url: SecretStr | None = None
    test_database_url: SecretStr | None = None
    database_pool_min_size: int = Field(default=1, ge=1)
    database_pool_max_size: int = Field(default=5, ge=1)
    database_connect_timeout_seconds: float = Field(default=5, gt=0, allow_inf_nan=False)
    database_startup_timeout_seconds: float = Field(default=10, gt=0, allow_inf_nan=False)
    model_timeout_seconds: float = Field(default=30, gt=0, allow_inf_nan=False)
    model_max_attempts: int = Field(default=8, gt=0)
    model_max_retries: int = Field(default=1, ge=0)
    run_timeout_seconds: float = Field(default=120, gt=0, allow_inf_nan=False)
    run_max_tool_calls: int = Field(default=12, gt=0)
    tool_timeout_seconds: float = Field(default=5, gt=0, allow_inf_nan=False)
    tool_read_max_retries: int = Field(default=1, ge=0, le=1)
    tool_max_calls_per_message: int = Field(default=4, gt=0)
    runtime_queue_capacity: int = Field(default=64, ge=2)
    runtime_max_active_runs: int = Field(default=8, gt=0)
    runtime_retained_runs: int = Field(default=100, gt=0)
    runtime_result_ttl_seconds: float = Field(default=1800, gt=0, allow_inf_nan=False)
    runtime_shutdown_grace_seconds: float = Field(default=5, ge=0, allow_inf_nan=False)
    demo_user_ids: tuple[str, ...] = ("dev-user", "demo-user-b")

    @field_validator("model_base_url")
    @classmethod
    def validate_model_url(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                url = urlsplit(value)
                _ = url.port
            except ValueError:
                raise ValueError("Invalid model URL") from None
            if (
                url.scheme not in ("http", "https")
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
            ):
                raise ValueError("Model URL must be HTTP(S) without credentials or query")
        return value

    @field_validator("database_url", "test_database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            from psycopg import ProgrammingError
            from psycopg.conninfo import conninfo_to_dict

            try:
                info = conninfo_to_dict(value.get_secret_value())
            except ProgrammingError:
                raise ValueError("Invalid PostgreSQL connection settings") from None
            if not info.get("host") or not info.get("dbname") or not info.get("user"):
                raise ValueError("Database host, dbname and user are required")
        return value

    @field_validator("demo_user_ids")
    @classmethod
    def normalize_users(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        users = tuple(dict.fromkeys(user.strip() for user in value if user.strip()))
        if not users or any(len(user) > 128 for user in users):
            raise ValueError("Demo users must contain identifiers of length 1–128")
        if any("\x00" in user for user in users):
            raise ValueError("Demo user identifiers must not contain NUL")
        return users

    @model_validator(mode="after")
    def validate_pool_sizes(self) -> "Settings":
        if self.database_pool_min_size > self.database_pool_max_size:
            raise ValueError("Database pool minimum exceeds maximum")
        return self

    @property
    def model_configured(self) -> bool:
        return bool(
            self.model_name
            and self.model_name.strip()
            and self.model_api_key
            and self.model_api_key.get_secret_value().strip()
        )
