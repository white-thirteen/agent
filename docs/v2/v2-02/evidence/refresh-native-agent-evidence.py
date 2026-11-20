"""Export only native role/model metadata, excluding conversation contents."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[4]
    output = Path(__file__).with_name("subagent-runtime-evidence.json")
    previous = json.loads(output.read_text(encoding="utf-8"))
    parent = "01a1f256-6373-77f1-b5a0-3ad522366927"
    agents = []
    for day in ("2026/11/19", "2026/11/20"):
        for path in (Path.home() / ".codex/sessions" / day).glob("*.jsonl"):
            with path.open(encoding="utf-8") as stream:
                first = json.loads(next(stream))
                if first.get("type") != "session_meta":
                    continue
                meta = first["payload"]
                source = meta.get("source")
                if not isinstance(source, dict):
                    continue
                spawn = source.get("subagent", {}).get("thread_spawn", {})
                name = spawn.get("agent_path", "")
                if spawn.get("parent_thread_id") != parent or not name.startswith("/root/v202_"):
                    continue
                turns = []
                for line in stream:
                    record = json.loads(line)
                    if record.get("type") == "turn_context":
                        payload = record["payload"]
                        turns.append({key: payload.get(key) for key in (
                            "model", "effort", "approval_policy", "sandbox_policy"
                        )})
            verified = bool(turns) and all(
                turn["model"] == "gpt-6.1-terra" and turn["effort"] == "high"
                for turn in turns
            )
            agents.append({
                "agent_path": name,
                "session_id": meta["id"],
                "agent_role": meta.get("agent_role"),
                "observed_turns": turns,
                "verified_terra_high": verified,
            })
    previous.update({
        "date": "2026-11-20",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "parent_thread_id": parent,
        "agents": sorted(agents, key=lambda agent: agent["agent_path"]),
    })
    for config in previous["configuration_sources"]:
        actual = hashlib.sha256((root / config["path"]).read_bytes()).hexdigest()
        if actual != config["sha256"]:
            raise AssertionError(f"Configuration changed: {config['path']}")
    if not agents or not all(agent["verified_terra_high"] for agent in agents):
        raise AssertionError("Native metadata does not prove all required model settings")
    output.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"agents": len(agents), "all_terra_high": True}))


if __name__ == "__main__":
    main()
