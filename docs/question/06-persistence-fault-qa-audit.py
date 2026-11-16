"""Read-only independent audit after the Task6.2.1 process probe completes."""

import json
import subprocess
from pathlib import Path

from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints


def read(name):
    return json.loads(Path(name).read_text("utf-8"))


async def audit():
    evidence = read("docs/question/06-persistence-fault-qa-real-evidence-20261114.json")
    assert evidence["result"] == "PASS"
    assert evidence["protected_files_before"] == evidence["protected_files_after"]
    reference = read("docs/06-state-events-full-regression-evidence-20261114-r2.json")
    summaries = []
    pids = []
    for case in evidence["cases"]:
        assert case["result"] == "PASS" and case["all_public_rows_columns_unchanged"]
        assert case["protected_before"] == reference["protected_after"]
        observations = {o["label"]: o for o in case["observations"]}
        waiting = observations["waiting"]
        final = observations["end_read_only"]
        assert final["fixed"] == waiting["fixed"]
        assert final["fixed"]["task_id"] == final["fixed"]["workflow_id"]
        assert final["approval"]["approver_id"] == "local-demo-approval"
        assert final["successful_applications"] == 1 and final["order_refunded"]
        assert final["paired_messages"] == [{
            "id": "tool:" + final["fixed"]["task_id"] + ":" + final["fixed"]["call_id"],
            "call": final["fixed"]["call_id"],
        }]
        if case["mode"] == "normal":
            assert not final["runs"] and not final["invocations"] and not final["writes"]
            assert sorted(r["status"] for r in case["concurrent_resume"]) == [202, 409]
            assert observations["first_resume"]["invocations"][0]["input"] == "Command"
        else:
            failed = observations["first_resume"]
            recovered = observations["reconciled"]
            assert failed["business_status"] == "SUCCEEDED" and failed["next"] == ["execute_refund"]
            assert len(failed["writes"]) == 1 and not recovered["writes"]
            assert all(i["input"] == "None" for i in recovered["invocations"])
            assert any(n["node"] == "execute_refund" and n["recovery"] == "succeeded" for n in recovered["nodes"])
        for proc in case["processes"]:
            assert proc["exit_confirmed"] and proc["exit_code"] is not None
            assert proc["server_pid"] != proc["pid"]
            pids.extend((proc["pid"], proc["server_pid"]))
        summaries.append({"mode": case["mode"], "processes": len(case["processes"]),
                          "all_public_unchanged": True, "original_call_preserved": True})
    # Query only the recorded launchers and service processes, without exposing commands.
    command = "$ids=@(" + ",".join(map(str, pids)) + "); @(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in $ids } | Select-Object ProcessId,Name) | ConvertTo-Json -Compress"
    process_result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                    capture_output=True, text=True, check=True)
    assert process_result.stdout.strip() in ("", "[]"), "recorded_process_still_present"
    original = Settings()
    validate_test_target(original.test_database_url, original.database_url)
    settings = original.model_copy(update={"database_url": original.test_database_url})
    pool = await open_pool(settings)
    try:
        snapshot = fingerprints(await database_snapshot(pool))
        assert snapshot == reference["protected_after"]
        assert snapshot == evidence["cases"][0]["protected_before"]
        async with pool.connection() as conn:
            identity = await (await conn.execute("SELECT current_database(),current_user,current_setting('server_version')")).fetchone()
            vector = await (await conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")).fetchone()
    finally:
        await pool.close()
    result = {"result": "PASS", "cases": summaries, "recorded_process_count": len(pids),
              "recorded_processes_absent": True, "identity": list(identity), "pgvector": vector[0],
              "all_public_matches_612_final_and_qa_start": True,
              "migration_identity_check": "database_snapshot asserts full registered/local checksum equality and test identity",
              "protected_after": snapshot}
    Path("docs/question/06-persistence-fault-qa-final-audit-20261114.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print("QA621_AUDIT_PASS")


if __name__ == "__main__":
    run_async(audit())
