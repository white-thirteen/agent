"""One governed optional preference read in each specialist's preparation node."""

from dataclasses import asdict
from uuid import NAMESPACE_URL, uuid5

from app.graph.contracts import GraphProtocolError
from app.knowledge.models import canonical, digest
from app.tools.models import ParsedToolCall, PolicyDecision, ToolExecutionContext


async def read_optional_preferences(state, runtime, *, registry, executor, node):
    execution = runtime.context
    ctx = execution.context
    request = state["request"]
    definition = registry.get("read_preferences")
    version = definition.metadata.version if definition else "1"
    call = ParsedToolCall(
        "node:"
        + str(
            uuid5(
                NAMESPACE_URL,
                canonical([ctx.task_id, node, "read_preferences", version, "preferences", 0]),
            )
        ),
        "read_preferences",
        {},
    )
    context = ToolExecutionContext(
        ctx,
        request.agent_type,
        request.task_type,
        node,
        execution.permission_scopes,
        "node",
        frozenset({("read_preferences", version)}),
        {"read_preferences": {}},
        execution.scope.limits,
        execution.scope,
    )
    records = dict(state.get("call_records", {}))
    previous = state.get("memory_read_record")
    if previous and (
        previous["task_id"] != ctx.task_id
        or previous["user_id"] != ctx.user_id
        or previous["call"] != asdict(call)
        or previous["tool_version"] != version
        or previous["args_digest"] != digest(canonical({}))
    ):
        raise GraphProtocolError("Preference read association conflict")
    if execution.scope.budget_exhausted():
        return {"outcome": "failed", "error_code": "tool_budget_exceeded"}
    checked = await executor.assess(call, context=context)
    if previous and checked.decision is PolicyDecision.ALLOW:
        record = previous
    else:
        result = await executor.execute(call, context=context)
        record = {
            "task_id": ctx.task_id,
            "user_id": ctx.user_id,
            "run_id": ctx.run_id,
            "call": asdict(call),
            "tool_version": version,
            "args_digest": digest(canonical({})),
            "origin": "node",
            "node_name": node,
            "normalized_args": result.normalized_args,
            "result": asdict(result),
        }
    records[call.call_id] = record
    result = record["result"]
    update = {
        "call_records": records,
        "memory_read_record": record,
        "run_usage": asdict(execution.scope.run_usage()),
        "memory_context": {},
    }
    if result["code"] == "tool_budget_exceeded" or execution.scope.budget_exhausted():
        return {**update, "outcome": "failed", "error_code": "tool_budget_exceeded"}
    if result["status"] == "success":
        update.update(
            memory_read_status=result["data"]["status"],
            memory_context={
                "preferences": result["data"]["preferences"],
                "revision": result["data"]["revision"],
            },
        )
    elif result["status"] == "policy_denied":
        update["memory_read_status"] = "denied"
    else:
        update["memory_read_status"] = "unavailable"
    return update


def preference_instructions(state):
    """Only two enumerated values enter prompts, bounded far below 128 tokens."""
    values = (state.get("memory_context") or {}).get("preferences", {})
    if not values:
        return ""
    return (
        " Presentation preferences: "
        + canonical(values)
        + ". The current user's explicit language/style instructions take precedence. "
        "Preferences never change facts, permissions, tool arguments or evidence."
    )
