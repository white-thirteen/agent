"""CLI ownership regression; real Qwen/PG verification is explicit and opt-in."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.store.base import PutOp

from app.infrastructure.postgres import open_pool
from app.infrastructure.sessions import SessionRepository
from app.infrastructure.store import store_resources
from app.memory.manager import preference_namespace
from scripts import demo_session, run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints


def directory_bytes(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_existing_prepare_directory_never_enters_cleanup(tmp_path, monkeypatch):
    folder = tmp_path / "previous"
    folder.mkdir()
    for name in ("manifest.json", "protected.pickle", "operator-notes.txt"):
        (folder / name).write_bytes(b"previous invocation")
    before = directory_bytes(folder)
    monkeypatch.setattr(sys, "argv", ["demo", "prepare", "--folder", str(folder)])

    def unexpected_execution(coroutine):
        coroutine.close()
        pytest.fail("Existing directory must not run preparation or cleanup")

    monkeypatch.setattr(demo_session, "run_async", unexpected_execution)
    with pytest.raises(FileExistsError):
        demo_session.main()
    assert directory_bytes(folder) == before


def test_new_directory_partial_failure_keeps_owned_cleanup(tmp_path, monkeypatch):
    folder = tmp_path / "new"
    cleanup_calls = []

    async def failing_prepare(owned):
        assert owned == folder and owned.is_dir()
        (owned / "manifest.json").write_text("owned", "utf-8")
        (owned / "protected.pickle").write_bytes(b"owned baseline")
        raise RuntimeError("controlled partial preparation")

    async def inspect(owned, cleanup=False):
        assert owned == folder and cleanup is True
        cleanup_calls.append(owned)
        return {"protected_unchanged": True}

    # The actual CLI exception boundary runs; only external fixture work is controlled.
    monkeypatch.setattr(sys, "argv", ["demo", "prepare", "--folder", str(folder)])
    monkeypatch.setattr(demo_session, "prepare", failing_prepare)

    monkeypatch.setattr(demo_session, "inspect", inspect)
    with pytest.raises(RuntimeError, match="controlled partial preparation"):
        demo_session.main()
    assert cleanup_calls == [folder]
    assert json.loads((folder / "prepare-failure-cleanup.json").read_text("utf-8")) == {
        "protected_unchanged": True
    }


@pytest.mark.skipif(
    os.environ.get("AGENT_VERIFY_DEMO_QWEN") != "1",
    reason="Explicit real Qwen/PG demo preparation verification only",
)
def test_real_prepare_ownership_and_partial_publication_cleanup(tmp_path):
    """No paid Chat: real publication, repeat rejection, then injected post-PG failure."""
    output = Path(os.environ["AGENT_DEMO_FIX_EVIDENCE"])
    assert not output.exists()
    root = Path(__file__).resolve().parents[1]
    folder = tmp_path / ("demo631-fix-" + uuid4().hex)
    failed_folder = tmp_path / ("demo631-failed-" + uuid4().hex)
    dummy = {"user_a": "demo631-probe-" + uuid4().hex, "user_b": "demo631-probe-" + uuid4().hex}
    report = {"issue": "06-QA-001", "paid_chat_calls": 0}
    cleaned_folders = set()

    async def snapshot(data, associated=False):
        settings = demo_session.settings_for(data, embedding=False)
        pool = await open_pool(settings)
        try:
            if associated:
                await SessionRepository(pool).get_or_create(
                    user_id=data["user_a"], conversation_id=data["prefix"] + "-retained"
                )
                async with store_resources(settings) as store:
                    await store.abatch(
                        [
                            PutOp(
                                preference_namespace(data["user_a"]),
                                "profile",
                                {
                                    "schema_version": 1,
                                    "revision": 1,
                                    "preferences": {"answer_style": "concise"},
                                },
                            )
                        ]
                    )
            result = await database_snapshot(pool)
            async with pool.connection() as conn:
                orders = await (
                    await conn.execute(
                        "SELECT order_id FROM demo_orders WHERE owner_id=%s ORDER BY order_id",
                        (data["user_a"],),
                    )
                ).fetchall()
                chunks = await (
                    await conn.execute(
                        "SELECT chunk_id,vector_dims(embedding) FROM knowledge_chunks "
                        "WHERE document_id=%s",
                        (data.get("document_id", ""),),
                    )
                ).fetchall()
            return result, orders, chunks
        finally:
            await pool.close()

    baseline, _, _ = run_async(snapshot(dummy))
    report["protected_before"] = fingerprints(baseline)

    def cli(target, action="prepare", injection=None):
        command = [sys.executable]
        command += ["-c", injection] if injection else ["-m", "scripts.demo_session"]
        command += [action, "--folder", str(target)]
        return subprocess.run(command, cwd=root, capture_output=True, text=True)

    try:
        first = cli(folder)
        assert first.returncode == 0, "Real initial preparation failed"
        data = json.loads((folder / "manifest.json").read_text("utf-8"))
        prepared, orders, chunks = run_async(snapshot(data, associated=True))
        assert len(orders) == 2 and chunks and all(row[1] == 1024 for row in chunks)
        files_before = directory_bytes(folder)
        repeated = cli(folder)
        after_repeat, _, _ = run_async(snapshot(data))
        assert repeated.returncode != 0 and "FileExistsError" in repeated.stderr
        assert after_repeat == prepared
        assert directory_bytes(folder) == files_before
        report["repeat"] = {
            "exit": repeated.returncode,
            "file_exists_error": True,
            "all_public_unchanged": True,
            "all_directory_bytes_unchanged": True,
            "orders": orders,
            "chunks": chunks,
            "associated_session_and_profile_preserved": True,
        }
        cleaned = cli(folder, "cleanup")
        assert cleaned.returncode == 0
        cleaned_folders.add(folder)

        injection = (
            "from unittest.mock import patch\n"
            "from app.knowledge.repository import KnowledgeRepository\n"
            "from scripts.demo_session import main\n"
            "original = KnowledgeRepository.replace\n"
            "async def fail_after_publication(self, document, vectors):\n"
            "    await original(self, document, vectors)\n"
            "    raise RuntimeError('controlled_after_real_publication')\n"
            "with patch.object(KnowledgeRepository, 'replace', fail_after_publication):\n"
            "    main()\n"
        )
        failed = cli(failed_folder, injection=injection)
        assert failed.returncode != 0 and "controlled_after_real_publication" in failed.stderr
        cleanup = json.loads((failed_folder / "prepare-failure-cleanup.json").read_text("utf-8"))
        assert cleanup["protected_unchanged"] is True
        cleaned_folders.add(failed_folder)
        after_failure, _, _ = run_async(snapshot(dummy))
        assert after_failure == baseline
        report["current_call_failure"] = {
            "exit": failed.returncode,
            "injection": "after actual Qwen1024 publication committed, before manifest completion",
            "protected_unchanged": True,
        }
        report["result"] = "PASS"
    finally:
        # If an assertion interrupts either scenario, use only that invocation's manifest.
        for owned in (folder, failed_folder):
            if owned not in cleaned_folders and (owned / "protected.pickle").exists():
                result = cli(owned, "cleanup")
                assert result.returncode == 0, "Exact cleanup failed"
        final, _, _ = run_async(snapshot(dummy))
        report["protected_after"] = fingerprints(final)
        report["protected_unchanged"] = final == baseline
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        assert final == baseline
