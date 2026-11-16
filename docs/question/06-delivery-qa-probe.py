"""Independent Task632 read-only environment, evidence and PG audit."""

import asyncio
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from app.main import create_app
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    report = {"python": platform.python_version(), "executable": sys.executable,
              "prefix": sys.prefix, "base_prefix": sys.base_prefix, "sys_path": sys.path,
              "pyvenv_cfg": (Path(sys.prefix) / "pyvenv.cfg").read_text()}
    assert report["python"] == "3.13.7"
    assert "include-system-site-packages = false" in report["pyvenv_cfg"]
    assert not any(".venv/" in p.replace("\\", "/") for p in sys.path)
    locked = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$", (ROOT / "requirements.txt").read_text(), re.M))
    report["lock_mismatches"] = {name: importlib.metadata.version(name) for name, version in locked.items() if importlib.metadata.version(name) != version}
    report["locked_count"] = len(locked)
    assert len(locked) == 90 and not report["lock_mismatches"]
    report["commands"] = []
    for args in (["-m", "pip", "check"], ["-m", "pytest", "-q", "tests/test_config.py", "tests/test_resources.py"], ["-m", "ruff", "check", "app", "scripts", "tests"], ["-m", "ruff", "format", "--check", "app", "scripts", "tests"]):
        result = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
        report["commands"].append({"args": args, "exit_code": result.returncode, "output": result.stdout + result.stderr})
        assert result.returncode == 0
    evidence_names = ["06-delivery-install-evidence-20261115.json", "06-delivery-clean-gate-evidence-20261115.json", "06-delivery-qwen-regression-evidence-20261115.json", "06-delivery-fresh-database-evidence-20261115.json", "06-database-reproduction-evidence-20261115-r2.json", "06-database-reproduction-cleanup-evidence-20261115.json"]
    report["reviewed_evidence_sha256"] = {name: digest(ROOT / "docs" / name) for name in evidence_names}
    gate = json.loads((ROOT / "docs" / evidence_names[1]).read_text())
    assert gate["pytest_outcomes"] == {"passed": 228, "failed": 0, "skipped": 0}
    assert gate["real_qwen_enabled"] and gate["protected_unchanged"]
    original = Settings()
    validate_test_target(original.test_database_url, original.database_url)
    settings = original.model_copy(update={"app_env": "test", "database_url": original.test_database_url, "embedding_enabled": False, "log_level": "CRITICAL"})
    pool = await open_pool(settings)
    try:
        before = await database_snapshot(pool)
        report["protected_before"] = fingerprints(before)
        report["same_as_full_gate_after"] = fingerprints(before) == gate["protected_after"]
        assert report["same_as_full_gate_after"]
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            report["live_status"] = {k: getattr(app.state, k) for k in ("database_status", "checkpoint_status", "store_status", "embedding_status", "model_status")}
            assert app.state.agent_service.is_ready
            assert app.state.embedding_status == "disabled"
        report["app_pools_closed"] = app.state.pool.closed and app.state.checkpoint_pool.closed
        assert report["app_pools_closed"]
        after = await database_snapshot(pool)
        report["protected_after"] = fingerprints(after)
        assert before == after
        report["protected_unchanged"] = True
    finally:
        await pool.close()
    report["audit_pool_closed"] = pool.closed
    report["remaining_async_tasks"] = [t.get_name() for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    assert not report["remaining_async_tasks"]
    files = [ROOT / name for name in ("README.md", ".env.example", "docs/06-delivery-report.md", "docs/final-acceptance.md", "docs/06-integration-handoff.md", "docs/database-reproduction.md", "docs/demo-walkthrough.md", "deploy/postgres-vector.Dockerfile", "scripts/verify_06_delivery.py")]
    files += [ROOT / "docs" / name for name in evidence_names]
    from psycopg.conninfo import conninfo_to_dict
    secrets = [original.model_api_key.get_secret_value()]
    for url in (original.database_url, original.test_database_url):
        secrets.extend([url.get_secret_value(), conninfo_to_dict(url.get_secret_value())["password"]])
    report["credential_leak_files"] = [str(p.relative_to(ROOT)) for p in files if any(secret and secret in p.read_text("utf-8") for secret in secrets)]
    assert not report["credential_leak_files"]
    report["result"] = "PASS"
    destination = ROOT / "docs/question/06-delivery-qa-evidence-20261115.json"
    assert not destination.exists()
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"result": "PASS", "locked_count": len(locked), "test_output": report["commands"][1]["output"], "live_status": report["live_status"], "protected_unchanged": True}, ensure_ascii=False))


if __name__ == "__main__":
    run_async(main())
