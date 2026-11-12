"""Single executor for model and deterministic calls, including batch preflight."""

import asyncio
import logging
from dataclasses import replace
from uuid import uuid4

from pydantic import ValidationError

from app.tools.models import (
    BusinessExecutionContext,
    HandlerResult,
    PolicyDecision,
    ToolExecutionResult,
    ToolTransientError,
    ToolUnavailableError,
)

logger = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(self, registry, policy, *, max_calls_per_message=4):
        self.registry = registry
        self.policy = policy
        self.max_calls_per_message = max_calls_per_message

    def _evaluate(self, call, context, *, validated_args=None):
        definition = self.registry.get(call.name)
        decision = self.policy.evaluate(
            call=call,
            definition=definition,
            context=context,
            usage=context.scope.run_usage(),
            remaining_active_seconds=context.scope.remaining_active_seconds(),
            validated_args=validated_args,
        )
        return definition, decision

    def _result(
        self,
        call,
        context,
        *,
        status,
        code,
        message,
        attempts=0,
        data=None,
        effect_status="not_started",
        execution_id=None,
    ):
        return ToolExecutionResult(
            call.call_id,
            call.name,
            execution_id or str(uuid4()),
            status,
            code,
            message,
            data,
            attempts,
            context.scope.run_usage(),
            effect_status,
        )

    async def execute(self, call, *, context):
        definition, decision = self._evaluate(call, context)
        result = await self._execute_checked(call, context, definition, decision)
        return self._record_args(result, decision)

    @staticmethod
    def _record_args(result, decision):
        args = decision.validated_args
        return replace(result, normalized_args=args.model_dump(mode="json") if args else None)

    async def execute_batch(self, calls, *, context):
        ids = [call.call_id for call in calls]
        if (
            not calls
            or len(calls) > self.max_calls_per_message
            or any(not isinstance(value, str) or not value.strip() for value in ids)
            or len(set(ids)) != len(ids)
            or any(
                not isinstance(call.name, str)
                or not call.name.strip()
                or not isinstance(call.raw_args, dict)
                for call in calls
            )
        ):
            raise ValueError("Uncorrelatable tool call batch")
        prepared = [(call, *self._evaluate(call, context)) for call in calls]
        results = []
        stopped = False
        for call, definition, decision in prepared:
            if stopped:
                results.append(
                    self._record_args(
                        self._result(
                            call,
                            context,
                            status="not_executed",
                            code="previous_call_failed",
                            message="Previous call did not succeed.",
                        ),
                        decision,
                    )
                )
                continue
            result = await self._execute_checked(call, context, definition, decision)
            results.append(self._record_args(result, decision))
            stopped = result.status != "success"
        return results

    async def _execute_checked(self, call, context, definition, initial):
        execution_id = str(uuid4())
        attempts = 0
        decision = initial
        if decision.decision is not PolicyDecision.ALLOW:
            return self._denied(call, context, decision, attempts, execution_id)
        typed = decision.validated_args
        for retry in range(definition.metadata.max_retries + 1):
            current_definition, decision = self._evaluate(call, context, validated_args=typed)
            if current_definition is not definition:
                return self._result(
                    call,
                    context,
                    status="policy_denied",
                    code="tool_not_allowed",
                    message="Tool call is not allowed.",
                    attempts=attempts,
                    execution_id=execution_id,
                )
            if decision.decision is not PolicyDecision.ALLOW:
                return self._denied(call, context, decision, attempts, execution_id)
            remaining = context.scope.remaining_active_seconds()
            if remaining <= 0:
                return self._result(
                    call,
                    context,
                    status="policy_denied",
                    code="tool_budget_exceeded",
                    message="Tool call is not allowed.",
                    attempts=attempts,
                    execution_id=execution_id,
                )
            usage = context.scope.run_usage()
            context.scope.adopt_tool_usage(replace(usage, tool_calls=usage.tool_calls + 1))
            attempts += 1
            business = BusinessExecutionContext(
                context.execution.user_id, context.execution.task_id, context.execution.run_id
            )
            timeout = min(definition.metadata.timeout_seconds, remaining)
            try:
                async with asyncio.timeout(timeout):
                    response = await definition.handler(typed, business)
            except TimeoutError:
                return self._result(
                    call,
                    context,
                    status="failed",
                    code="tool_timeout",
                    message="Tool execution timed out.",
                    attempts=attempts,
                    effect_status="not_applicable" if definition.metadata.read_only else "unknown",
                    execution_id=execution_id,
                )
            except ToolTransientError:
                if definition.metadata.read_only and retry < definition.metadata.max_retries:
                    continue
                return self._result(
                    call,
                    context,
                    status="failed",
                    code="order_query_unavailable",
                    message="Tool execution unavailable.",
                    attempts=attempts,
                    effect_status="not_applicable" if definition.metadata.read_only else "unknown",
                    execution_id=execution_id,
                )
            except ToolUnavailableError:
                return self._result(
                    call,
                    context,
                    status="failed",
                    code="order_query_unavailable",
                    message="Tool execution unavailable.",
                    attempts=attempts,
                    effect_status="not_applicable" if definition.metadata.read_only else "unknown",
                    execution_id=execution_id,
                )
            if not isinstance(response, HandlerResult):
                raise TypeError("Tool handler returned an invalid contract")
            if response.rejection:
                return self._result(
                    call,
                    context,
                    status="business_rejected",
                    code=response.rejection.code,
                    message=response.rejection.message,
                    attempts=attempts,
                    effect_status="not_applicable",
                    execution_id=execution_id,
                )
            try:
                data = definition.result_schema.model_validate(
                    response.data.model_dump()
                ).model_dump(mode="json")
            except ValidationError:
                return self._result(
                    call,
                    context,
                    status="failed",
                    code="tool_result_invalid",
                    message="Tool result is invalid.",
                    attempts=attempts,
                    effect_status="not_applicable" if definition.metadata.read_only else "unknown",
                    execution_id=execution_id,
                )
            logger.info(
                "Tool completed task_id=%s run_id=%s tool=%s attempts=%d",
                context.execution.task_id,
                context.execution.run_id,
                definition.metadata.name,
                attempts,
            )
            return self._result(
                call,
                context,
                status="success",
                code="ok",
                message="Tool succeeded.",
                data=data,
                attempts=attempts,
                effect_status="not_applicable" if definition.metadata.read_only else "completed",
                execution_id=execution_id,
            )

    def _denied(self, call, context, decision, attempts, execution_id):
        approval = decision.decision is PolicyDecision.REQUIRE_APPROVAL
        return self._result(
            call,
            context,
            status="approval_required" if approval else "policy_denied",
            code=decision.code,
            message=decision.message,
            attempts=attempts,
            execution_id=execution_id,
        )
