"""Configuration boundaries must fail without echoing secrets."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults_and_normalization():
    settings = Settings(_env_file=None, demo_user_ids=(" dev-user ", "", "dev-user", " 演示用户 "))
    assert settings.demo_user_ids == ("dev-user", "演示用户")
    assert not settings.model_configured


@pytest.mark.parametrize(
    "values",
    [
        {"model_base_url": "https://user:private-secret@example.com/v1"},
        {"model_base_url": "https://example.com:private-secret/v1"},
        {"database_url": "private-secret"},
        {"model_timeout_seconds": "private-secret"},
        {"database_pool_min_size": 6},
        {"demo_user_ids": ()},
        {"demo_user_ids": ("dev-user", "private-secret\x00probe")},
    ],
)
def test_settings_errors_hide_inputs(values):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert "private-secret" not in str(error.value)
