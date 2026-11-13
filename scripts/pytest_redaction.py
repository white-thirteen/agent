"""Redact configured PostgreSQL credentials from pytest's captured reports."""

import linecache
import os
import warnings
from urllib.parse import quote, quote_plus

import pytest
from dotenv import dotenv_values
from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict

from app.core.config import PROJECT_ROOT

_DATABASE_KEYS = ("AGENT_DATABASE_URL", "AGENT_TEST_DATABASE_URL")
_REDACTED = "[REDACTED]"


def _configured_secrets() -> tuple[str, ...]:
    """Include both dotenv and environment values, even when one overrides the other."""
    dotenv = dotenv_values(PROJECT_ROOT / ".env")
    secrets = set()
    for source in (dotenv, os.environ):
        for key in _DATABASE_KEYS:
            url = source.get(key)
            if not url:
                continue
            secrets.add(url)
            try:
                password = conninfo_to_dict(url).get("password")
            except ProgrammingError:
                continue
            if password:
                secrets.update((password, quote(password, safe=""), quote_plus(password)))
                secrets.add(repr(password)[1:-1])
                secrets.add(ascii(password)[1:-1])
    return tuple(sorted(secrets, key=len, reverse=True))


def _redact(value: str) -> str:
    for secret in _configured_secrets():
        value = value.replace(secret, _REDACTED)
    return value


def _redact_longrepr(value):
    if isinstance(value, tuple):
        return tuple(_redact(item) if isinstance(item, str) else item for item in value)
    return _redact(str(value))


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    # Live output and file reporters bypass the captured terminal report boundary.
    if config.getoption("capture") != "fd":
        raise pytest.UsageError("Use pytest capture=fd for credential redaction")
    if (
        config.getoption("xmlpath", default=None)
        or config.getini("log_cli")
        or config.getoption("log_cli_level", default=None)
        or config.getoption("log_file", default=None)
        or config.getini("log_file")
    ):
        raise pytest.UsageError(
            "JUnit XML, live logging and file logging are unsupported by credential redaction"
        )


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.longrepr is not None:
        report.longrepr = _redact_longrepr(report.longrepr)
    report.sections[:] = [(name, _redact(content)) for name, content in report.sections]


@pytest.hookimpl(tryfirst=True)
def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.longrepr is not None:
        report.longrepr = _redact_longrepr(report.longrepr)
    report.sections[:] = [(name, _redact(content)) for name, content in report.sections]


@pytest.hookimpl(tryfirst=True)
def pytest_warning_recorded(warning_message: warnings.WarningMessage) -> None:
    # The terminal warnings summary formats the warning independently of test reports.
    message = str(warning_message.message)
    redacted = _redact(message)
    if redacted != message:
        warning_message.message = Warning(redacted)
    source = warning_message.line or linecache.getline(
        warning_message.filename, warning_message.lineno
    )
    if source:
        warning_message.line = _redact(source)
