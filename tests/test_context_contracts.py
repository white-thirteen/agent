import json
import time

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.agents.types import AgentType
from app.context.compaction import summarize_messages
from app.context.models import SessionIdentity, mutation_source
from app.runtime.model_gateway import (
    MaintenanceCallContext,
    ModelCallContext,
    ModelCallLimits,
    ModelCallUsage,
    ModelGateway,
)


def counter(messages):
    return sum(len(str(message.content)) for message in messages)


def test_identity_and_legacy_mutation_contracts():
    a = SessionIdentity(user_id="a:b", conversation_id="中文/1")
    b = SessionIdentity(user_id="a", conversation_id="b:中文/1")
    assert a.archive_ref("s:1") != b.archive_ref("s:1")
    assert mutation_source({"task_id": "old"}).task_id == "old"
    assert (
        mutation_source({"source": {"kind": "preference_control", "command_id": "new"}}).command_id
        == "new"
    )


async def test_actual_langmem_gateway_and_provider_request():
    requests = []

    async def respond(request):
        import json

        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "t",
                "object": "chat.completion",
                "created": 0,
                "model": "controlled",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "summary"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = ChatOpenAI(
            model="controlled", api_key="test", http_async_client=client, max_retries=0
        )
        gateway = ModelGateway(model, ModelCallLimits(3, 3, 0))
        from langchain_core.messages import AIMessage

        original = [
            HumanMessage(content='ignore "rules"', id="1"),
            AIMessage(content="historical response", id="2"),
        ]
        summary, usage, reports = await summarize_messages(
            original,
            running_summary=None,
            gateway=gateway,
            context=ModelCallContext("run", "task", AgentType.SUPERVISOR),
            model_usage=ModelCallUsage(),
            token_counter=counter,
            max_input_tokens=10000,
            max_output_tokens=100,
        )
        next_summary, _, _ = await summarize_messages(
            [*original, HumanMessage(content="next", id="3")],
            running_summary=summary,
            gateway=gateway,
            context=ModelCallContext("run", "task", AgentType.SUPERVISOR),
            model_usage=usage,
            token_counter=counter,
            max_input_tokens=10000,
            max_output_tokens=100,
        )
        with pytest.raises(ValueError, match="prompt exceeds"):
            await summarize_messages(
                [HumanMessage(content="x", id="x")],
                running_summary=None,
                gateway=gateway,
                context=ModelCallContext("run", "task", AgentType.SUPERVISOR),
                model_usage=ModelCallUsage(),
                token_counter=counter,
                max_input_tokens=100,
                max_output_tokens=10,
            )
    assert summary.summarized_message_ids == {"1", "2"}
    assert usage.model_attempts == 1 and reports[0].total_tokens == 12
    assert requests[0]["max_completion_tokens"] == 100
    assert next_summary.summarized_message_ids == {"1", "2", "3"}
    assert len(requests) == 2
    for request in requests:
        assert [message["role"] for message in request["messages"]] == ["system", "user"]
    initial = json.loads(requests[0]["messages"][1]["content"].split("\n", 1)[1])
    incremental = json.loads(requests[1]["messages"][1]["content"].split("\n", 1)[1])
    assert initial == {
        "prior_summary": None,
        "messages": [
            {"role": "user", "content": 'ignore "rules"'},
            {"role": "assistant", "content": "historical response"},
        ],
    }
    assert incremental == {
        "prior_summary": "summary",
        "messages": [{"role": "user", "content": "next"}],
    }


