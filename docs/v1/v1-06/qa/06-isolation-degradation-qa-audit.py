"""Independent read-only semantic and online cleanup audit for Task6.2.2."""

import json
import subprocess
from pathlib import Path

from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints


def read(path):
    return json.loads(Path(path).read_text("utf-8"))


async def audit():
    evidence = read("docs/question/06-isolation-degradation-qa-real-evidence-20261114.json")
    reference = read("docs/06-state-events-full-regression-evidence-20261114-r2.json")
    assert evidence["probe_result"] == "PASS"
    assert evidence["protected_unchanged"] and evidence["protected_files_unchanged"]
    assert evidence["owned_server_stopped"]
    assert evidence["protected_before"] == evidence["protected_after"] == reference["protected_after"]
    assert evidence["tcp_disconnect"] == {
        "subscription_released_before_completion": True,
        "final_status": "completed",
        "old_tokens_replayed": False,
    }
    assert evidence["refund_then_memory_failure"] == {
        "order_refunded": True, "refund_status": "SUCCEEDED", "memory_status": "failed"
    }
    faults = {item["fault"]: item for item in evidence["degradation"]}
    assert set(faults) == {"embedding", "pg", "empty", "model"}
    for name, item in faults.items():
        assert not item["sources"]
        assert item["status"] == ("rejected" if name == "empty" else "failed")
        assert item["final_answer"] == (
            "现有知识证据不足或存在冲突，无法可靠回答。" if name == "empty" else None
        )
    for case in evidence["cases"]:
        events = case["events"]
        assert events[-1]["event"] == "done"
        assert sum(event["event"] == "done" for event in events) == 1
        if case["message"] == "knowledge":
            tokens = [event["data"]["content"] for event in events if event["event"] == "token"]
            assert tokens in ([], [faults["empty"]["final_answer"]])
        serialized = json.dumps(events, ensure_ascii=False)
        for private in ("private model", "private structured", "raw_args", "permission_scopes",
                        "checkpoint_ns", "api_key", "answer_language", "controlled Store"):
            assert private not in serialized
    command = (
        "@(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq "
        + str(evidence["pid"]) + " } | Select-Object ProcessId,Name) | ConvertTo-Json -Compress"
    )
    processes = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                               capture_output=True, text=True, check=True)
    assert processes.stdout.strip() in ("", "[]")
    original = Settings()
    validate_test_target(original.test_database_url, original.database_url)
    pool = await open_pool(original.model_copy(update={"database_url": original.test_database_url}))
    try:
        snapshot = fingerprints(await database_snapshot(pool))
        assert snapshot == evidence["protected_after"]
        async with pool.connection() as conn:
            identity = await (await conn.execute(
                "SELECT current_database(),current_user,current_setting('server_version')"
            )).fetchone()
            vector = await (await conn.execute(
                "SELECT extversion FROM pg_extension WHERE extname='vector'"
            )).fetchone()
    finally:
        await pool.close()
    targeted = read("docs/06-isolation-degradation-targeted-evidence-20261114.json")
    assert targeted["exit_code"] == 0 and len(targeted["results"]) == 99
    assert all(item["outcome"] == "passed" for item in targeted["results"])
    output = {"result": "PASS", "identity": list(identity), "pgvector": vector[0],
              "recorded_probe_pid_absent": True, "public_matches_qa_start_and_612_final": True,
              "protected_after": snapshot, "public_events_checked": True,
              "implementation_targeted_results_checked": 99,
              "migration_check": "all local and registered checksums asserted by database_snapshot",
              "connection_count": "not measured by application_name; no attribution claimed"}
    Path("docs/question/06-isolation-degradation-qa-final-audit-20261114.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), "utf-8")
    print("QA622_AUDIT_PASS")


if __name__ == "__main__":
    run_async(audit())
