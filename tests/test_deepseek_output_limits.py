"""Verify DeepSeek's wire field and truncated summary settlement without paid calls."""

import json
import time

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.agents.types import AgentType
from app.context.compaction import CompactionError, summarize_messages
from app.core.config import Settings
from app.infrastructure.model import DeepSeekChatOpenAI, model_resources
from app.runtime.model_gateway import (
    MaintenanceCallContext,
    ModelCallContext,
    ModelCallLimits,
    ModelCallUsage,
    ModelGateway,
)


class Answer(BaseModel):
    text: str


class Budget:
    def __init__(self):
        self.reports = []

    async def reserve_attempt(self, identifier):
        return "attempt"

    async def record_attempt(self, identifier, attempt, usage):
        self.reports.append(usage)


async def test_deepseek_wire_field_for_all_call_paths_and_summary_truncation():
    requests = []

    async def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if "tools" in payload:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call",
                        "type": "function",
                        "function": {"name": "Answer", "arguments": '{"text":"ok"}'},
                    }
                ],
            }
            reason = "tool_calls"
        else:
            message = {"role": "assistant", "content": "summary"}
            reason = "length" if len(requests) == 5 else "stop"
        return httpx.Response(
            200,
            json={
                "id": "t",
                "object": "chat.completion",
                "created": 0,
                "model": "controlled",
                "choices": [{"index": 0, "message": message, "finish_reason": reason}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = DeepSeekChatOpenAI(model="controlled", api_key="test", http_async_client=client)
        gateway = ModelGateway(model, ModelCallLimits(8, 3, 0), output_reserve=64)
        ctx = ModelCallContext("run", "task", AgentType.SUPERVISOR)
        await gateway.invoke(
            [HumanMessage(content="current")], context=ctx, model_usage=ModelCallUsage()
        )
        await gateway.invoke_structured(
            [HumanMessage(content="current")],
            schema=Answer,
            context=ctx,
            model_usage=ModelCallUsage(),
        )
        kwargs = dict(
            messages=[HumanMessage(content="history", id="one")],
            running_summary=None,
            gateway=gateway,
            token_counter=lambda ms: sum(len(str(m.content)) for m in ms),
            max_input_tokens=10000,
            max_output_tokens=32,
            model_usage=ModelCallUsage(),
        )
        await summarize_messages(context=ctx, **kwargs)
        budget = Budget()
        maintenance = MaintenanceCallContext("maintenance", budget, time.monotonic() + 25, 32)
        await summarize_messages(context=maintenance, **kwargs)
        with pytest.raises(CompactionError) as truncated:
            await summarize_messages(context=ctx, **kwargs)
        assert truncated.value.model_usage.model_attempts == 1
        assert truncated.value.reports[0].output_tokens == 7
        assert budget.reports[0].output_tokens == 7
    assert [request["max_tokens"] for request in requests] == [64, 64, 32, 32, 32]
    assert all("max_completion_tokens" not in request for request in requests)
    assert all("temperature" not in request for request in requests[:2])
    assert all(request["temperature"] == 0 for request in requests[2:])


def test_other_providers_keep_sdk_default_wire_field():
    model = ChatOpenAI(model="controlled", api_key="test")
    payload = model._get_request_payload([HumanMessage(content="x")], max_tokens=32)
    assert payload["max_completion_tokens"] == 32 and "max_tokens" not in payload


async def test_application_selects_adapter_only_for_official_deepseek_host():
    for url, expected in (
        ("https://api.deepseek.com/v1", DeepSeekChatOpenAI),
        ("https://example.test/v1", ChatOpenAI),
    ):
        settings = Settings(
            _env_file=None, model_name="controlled", model_api_key="test", model_base_url=url
        )
        async with model_resources(settings) as (model, _):
            assert type(model) is expected
