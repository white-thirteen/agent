"""Controlled provider attempts, native tools, structured parsing and token accounting."""

import asyncio

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.agents.types import AgentType
from app.runtime.model_gateway import (
    ModelCallContext,
    ModelCallError,
    ModelCallLimits,
    ModelCallUsage,
    ModelGateway,
)

CONTEXT = ModelCallContext("run-1", "task-1", AgentType.SUPERVISOR)


class Answer(BaseModel):
    answer: str


class ControlledModel:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0
        self.bindings = []

    def bind_tools(self, tools):
        self.bindings.append(tuple(tools))
        return self

    def with_structured_output(self, schema, **kwargs):
        assert schema is Answer
        assert kwargs == {"method": "function_calling", "include_raw": True}
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        output = next(self.outputs)
        if isinstance(output, BaseException):
            raise output
        if callable(output):
            return await output()
        return output


def known_message(**kwargs):
    return AIMessage(
        content="ready",
        usage_metadata={
            "input_tokens": 3,
            "output_tokens": 2,
            "total_tokens": 5,
        },
        **kwargs,
    )


async def test_native_calls_and_structured_raw_usage_are_preserved():
    message = known_message(tool_calls=[{"name": "lookup", "args": {"id": "1"}, "id": "call-1"}])
    model = ControlledModel(
        [message, {"raw": message, "parsed": Answer(answer="ok"), "parsing_error": None}]
    )
    gateway = ModelGateway(model, ModelCallLimits(8, 1, 1))
    first = await gateway.invoke(
        [], context=CONTEXT, model_usage=ModelCallUsage(), tools=[{"name": "a"}]
    )
    assert first.message is message
    assert first.message.tool_calls[0]["id"] == "call-1"
    second = await gateway.invoke_structured(
        [], schema=Answer, context=CONTEXT, model_usage=first.model_usage
    )
    assert second.parsed == Answer(answer="ok")
    assert second.usage.total_tokens == 5
    assert second.usage.status == "known"
    assert second.model_usage.model_attempts == 2


async def test_retry_consumes_task_budget_and_failed_tokens_remain_unknown():
    error = openai.APIConnectionError(request=httpx.Request("POST", "https://provider.invalid"))
    model = ControlledModel([error, known_message()])
    gateway = ModelGateway(model, ModelCallLimits(2, 1, 1))
    result = await gateway.invoke([], context=CONTEXT, model_usage=ModelCallUsage())
    assert result.model_usage.model_attempts == 2
    assert result.usage.total_tokens is None
    assert result.usage.status == "unknown"
    with pytest.raises(ModelCallError) as failure:
        await gateway.invoke([], context=CONTEXT, model_usage=result.model_usage)
    assert failure.value.code == "model_limit_exceeded"
    assert model.calls == 2


async def test_timeout_authentication_and_parse_failures_have_safe_snapshots():
    async def slow():
        await asyncio.sleep(1)

    model = ControlledModel([slow])
    gateway = ModelGateway(model, ModelCallLimits(8, 0.01, 0))
    with pytest.raises(ModelCallError) as timeout:
        await gateway.invoke([], context=CONTEXT, model_usage=ModelCallUsage(3))
    assert timeout.value.code == "model_timeout"
    assert timeout.value.model_usage.model_attempts == 4
    response = httpx.Response(401, request=httpx.Request("POST", "https://provider.invalid"))
    model = ControlledModel(
        [openai.AuthenticationError("private-provider-body", response=response, body=None)]
    )
    gateway = ModelGateway(model, ModelCallLimits(8, 1, 1))
    with pytest.raises(ModelCallError) as auth:
        await gateway.invoke([], context=CONTEXT, model_usage=ModelCallUsage())
    assert auth.value.code == "model_unavailable"
    assert "private-provider-body" not in str(auth.value)
    assert model.calls == 1
    model = ControlledModel(
        [{"raw": known_message(), "parsed": None, "parsing_error": ValueError("private")}]
    )
    gateway = ModelGateway(model, ModelCallLimits(8, 1, 1))
    with pytest.raises(ModelCallError) as invalid:
        await gateway.invoke_structured(
            [], schema=Answer, context=CONTEXT, model_usage=ModelCallUsage()
        )
    assert invalid.value.code == "model_output_invalid"
    assert invalid.value.usage.total_tokens == 5
    assert model.calls == 1


async def test_cancellation_and_programming_errors_propagate():
    for error in (asyncio.CancelledError(), TypeError("programming error")):
        gateway = ModelGateway(ControlledModel([error]), ModelCallLimits(8, 1, 1))
        with pytest.raises(type(error)):
            await gateway.invoke([], context=CONTEXT, model_usage=ModelCallUsage())


async def test_partial_usage_and_retry_ceiling_do_not_manufacture_known_totals():
    partial = AIMessage(content="ready", response_metadata={"token_usage": {"prompt_tokens": 7}})
    gateway = ModelGateway(ControlledModel([partial]), ModelCallLimits(8, 1, 0))
    result = await gateway.invoke([], context=CONTEXT, model_usage=ModelCallUsage())
    assert result.usage.input_tokens == 7
    assert result.usage.output_tokens is None
    assert result.usage.status == "unknown"
    error = openai.APIConnectionError(request=httpx.Request("POST", "https://provider.invalid"))
    model = ControlledModel([error, error, known_message()])
    gateway = ModelGateway(model, ModelCallLimits(8, 1, 1))
    with pytest.raises(ModelCallError) as failed:
        await gateway.invoke([], context=CONTEXT, model_usage=ModelCallUsage(5))
    assert model.calls == 2
    assert failed.value.model_usage.model_attempts == 7
    model = ControlledModel([error, known_message()])
    gateway = ModelGateway(model, ModelCallLimits(8, 1, 1))
    with pytest.raises(ModelCallError) as exhausted:
        await gateway.invoke([], context=CONTEXT, model_usage=ModelCallUsage(7))
    assert exhausted.value.code == "model_limit_exceeded"
    assert exhausted.value.model_usage.model_attempts == 8
    assert model.calls == 1


async def test_real_langchain_tool_bindings_do_not_mutate_shared_model():
    from langchain_openai import ChatOpenAI

    requests = []

    async def respond(request):
        import json

        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "controlled",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = ChatOpenAI(
            model="controlled", api_key="test", http_async_client=client, max_retries=0
        )
        gateway = ModelGateway(model, ModelCallLimits(8, 1, 0))
        for name in ("first", "second"):
            tool = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": name,
                    "parameters": {"type": "object", "properties": {}},
                },
            }
            await gateway.invoke([], context=CONTEXT, model_usage=ModelCallUsage(), tools=[tool])
        assert requests[0]["tools"][0]["function"]["name"] == "first"
        assert requests[1]["tools"][0]["function"]["name"] == "second"
        assert model.model_kwargs == {}
