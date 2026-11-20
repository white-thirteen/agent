"""Check current client examples and local OpenAPI references without a desktop client."""

import json
import re
from pathlib import Path

root = Path("apifox")
collection = json.loads((root / "agent-engine-demo.postman_collection.json").read_text(encoding="utf8"))
api = json.loads((root / "agent-engine-demo.openapi.json").read_text(encoding="utf8"))
env = json.loads((root / "local.postman_environment.json").read_text(encoding="utf8"))
paths = {
    "/agent/preferences/read",
    "/agent/preferences/mutations",
    "/agent/preferences/operations/{operation_id}/status",
}
assert paths <= api["paths"].keys()
for name in ("PreferenceIdentity", "PreferenceMutation", "MemoryCommand"):
    assert name in api["components"]["schemas"]


def check(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and value.startswith("#/"):
                target = api
                for part in value[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
            check(value)
    elif isinstance(node, list):
        for value in node:
            check(value)


check(api)
keys = {item["key"] for item in env["values"]}
assert {"preference_revision", "preference_operation_id"} <= keys
for item in collection["item"][-1]["item"]:
    raw = item["request"].get("body", {}).get("raw")
    if raw:
        raw = raw.replace("{{preference_revision}}", "0")
        json.loads(re.sub(r"\{\{[^{}]+\}\}", "sample", raw))
examples = api["paths"]["/agent/chat"]["post"]["requestBody"]["content"]["application/json"]["examples"]
assert "legacyPreferenceHint" in examples and not any(key.startswith("memory") for key in examples)
print("PASS: JSON syntax, OpenAPI references, preference paths, environment keys and legacy hint")
