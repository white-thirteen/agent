"""Serial model calls with task-owned immutable usage and bounded provider attempts.

Callers must collect the returned snapshot before the next call for the same task.
This gateway owns neither Run timing nor tool execution and keeps no request state.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import openai
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from app.agents.types import AgentType

logger = logging.getLogger(__name__)
STRUCTURED_METHOD = "function_calling"


@dataclass(frozen=True, slots=True)
class ModelCallLimits:
    max_attempts: int
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True, slots=True)
class ModelCallUsage:
    model_attempts: int = 0


@dataclass(frozen=True, slots=True)
class ModelCallContext:
    run_id: str
    task_id: str
    agent_type: AgentType


@dataclass(frozen=True, slots=True)
class UsageReport:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    status: Literal["known", "estimated", "unknown"]
    estimation_method: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCallResult:
    message: AIMessage
    parsed: BaseModel | None
    usage: UsageReport
    model_usage: ModelCallUsage


class ModelCallError(RuntimeError):
    """Safe provider/output failure, carrying even unsuccessful attempt consumption."""

    def __init__(self, code: str, *, model_usage: ModelCallUsage, usage: UsageReport):
        super().__init__(code)
        self.code = code
        self.model_usage = model_usage
        self.usage = usage


def _token_usage(message: AIMessage | None) -> UsageReport:
    metadata = message.usage_metadata if message is not None else None
    if metadata is None and message is not None:
        tokens = message.response_metadata.get("token_usage") or {}
        metadata = {
            "input_tokens": tokens.get("prompt_tokens"),
            "output_tokens": tokens.get("completion_tokens"),
            "total_tokens": tokens.get("total_tokens"),
        }
    values = [
        (metadata or {}).get(field) for field in ("input_tokens", "output_tokens", "total_tokens")
    ]
    return UsageReport(*values, status="known" if all(v is not None for v in values) else "unknown")


def _sum_usage(reports: list[UsageReport]) -> UsageReport:
    totals = []
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        values = [getattr(report, field) for report in reports]
        totals.append(
            sum(values) if values and all(value is not None for value in values) else None
        )
    return UsageReport(*totals, status="known" if all(v is not None for v in totals) else "unknown")


class ModelGateway:
    def __init__(self, model, limits: ModelCallLimits):
        self._model = model
        self._limits = limits

    async def invoke(
        self,
        messages,
        *,
        context: ModelCallContext,
        model_usage: ModelCallUsage,
        tools: Sequence[BaseTool | dict] = (),
    ) -> ModelCallResult:
        runnable = self._model.bind_tools(tools) if tools else self._model
        return await self._call(
            runnable,
            messages,
            context=context,
            model_usage=model_usage,
            structured=False,
        )

    async def invoke_structured(
        self,
        messages,
        *,
        schema: type[BaseModel],
        context: ModelCallContext,
        model_usage: ModelCallUsage,
    ) -> ModelCallResult:
        runnable = self._model.with_structured_output(
            schema,
            method=STRUCTURED_METHOD,
            include_raw=True,
        )
        return await self._call(
            runnable,
            messages,
            context=context,
            model_usage=model_usage,
            structured=True,
        )

    async def _call(self, runnable, messages, *, context, model_usage, structured):
        reports = []
        current = model_usage
        for retry in range(self._limits.max_retries + 1):
            if current.model_attempts >= self._limits.max_attempts:
                raise ModelCallError(
                    "model_limit_exceeded",
                    model_usage=current,
                    usage=_sum_usage(reports),
                )
            current = ModelCallUsage(current.model_attempts + 1)
            logger.info(
                "Model attempt task_id=%s run_id=%s agent=%s attempt=%s",
                context.task_id,
                context.run_id,
                context.agent_type.value,
                current.model_attempts,
            )
            try:
                async with asyncio.timeout(self._limits.timeout_seconds):
                    output = await runnable.ainvoke(messages)
            except (TimeoutError, openai.APIError) as error:
                reports.append(_token_usage(None))
                timeout = isinstance(error, (TimeoutError, openai.APITimeoutError))
                retryable = (
                    timeout
                    or isinstance(
                        error,
                        (
                            openai.APIConnectionError,
                            openai.RateLimitError,
                        ),
                    )
                    or isinstance(error, openai.APIStatusError)
                    and error.status_code >= 500
                )
                if retryable and retry < self._limits.max_retries:
                    await asyncio.sleep(0.1)
                    continue
                raise ModelCallError(
                    "model_timeout" if timeout else "model_unavailable",
                    model_usage=current,
                    usage=_sum_usage(reports),
                ) from None

            message = output.get("raw") if structured else output
            reports.append(_token_usage(message if isinstance(message, AIMessage) else None))
            parsed = output.get("parsed") if structured else None
            if (
                not isinstance(message, AIMessage)
                or structured
                and (output.get("parsing_error") is not None or not isinstance(parsed, BaseModel))
            ):
                raise ModelCallError(
                    "model_output_invalid",
                    model_usage=current,
                    usage=_sum_usage(reports),
                )
            return ModelCallResult(message, parsed, _sum_usage(reports), current)
