"""Independent Task631 checks; only UUID-owned demo data, never imported snapshots."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from scripts import run_async
from scripts.demo_session import settings_for
from app.infrastructure.postgres import open_pool
from scripts.verify_05_memory_manage import database_snapshot, fingerprints

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/question/06-demo-qa-reprepare-evidence.json"


async def snapshot(data):
    pool = await open_pool(settings_for(data, embedding=False))
    try:
        snap = await database_snapshot(pool)
        async with pool.connection() as conn:
            orders = await (await conn.execute(
                "SELECT order_id FROM demo_orders WHERE owner_id=%s ORDER BY order_id",
                (data["user_a"],),
            )).fetchall()
            chunks = await (await conn.execute(
                "SELECT document_version,chunk_id,vector_dims(embedding) "
                "FROM knowledge_chunks WHERE document_id=%s",
                (data["document_id"],),
            )).fetchall()
        return {"public": fingerprints(snap), "orders": orders, "chunks": chunks}
    finally:
        await pool.close()


def main():
    assert not OUT.exists()
    folder = Path(tempfile.gettempdir()) / ("demo631-qa-" + uuid4().hex)
    cmd = [sys.executable, "-m", "scripts.demo_session", "prepare", "--folder", str(folder)]
    report = {"folder": str(folder), "commands": []}
    try:
        first = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        report["commands"].append({"action": "first prepare", "exit": first.returncode})
        assert first.returncode == 0, "First prepare failed; inspect local captured stderr"
        data = json.loads((folder / "manifest.json").read_text("utf-8"))
        report["prepared"] = run_async(snapshot(data))
        assert len(report["prepared"]["orders"]) == 2
        assert report["prepared"]["chunks"] and all(r[2] == 1024 for r in report["prepared"]["chunks"])
        repeated = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        report["commands"].append({"action": "same-folder prepare", "exit": repeated.returncode,
                                   "file_exists_error": "FileExistsError" in repeated.stderr})
        report["after_repeated_prepare"] = run_async(snapshot(data))
        report["previous_data_deleted"] = not report["after_repeated_prepare"]["orders"] and not report["after_repeated_prepare"]["chunks"]
        report["failure_cleanup_created"] = (folder / "prepare-failure-cleanup.json").exists()
        assert repeated.returncode != 0 and report["previous_data_deleted"]
        report["result"] = "REPRODUCED_06-QA-001"
    finally:
        if (folder / "protected.pickle").exists():
            cleanup = subprocess.run([sys.executable, "-m", "scripts.demo_session", "cleanup", "--folder", str(folder), "--output", str(folder / "qa-final-cleanup.json")], cwd=ROOT, capture_output=True, text=True)
            report["cleanup_exit"] = cleanup.returncode
            if cleanup.returncode == 0:
                clean = json.loads((folder / "qa-final-cleanup.json").read_text("utf-8"))
                report["protected_after"] = clean["protected_after"]
                report["protected_unchanged"] = clean["protected_unchanged"]
        OUT.write_text(json.dumps(report, ensure_ascii=False, default=str, indent=2), "utf-8")
    print(report["result"], report["protected_unchanged"])


if __name__ == "__main__":
    main()
