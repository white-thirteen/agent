"""Independent material validation; controlled JS is explicitly not client GUI proof."""

import json
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from app.main import create_app
from app.core.config import Settings
from app.api.schemas.chat import ChatRequest, RunRequest
from app.api.routes.approvals import DecisionInput, EmptyInput

ROOT = Path(__file__).resolve().parents[2]


def main():
    collection = json.loads((ROOT / "apifox/agent-engine-demo.postman_collection.json").read_text("utf-8"))
    exported = json.loads((ROOT / "apifox/agent-engine-demo.openapi.json").read_text("utf-8"))
    env = json.loads((ROOT / "apifox/local.postman_environment.json").read_text("utf-8"))
    actual = create_app(Settings().model_copy(update={"app_env": "test"})).openapi()
    assert set(exported["paths"]) == set(actual["paths"])
    # The export adds documented response models for routes with untyped returns.
    for name, schema in actual["components"]["schemas"].items():
        assert exported["components"]["schemas"][name] == schema
    variables = {item["key"]: item["value"] for item in env["values"]}
    assert len(variables) == 12
    assert variables["base_url"] == "http://127.0.0.1:8631"
    for key, value in variables.items():
        assert value in ("", "demo-c1", "demo-c2", "http://127.0.0.1:8631")
        if not value:
            variables[key] = str(uuid4())
    checked, scripts = [], []
    for group in collection["item"]:
        for item in group["item"]:
            request = item["request"]
            url = request["url"].removeprefix("{{base_url}}")
            url = re.sub(r"\{\{(.*?)\}\}", r"{\1}", url)
            method = request["method"].lower()
            assert method in actual["paths"][url]
            assert request["auth"]["type"] == "noauth"
            assert all(h["key"].lower() == "content-type" for h in request["header"])
            if "body" in request:
                raw = request["body"]["raw"]
                raw = re.sub(r"\{\{(.*?)\}\}", lambda m: variables[m[1]], raw)
                body = json.loads(raw)
                model = ChatRequest if url == "/agent/chat" else DecisionInput if url.endswith("/decision") else EmptyInput if "/admin/" in url else RunRequest
                model.model_validate(body)
            checked.append(item["name"])
            scripts.extend(event["script"]["exec"] for event in item.get("event", []))
    assert len(checked) == 26 and len(scripts) == 3
    node = r'''
const vm=require('vm'); const fs=require('fs'); const scripts=JSON.parse(fs.readFileSync(0,'utf8'));
let tests=0;
for(const script of scripts){
  const env={run_id:'old-run'};
  function run(j){vm.runInNewContext(script.join('\n'), {pm:{response:{json:()=>j},environment:{set:(k,v)=>env[k]=v}}});tests++;}
  run({current_task:{task_id:'task',run_id:null,refund:{application_id:'application',approval_id:'approval'}}});
  if(env.run_id!=='old-run'||env.task_id!=='task'||env.approval_id!=='approval') throw Error('task extraction');
  run({approval_id:'approval',subject_digest:'digest'});
  if(env.subject_digest!=='digest')throw Error('digest');
  run({accepted:true,run_id:'new-run',task_id:'task'});
  if(env.run_id!=='new-run')throw Error('resume');
  run({accepted:false,run_id:null});
  if(env.run_id!=='new-run')throw Error('END must not erase run');
  run({current_task:null});
}
process.stdout.write(JSON.stringify({controlled_script_cases:tests}));
'''
    result = subprocess.run(["node", "-e", node], input=json.dumps(scripts), text=True, capture_output=True, check=True)
    report = {"result": "PASS_material_contract", "paths": len(actual["paths"]),
              "groups": [len(g["item"]) for g in collection["item"]], "requests": checked,
              "variables": sorted(variables), "schema_matches_current_app": True,
              "javascript": json.loads(result.stdout), "gui_script_sse": "not executed"}
    output = ROOT / "docs/question/06-demo-qa-contract-evidence.json"
    assert not output.exists()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(report["result"], report["paths"], len(checked), result.stdout)


if __name__ == "__main__":
    main()
