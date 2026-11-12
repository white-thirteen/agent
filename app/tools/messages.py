"""Validate correlatable native batches and create stable private ToolMessages."""

import json

from langchain_core.messages import AIMessage, ToolMessage

from app.tools.models import ParsedToolCall


def parse_tool_calls(message: AIMessage, *, used_ids: set[str], max_calls: int):
    if message.invalid_tool_calls or len(message.tool_calls) > max_calls:
        raise ValueError("Invalid tool call batch")
    calls = []
    for raw in message.tool_calls:
        call_id, name, args = raw.get("id"), raw.get("name"), raw.get("args")
        if (
            not isinstance(call_id, str)
            or not call_id.strip()
            or call_id in used_ids
            or not isinstance(name, str)
            or not name.strip()
            or not isinstance(args, dict)
        ):
            raise ValueError("Uncorrelatable tool call")
        used_ids.add(call_id)
        calls.append(ParsedToolCall(call_id, name, args))
    return calls


async def execute_tool_calls(calls, *, executor, context):
    return await executor.execute_batch(calls, context=context)


def to_tool_message(result, *, task_id: str) -> ToolMessage:
    content = json.dumps(
        {
            "status": result.status,
            "code": result.code,
            "message": result.message,
            "data": result.data,
        },
        ensure_ascii=False,
        allow_nan=False,
    )
    return ToolMessage(
        content=content,
        tool_call_id=result.call_id,
        name=result.tool_name,
        id=f"tool:{task_id}:{result.call_id}",
        status="success" if result.status == "success" else "error",
    )