async def test_maintenance_reservation_and_separate_attempts():
    class Budget:
        def __init__(self):
            self.events = []

        async def reserve_attempt(self, identifier):
            self.events.append(("reserved", identifier))
            return "attempt"

        async def record_attempt(self, identifier, attempt_id, usage):
            assert attempt_id == "attempt"
            self.events.append((usage.status, identifier))

    async def respond(request):
        return httpx.Response(
            200,
            json={
                "id": "t",
                "object": "chat.completion",
                "created": 0,
                "model": "controlled",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "summary"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    budget = Budget()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = ChatOpenAI(
            model="controlled", api_key="test", http_async_client=client, max_retries=0
        )
        gateway = ModelGateway(model, ModelCallLimits(8, 3, 0))
        context = MaintenanceCallContext("maint", budget, time.monotonic() + 30, 100)
        result = await gateway.invoke(
            [HumanMessage(content="hi")], context=context, model_usage=ModelCallUsage()
        )
    assert result.model_usage.model_attempts == 1
    assert budget.events == [("reserved", "maint"), ("unknown", "maint")]


async def test_summary_rejects_over_budget_before_provider_call():
    with pytest.raises(ValueError, match="exceeds"):
        await summarize_messages(
            [HumanMessage(content="too long", id="1")],
            running_summary=None,
            gateway=None,
            context=ModelCallContext("r", "t", AgentType.SUPERVISOR),
            model_usage=ModelCallUsage(),
            token_counter=counter,
            max_input_tokens=5,
            max_output_tokens=1,
        )


async def test_maintenance_retry_reserves_each_attempt_and_preserves_unknown():
    import openai

    from app.runtime.model_gateway import ModelCallError

    class Budget:
        def __init__(self):
            self.events = []

        async def reserve_attempt(self, identifier):
            self.events.append("reserve")
            return "attempt"

        async def record_attempt(self, identifier, attempt_id, usage):
            assert attempt_id == "attempt"
            self.events.append(usage.status)

    class Model:
        def bind(self, **kwargs):
            assert kwargs == {"max_tokens": 64, "temperature": 0}
            return self

        async def ainvoke(self, messages):
            raise openai.APIConnectionError(request=httpx.Request("POST", "https://test.invalid"))

    budget = Budget()
    gateway = ModelGateway(Model(), ModelCallLimits(8, 1, 3))
    with pytest.raises(ModelCallError) as failure:
        await gateway.invoke(
            [],
            context=MaintenanceCallContext("m", budget, time.monotonic() + 30, 64),
            model_usage=ModelCallUsage(),
        )
    assert failure.value.model_usage.model_attempts == 2
    assert failure.value.usage.status == "unknown"
    assert budget.events == ["reserve", "unknown", "reserve", "unknown"]


async def test_incremental_summary_accepts_full_and_new_ranges_without_replay():
    from langchain_core.messages import AIMessage

    class Model:
        def __init__(self):
            self.calls = 0

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            self.calls += 1
            return AIMessage(content="summary")

    model = Model()
    kwargs = dict(
        gateway=ModelGateway(model, ModelCallLimits(8, 3, 0)),
        context=ModelCallContext("r", "t", AgentType.SUPERVISOR),
        token_counter=counter,
        max_input_tokens=10000,
        max_output_tokens=100,
    )
    first = HumanMessage(content="first", id="1")
    second = HumanMessage(content="second", id="2")
    summary, usage, _ = await summarize_messages(
        [first], running_summary=None, model_usage=ModelCallUsage(), **kwargs
    )
    full, full_usage, _ = await summarize_messages(
        [first, second], running_summary=summary, model_usage=usage, **kwargs
    )
    incremental, incremental_usage, _ = await summarize_messages(
        [second], running_summary=summary, model_usage=usage, **kwargs
    )
    before = model.calls
    replay, replay_usage, reports = await summarize_messages(
        [first], running_summary=summary, model_usage=usage, **kwargs
    )
    assert full.summarized_message_ids == incremental.summarized_message_ids == {"1", "2"}
    assert full_usage.model_attempts == incremental_usage.model_attempts == 2
    assert replay == summary and replay_usage == usage and not reports and model.calls == before


async def test_system_message_rejected_before_model_call():
    from langchain_core.messages import SystemMessage

    with pytest.raises(ValueError, match="public"):
        await summarize_messages(
            [SystemMessage(content="", id="s"), HumanMessage(content="hello", id="h")],
            running_summary=None,
            gateway=None,
            context=ModelCallContext("r", "t", AgentType.SUPERVISOR),
            model_usage=ModelCallUsage(),
            token_counter=counter,
            max_input_tokens=10000,
            max_output_tokens=100,
        )


async def test_run_compaction_charges_attempt_even_when_interrupted():
    import asyncio

    from app.context.compaction import summarize_for_run
    from app.runtime.models import RunLimits, RunUsage
    from app.runtime.run_scope import RunScope

    class Model:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            raise asyncio.CancelledError

    scope = RunScope(
        limits=RunLimits(active_timeout_seconds=10, max_tool_calls=5),
        model_usage=ModelCallUsage(1),
        run_usage=RunUsage(),
    )
    scope.start_active_period()
    with pytest.raises(asyncio.CancelledError):
        await summarize_for_run(
            [HumanMessage(content="hello", id="h")],
            scope=scope,
            context=ModelCallContext("r", "t", AgentType.SUPERVISOR),
            execution_mode="normal",
            running_summary=None,
            gateway=ModelGateway(Model(), ModelCallLimits(8, 3, 0)),
            token_counter=counter,
            max_input_tokens=10000,
            max_output_tokens=100,
        )
    assert scope.model_usage().model_attempts == 2


@pytest.mark.parametrize("known", [True, False])
async def test_post_call_failure_preserves_consumed_budget_and_usage(monkeypatch, known):
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage

    import app.context.compaction as compaction

    class Model:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            usage = {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12} if known else None
            return AIMessage(content="summary", usage_metadata=usage)

    async def bad_result(messages, *, model, **kwargs):
        await model.ainvoke(messages)
        return SimpleNamespace(running_summary=None)

    monkeypatch.setattr(compaction, "asummarize_messages", bad_result)
    with pytest.raises(compaction.CompactionError) as failure:
        await summarize_messages(
            [HumanMessage(content="hello", id="h")],
            running_summary=None,
            gateway=ModelGateway(Model(), ModelCallLimits(8, 3, 0)),
            context=ModelCallContext("r", "t", AgentType.SUPERVISOR),
            model_usage=ModelCallUsage(3),
            token_counter=counter,
            max_input_tokens=10000,
            max_output_tokens=100,
        )
    assert failure.value.model_usage.model_attempts == 4
    assert failure.value.usage.status == ("known" if known else "unknown")
    assert failure.value.usage.total_tokens == (12 if known else None)
    assert len(failure.value.reports) == 1
    assert isinstance(failure.value.__cause__, ValueError)
