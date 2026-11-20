import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.agents.types import AgentType
from app.context.builder import ContextBudgetExceeded, ContextBuilder
from app.graph.transfers import public_task_messages
from app.runtime.model_gateway import (
    ModelCallContext,
    ModelCallError,
    ModelCallLimits,
    ModelCallUsage,
    ModelGateway,
)


def count(messages):
    return sum(len(str(message.content)) for message in messages)


def test_complete_task_messages_are_not_truncated():
    messages = [HumanMessage(content=str(i), id=str(i)) for i in range(20)]
    assert (
        public_task_messages({"messages": messages, "task_message_ids": [m.id for m in messages]})
        == messages
    )


def test_budget_counts_schema_and_preserves_whole_interactions():
    class Output(BaseModel):
        answer: str

    builder = ContextBuilder(token_counter=count, count_method="test characters")
    mandatory = [SystemMessage(content="trusted"), HumanMessage(content="current")]
    history = [[HumanMessage(content="old", id="1"), AIMessage(content="answer", id="2")]]
    result = builder.build(
        mandatory=mandatory, history=history, window_tokens=2000, output_tokens=100, schema=Output
    )
    assert result.history_ids == ("1", "2")
    assert result.messages[0] == mandatory[0] and result.messages[-1] == mandatory[-1]
    assert "untrusted background" in result.messages[1].content
    with pytest.raises(ContextBudgetExceeded):
        builder.build(
            mandatory=mandatory, history=history, window_tokens=100, output_tokens=10, schema=Output
        )


@pytest.mark.asyncio
async def test_gateway_budgets_complete_schema_and_records_injection():
    class Output(BaseModel):
        answer: str

    class Model:
        def __init__(self):
            self.calls = []
            self.maximum = None

        def with_structured_output(self, schema, **kwargs):
            assert schema is Output
            self.maximum = kwargs["max_tokens"]
            return self

        def bind(self, **kwargs):
            self.maximum = kwargs["max_tokens"]
            return self

        async def ainvoke(self, messages):
            self.calls.append(messages)
            return {
                "raw": AIMessage(content="ok"),
                "parsed": Output(answer="ok"),
                "parsing_error": None,
            }

    model = Model()
    views = []
    context = ModelCallContext(
        "run",
        "task",
        AgentType.SUPERVISOR,
        history=((HumanMessage(content="old", id="old"), AIMessage(content="reply", id="reply")),),
        on_context_view=views.append,
    )
    gateway = ModelGateway(model, ModelCallLimits(2, 3, 0), context_window=1024, output_reserve=64)
    await gateway.invoke_structured(
        [HumanMessage(content="now")], schema=Output, context=context, model_usage=ModelCallUsage()
    )
    assert model.maximum == 64 and views[0]["history_ids"] == ["old", "reply"]
    assert views[0]["count_status"] == "estimated" and len(model.calls) == 1
    narrow = ModelGateway(model, ModelCallLimits(2, 3, 0), context_window=70, output_reserve=64)
    with pytest.raises(ModelCallError) as error:
        await narrow.invoke_structured(
            [HumanMessage(content="now")],
            schema=Output,
            context=context,
            model_usage=ModelCallUsage(),
        )
    assert error.value.code == "context_budget_exceeded" and len(model.calls) == 1


@pytest.mark.asyncio
async def test_structured_output_reservation_reaches_provider_transport():
    import json

    import httpx
    from langchain_openai import ChatOpenAI

    class Output(BaseModel):
        answer: str

    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 1,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call",
                                    "type": "function",
                                    "function": {"name": "Output", "arguments": '{"answer":"ok"}'},
                                }
                            ],
                        },
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        model = ChatOpenAI(
            model="test", api_key="test", base_url="https://test.invalid", http_async_client=client
        )
        gateway = ModelGateway(
            model, ModelCallLimits(1, 5, 0), context_window=2048, output_reserve=64
        )
        context = ModelCallContext("run", "task", AgentType.SUPERVISOR)
        result = await gateway.invoke_structured(
            [HumanMessage(content="hello")],
            schema=Output,
            context=context,
            model_usage=ModelCallUsage(),
        )
    assert result.parsed.answer == "ok"
    assert requests[0]["max_completion_tokens"] == 64 and len(requests[0]["tools"]) == 1
