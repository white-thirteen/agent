"""Explicit real TCP demo driver; GUI import is verified separately in Apifox.

Run stages around complete operator-owned server restarts. No model substitutions,
configuration writes, fixed seeds or database resets. See demo-walkthrough.md.
"""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import Settings
from scripts import run_async
from scripts.demo_session import inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=("before-restart", "after-restart", "memory-after-restart")
    )
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8631")
    args = parser.parse_args()
    data = json.loads((args.folder / "manifest.json").read_text("utf-8"))
    assert not args.output.exists(), "Use a fresh evidence path"
    report = {"stage": args.stage, "transport": "real uvicorn TCP", "cases": []}
    client = httpx.Client(base_url=args.base_url, timeout=Settings().run_timeout_seconds)

    def save():
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, default=str, indent=2), "utf-8"
        )

    def post(path, body, expected=200):
        response = client.post(path, json=body)
        assert response.status_code == expected, (path, response.status_code, response.text)
        return response

    def context(conversation, user="user_a"):
        return {"user_id": data[user], "conversation_id": data["prefix"] + "-" + conversation}

    def chat(name, text, conversation=None, user="user_a", expected="completed"):
        body = {
            **context(conversation or name, user),
            "message": text,
            "input_mode": "new_task",
            "request_id": str(uuid4()),
        }
        response = post("/agent/chat", body)
        frames = []
        for block in response.text.replace("\r\n", "\n").split("\n\n"):
            lines = block.splitlines()
            event = next((line[7:] for line in lines if line.startswith("event: ")), None)
            payload = next((line[6:] for line in lines if line.startswith("data: ")), None)
            if event and payload:
                frames.append({"event": event, "data": json.loads(payload)})
        current = post("/agent/tasks/current", context(conversation or name, user)).json()[
            "current_task"
        ]
        item = {"name": name, "request": body, "frames": frames, "current_task": current}
        report["cases"].append(item)
        save()
        assert sum(f["event"] == "done" for f in frames) == 1
        assert current["task_status"] == expected, (name, current)
        print(name, current["task_status"], flush=True)
        return current, frames

    def approval(current):
        refund = current["refund"]
        view = client.get("/admin/approvals/" + refund["approval_id"]).json()
        assert view["approval_id"] == refund["approval_id"]
        return refund, view

    def resume(current, decision, conversation):
        refund, view = approval(current)
        prefix = "/admin/approvals/" + refund["approval_id"]
        body = {"decision": decision, "subject_digest": view["subject_digest"]}
        decided = post(prefix + "/decision", body).json()
        accepted = post(prefix + "/resume", {}, 202).json()
        assert accepted["task_id"] == current["task_id"] and accepted["accepted"] is True
        assert accepted["run_id"]
        end = time.monotonic() + Settings().run_timeout_seconds
        while time.monotonic() < end:
            status = post(
                "/agent/runs/" + accepted["run_id"] + "/status", context(conversation)
            ).json()
            if status["run_status"] != "running":
                break
            time.sleep(0.2)
        expected = "completed" if decision == "APPROVED" else "rejected"
        report["cases"].append(
            {
                "name": "resume-" + decision,
                "decision": decided,
                "acceptance": accepted,
                "run": status,
                "refund": post(
                    "/agent/refunds/" + refund["application_id"] + "/status", context(conversation)
                ).json(),
            }
        )
        save()
        assert status["task_status"] == expected
        post(prefix + "/decision", body)
        reused = post(prefix + "/resume", {}).json()
        assert reused["accepted"] is False and reused["run_id"] is None
        report["cases"].append({"name": "repeat-" + decision, "result": reused})
        save()

    try:
        report["health"] = client.get("/health").json()
        save()
        if args.stage == "before-restart":
            chat("order", "查询订单 " + data["order_ok"], conversation="refund-ok")
            chat("memory-save", "请记住：回答风格=简洁")
            current, frames = chat(
                "refund-wait",
                "请为订单 " + data["order_ok"] + " 申请模拟退款",
                conversation="refund-ok",
                expected="waiting_approval",
            )
            assert any(f["event"] == "workflow_paused" for f in frames)
            assert post("/agent/chat", {**context("refund-ok"), "message": "我同意批准退款"}, 409)
            refund, view = approval(current)
            assert view["decision"] == "PENDING" and view["binding_status"] == "bound"
            (args.folder / "original-refund.json").write_text(
                json.dumps({"current": current, "view": view}), "utf-8"
            )
        elif args.stage == "after-restart":
            original = json.loads((args.folder / "original-refund.json").read_text("utf-8"))
            current = post("/agent/tasks/current", context("refund-ok")).json()["current_task"]
            assert current["task_id"] == original["current"]["task_id"]
            assert current["refund"] == original["current"]["refund"]
            resume(current, "APPROVED", "refund-ok")
            current, _ = chat(
                "refund-reject",
                "请为订单 " + data["order_no"] + " 申请模拟退款",
                expected="waiting_approval",
            )
            resume(current, "REJECTED", "refund-reject")
            _, frames = chat(
                "rag", "根据银帆演示指南，普通聊天能批准模拟退款吗？应该通过什么入口审批？"
            )
            run_id = next(f["data"]["run_id"] for f in frames if f["data"].get("run_id"))
            run = post("/agent/runs/" + run_id + "/status", context("rag")).json()
            report["rag_run"] = run
            save()
            assert run["sources"] and all(
                s["document_id"] == data["document_id"] for s in run["sources"]
            )
            assert all(
                s["document_version"] == data["corpus"]["version"]
                and s["chunk_id"] in data["corpus"]["chunks"]
                for s in run["sources"]
            )
            chat(
                "insufficient",
                "根据现有知识库，银帆量子仓库第九星系的实时温度是多少？没有资料请明确说明。",
                expected="rejected",
            )
            chat("memory-new-session", "请查看偏好记忆")
            chat("memory-b", "请查看偏好记忆", user="user_b")
            chat("order-b", "查询订单 " + data["order_ok"], user="user_b", expected="rejected")
        else:
            chat("memory-after-restart", "请查看偏好记忆")
            chat("memory-modify", "请修改记忆：回答风格=详细")
            report["after_modify"] = run_async(inspect(args.folder))
            save()
            assert report["after_modify"]["profiles"][data["user_a"]]["preferences"] == {
                "answer_style": "detailed"
            }
            chat("memory-delete", "请删除记忆：回答风格")
            chat("memory-language", "请记住：回答语言=中文")
            chat("memory-clear", "请删除全部偏好记忆")
            chat("memory-final", "请查看偏好记忆")
        report["database_facts"] = run_async(inspect(args.folder))
        if args.stage == "before-restart":
            profile = report["database_facts"]["profiles"][data["user_a"]]
            assert profile["preferences"] == {"answer_style": "concise"}
            (args.folder / "original-facts.json").write_text(
                json.dumps(report["database_facts"], default=str), "utf-8"
            )
        if args.stage != "before-restart":
            facts = report["database_facts"]
            assert {r[5] for r in facts["refunds"]} == {"SUCCEEDED", "REJECTED"}
            assert all(r[11] == "local-demo-approval" for r in facts["refunds"])
            assert all(r[15] == (r[5] == "SUCCEEDED") for r in facts["refunds"])
            assert facts["profiles"][data["user_b"]] is None
            original = json.loads((args.folder / "original-facts.json").read_text("utf-8"))
            old = original["refunds"][0]
            same = next(r for r in facts["refunds"] if str(r[0]) == old[0])
            for index in (0, 1, 2, 3, 4, 6, 7, 8, 9, 12, 13, 14):
                assert str(same[index]) == str(old[index]), "Original refund binding changed"
        if args.stage == "memory-after-restart":
            profile = report["database_facts"]["profiles"][data["user_a"]]
            assert profile["preferences"] == {} and profile["last_mutation"]
        report["result"] = "PASS"
        save()
    except BaseException as error:
        report["result"] = "FAIL"
        report["failure_category"] = type(error).__name__
        save()
        raise
    finally:
        client.close()


if __name__ == "__main__":
    main()
