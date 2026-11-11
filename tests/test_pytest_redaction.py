"""Exercise the real pytest output boundary with fictional database credentials."""

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("external", [False, True])
def test_failure_reports_redact_urls_kwargs_logs_and_output(tmp_path, external):
    password = "invented-PG-p@ssword"
    encoded = quote(password, safe="")
    test_url = f"postgresql://test:{encoded}@localhost/agent_demo_test"
    app_url = "postgresql://app:invented-app-password@localhost/agent_demo"
    probe = tmp_path / "test_external_probe.py"
    probe.write_text(
        "import logging, os, sys\n"
        "from psycopg.conninfo import conninfo_to_dict\n"
        "def test_connection():\n"
        "    url = os.environ['AGENT_TEST_DATABASE_URL']\n"
        "    kwargs = conninfo_to_dict(url)\n"
        "    logging.warning('connection %s %s', kwargs, os.environ['AGENT_DATABASE_URL'])\n"
        "    print('captured output', url, kwargs)\n"
        "    print('captured error', url, file=sys.stderr)\n"
        "    raise RuntimeError('connection failed: ' + str(kwargs))\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(AGENT_TEST_DATABASE_URL=test_url, AGENT_DATABASE_URL=app_url)
    args = [sys.executable, "-m", "pytest", "-c", str(ROOT / "pyproject.toml"), "-q"]
    if external:
        args.extend(["--showlocals", str(probe)])
    else:
        args.extend(["--showlocals", str(probe), str(ROOT / "tests/test_config.py")])
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert password not in output
    assert encoded not in output
    assert "invented-app-password" not in output
    assert test_url not in output and app_url not in output
    assert "[REDACTED]" in output
    assert "RuntimeError" in output and "test_external_probe.py" in output
    assert re.search(r"test_external_probe\.py:\d+", output)
    assert "Captured stdout" in output and "Captured stderr" in output and "Captured log" in output


def test_warning_summary_redacts_credentials_and_retains_location_and_category(tmp_path):
    password = "invented-warning-secret"
    url = f"postgresql://test:{password}@localhost/agent_demo_test"
    probe = tmp_path / "test_warning_probe.py"
    probe.write_text(
        "import logging, os, warnings\n"
        "def test_probe():\n"
        "    value = os.environ['AGENT_TEST_DATABASE_URL']\n"
        "    warnings.warn(value, UserWarning)\n"
        "    logging.warning(value)\n"
        "    raise RuntimeError('controlled probe')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-c", str(ROOT / "pyproject.toml"), "-q", str(probe)],
        cwd=ROOT,
        env={**os.environ, "AGENT_TEST_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert password not in output and url not in output
    assert "warnings summary" in output
    summary = output.split("warnings summary", maxsplit=1)[1]
    assert "UserWarning: [REDACTED]" in summary
    assert re.search(r"test_warning_probe\.py:\d+", summary)
    assert "RuntimeError: controlled probe" in output


@pytest.mark.parametrize("configuration", ["cli", "ini"])
def test_file_logging_is_rejected_before_test_execution(tmp_path, configuration):
    marker = tmp_path / "executed"
    log = tmp_path / "probe.log"
    probe = tmp_path / "test_file_probe.py"
    probe.write_text(
        f"from pathlib import Path\ndef test_probe():\n    Path({str(marker)!r}).touch()\n",
        encoding="utf-8",
    )
    setting = ["--log-file", str(log)] if configuration == "cli" else ["-o", f"log_file={log}"]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-c", str(ROOT / "pyproject.toml"), *setting, str(probe)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 4
    assert "file logging" in result.stderr
    assert not marker.exists() and not log.exists()


@pytest.mark.parametrize(
    "option",
    ["-s", "--capture=sys", "--capture=tee-sys", "--junitxml=result.xml", "--log-cli-level=INFO"],
)
def test_unsafe_output_modes_are_rejected(tmp_path, option):
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-c", str(ROOT / "pyproject.toml"), option],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 4
    assert "credential redaction" in result.stderr
