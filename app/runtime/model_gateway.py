"""Serial model calls with task-owned immutable usage and bounded provider attempts.

Callers must collect the returned snapshot before the next call for the same task.
This gateway owns neither Run timing nor tool execution and keeps no request state.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

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
    deadline_monotonic: float | None = None
    on_attempt: Callable[[ModelCallUsage], None] | None = None
    before_attempt: Callable | None = None
    remaining_call_seconds: Callable[[], float] | None = None
    on_provider_call: Callable[[], None] | None = None
    history: tuple = ()
    on_context_view: Callable[[dict], None] | None = None
    on_context_usage: Callable | None = None
    on_compact: Callable | None = None
    current_usage: Callable | None = None
    prevalidated_summary: bool = False
    reserved_attempts: int = 0
    max_call_attempts: int | None = None

    def __post_init__(self):
        if self.reserved_attempts < 0 or (
            self.max_call_attempts is not None and self.max_call_attempts < 1
        ):
            raise ValueError("Invalid call attempt bounds")


class MaintenanceBudget(Protocol):
    """Durable reservations are consumed even if the process dies during a call."""

    async def reserve_attempt(self, maintenance_id: str) -> str: ...

    async def record_attempt(
        self, maintenance_id: str, attempt_id: str, usage: "UsageReport"
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class MaintenanceCallContext:
    maintenance_id: str
    budget: MaintenanceBudget
    deadline_monotonic: float
    max_output_tokens: int

    def __post_init__(self):
        if self.deadline_monotonic > time.monotonic() + 30 or self.max_output_tokens <= 0:
            raise ValueError("Invalid maintenance budget")


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
    status = (
        "unknown"
        if not reports or any(report.status == "unknown" for report in reports)
        else "estimated"
        if any(report.status == "estimated" for report in reports)
        else "known"
    )
    return UsageReport(*totals, status=status)


class ModelGateway:
    def __init__(
        self,
        model,
        limits: ModelCallLimits,
        *,
        context_window=None,
        output_reserve=None,
        require_context_limits=False,
    ):
        self._model = model
        self._limits = limits
        self._context_window = context_window
        self._output_reserve = output_reserve
        self._require_context_limits = require_context_limits

    @property
    def limits(self) -> ModelCallLimits:
        return self._limits

    async def _build_input(self, messages, *, context, model_usage, tools=(), schema=None):
        from langchain_core.messages.utils import count_tokens_approximately

        from app.context.builder import (
            ContextBudgetExceeded,
            ContextBuilder,
            ContextHistoryBudgetExceeded,
        )

        if context.prevalidated_summary:
            return messages
        if self._context_window is None or self._output_reserve is None:
            if self._require_context_limits:
                raise ModelCallError(
                    "context_budget_unavailable",
                    model_usage=model_usage,
                    usage=UsageReport(None, None, None, "unknown"),
                )
            return messages
        builder = ContextBuilder(
            token_counter=count_tokens_approximately, count_method="langchain_approximate"
        )

        def build(history):
            return builder.build(
                mandatory=messages,
                history=history,
                tools=tools,
                schema=schema,
                window_tokens=self._context_window,
                output_tokens=self._output_reserve,
            )

        try:
            result = build(context.history)
        except ContextHistoryBudgetExceeded:
            if context.on_compact is None:
                raise ModelCallError(
                    "context_budget_exceeded",
                    model_usage=model_usage,
                    usage=UsageReport(None, None, None, "unknown"),
                ) from None
            history = await context.on_compact(context)
            try:
                result = build(history)
            except ContextBudgetExceeded:
                raise ModelCallError(
                    "context_budget_exceeded",
                    model_usage=context.current_usage(),
                    usage=UsageReport(None, None, None, "unknown"),
                ) from None
        except ContextBudgetExceeded:
            raise ModelCallError(
                "context_budget_exceeded",
                model_usage=model_usage,
                usage=UsageReport(None, None, None, "unknown"),
            ) from None
        if context.on_context_view:
            context.on_context_view(
                {
                    "input_hash": result.input_hash,
                    "history_ids": list(result.history_ids),
                    "input_tokens": result.input_tokens,
                    "count_status": "estimated",
                    "count_method": result.count_method,
                }
            )
        return list(result.messages)

    async def invoke(
        self,
        messages,
        *,
        context: ModelCallContext | MaintenanceCallContext,
        model_usage: ModelCallUsage,
        tools: Sequence[BaseTool | dict] = (),
        max_output_tokens: int | None = None,
    ) -> ModelCallResult:
        if isinstance(context, MaintenanceCallContext):
            if tools or context.max_output_tokens <= 0:
                raise ValueError("Invalid maintenance model call")
            runnable = self._model.bind(max_tokens=context.max_output_tokens, temperature=0)
        else:
            messages = await self._build_input(
                messages, context=context, model_usage=model_usage, tools=tools
            )
            if context.current_usage:
                model_usage = context.current_usage()
            if max_output_tokens is not None and max_output_tokens <= 0:
                raise ValueError("Invalid model output limit")
            runnable = self._model.bind_tools(tools) if tools else self._model
            if max_output_tokens is None:
                max_output_tokens = self._output_reserve
            options = {}
            if max_output_tokens is not None:
                options["max_tokens"] = max_output_tokens
            if context.prevalidated_summary:
                options["temperature"] = 0
            if options:
                runnable = runnable.bind(**options)
        return await self._call_recorded(
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
        messages = await self._build_input(
            messages, context=context, model_usage=model_usage, schema=schema
        )
        if context.current_usage:
            model_usage = context.current_usage()
        runnable = self._model.with_structured_output(
            schema,
            method=STRUCTURED_METHOD,
            include_raw=True,
            **({"max_tokens": self._output_reserve} if self._output_reserve else {}),
        )
        return await self._call_recorded(
            runnable,
            messages,
            context=context,
            model_usage=model_usage,
            structured=True,
        )

    async def _call_recorded(self, runnable, messages, *, context, model_usage, structured):
        try:
            result = await self._call(
                runnable, messages, context=context, model_usage=model_usage, structured=structured
            )
        except ModelCallError as error:
            if isinstance(context, ModelCallContext) and context.on_context_usage:
                context.on_context_usage(error.usage)
            raise
        if isinstance(context, ModelCallContext) and context.on_context_usage:
            context.on_context_usage(result.usage)
        return result

    async def _call(self, runnable, messages, *, context, model_usage, structured):
        reports = []
        current = model_usage
        maintenance = isinstance(context, MaintenanceCallContext)
        initial_attempts = current.model_attempts
        max_retries_for_call = self._limits.max_retries
        if not maintenance and context.max_call_attempts is not None:
            max_retries_for_call = min(max_retries_for_call, max(0, context.max_call_attempts - 1))
        for retry in range(max_retries_for_call + 1):
            limit = (
                min(self._limits.max_attempts, 2)
                if maintenance
                else max(0, self._limits.max_attempts - context.reserved_attempts)
            )
            if not maintenance and context.max_call_attempts is not None:
                limit = min(limit, initial_attempts + context.max_call_attempts)
            deadline = context.deadline_monotonic
            remaining = deadline - time.monotonic() if deadline is not None else None
            if current.model_attempts >= limit or (remaining is not None and remaining <= 0):
                raise ModelCallError(
                    "model_limit_exceeded",
                    model_usage=current,
                    usage=_sum_usage(reports),
                )
            if maintenance:
                attempt_id = await context.budget.reserve_attempt(context.maintenance_id)
            current = ModelCallUsage(current.model_attempts + 1)
            if not maintenance and context.before_attempt is not None:
                await context.before_attempt(current)
            if not maintenance and context.on_attempt is not None:
                context.on_attempt(current)
            # Persistence and input preparation consume the same Run deadline.
            # Recheck after the durable attempt reservation, including on retries.
            remaining = deadline - time.monotonic() if deadline is not None else None
            if not maintenance and context.remaining_call_seconds is not None:
                scoped = context.remaining_call_seconds()
                remaining = min(remaining, scoped) if remaining is not None else scoped
            if remaining is not None and remaining <= 0:
                raise ModelCallError(
                    "model_limit_exceeded", model_usage=current, usage=_sum_usage(reports)
                )
            if maintenance:
                logger.info(
                    "Model maintenance attempt id=%s attempt=%s",
                    context.maintenance_id,
                    current.model_attempts,
                )
            else:
                logger.info(
                    "Model attempt task_id=%s run_id=%s agent=%s attempt=%s",
                    context.task_id,
                    context.run_id,
                    context.agent_type.value,
                    current.model_attempts,
                )
            try:
                # Logging and other local work also consume the granted time.
                remaining = deadline - time.monotonic() if deadline is not None else None
                if not maintenance and context.remaining_call_seconds is not None:
                    scoped = context.remaining_call_seconds()
                    remaining = min(remaining, scoped) if remaining is not None else scoped
                if remaining is not None and remaining <= 0:
                    raise ModelCallError(
                        "model_limit_exceeded", model_usage=current, usage=_sum_usage(reports)
                    )
                timeout_seconds = (
                    min(self._limits.timeout_seconds, remaining)
                    if remaining is not None
                    else self._limits.timeout_seconds
                )
                async with asyncio.timeout(timeout_seconds):
                    if not maintenance and context.on_provider_call is not None:
                        context.on_provider_call()
                    output = await runnable.ainvoke(messages)
            except (TimeoutError, openai.APIError) as error:
                reports.append(_token_usage(None))
                if maintenance:
                    await context.budget.record_attempt(
                        context.maintenance_id, attempt_id, reports[-1]
                    )
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
                if retryable and retry < max_retries_for_call:
                    await asyncio.sleep(0.1)
                    continue
                raise ModelCallError(
                    "model_timeout" if timeout else "model_unavailable",
                    model_usage=current,
                    usage=_sum_usage(reports),
                ) from None

            message = output.get("raw") if structured else output
            reports.append(_token_usage(message if isinstance(message, AIMessage) else None))
            if maintenance:
                await context.budget.record_attempt(context.maintenance_id, attempt_id, reports[-1])
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
