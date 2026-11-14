"""Single executor for model and deterministic calls, including batch preflight."""

import asyncio
import logging
from dataclasses import asdict, replace
from uuid import uuid4

from pydantic import ValidationError

from app.tools.models import (
    BusinessExecutionContext,
    HandlerResult,
    MemoryBusinessContext,
    PolicyDecision,
    PreparedToolAttempt,
    ToolEffectUnknownError,
    ToolExecutionResult,
    ToolNotStartedError,
    ToolTransientError,
    ToolUnavailableError,
)

logger = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(self, registry, policy, *, max_calls_per_message=4, approval_service=None):
        self.registry = registry
        self.policy = policy
        self.max_calls_per_message = max_calls_per_message
        self.approval_service = approval_service

    def _evaluate(self, call, context, *, validated_args=None, verified_approval=None):
        definition = self.registry.get(call.name)
        decision = self.policy.evaluate(
            call=call,
            definition=definition,
            context=context,
            usage=context.scope.run_usage(),
            remaining_active_seconds=context.scope.remaining_active_seconds(),
            validated_args=validated_args,
            verified_approval=verified_approval,
        )
        return definition, decision

    async def assess(self, call, *, context):
        """Evaluate a call without consuming a tool attempt or executing a handler."""
        return self._evaluate(call, context)[1]

    @staticmethod
    def _business_context(call, context):
        """Project only the associations a refund handler actually needs."""
        refund_tools = {
            "check_refund_eligibility",
            "prepare_refund_application",
            "register_refund_approval",
            "close_refund_application",
        }
        business = context.refund_context
        if call.name in refund_tools and business is not None:
            execution = context.execution
            if (
                business.user_id != execution.user_id
                or business.task_id != execution.task_id
                or business.run_id != execution.run_id
                or business.conversation_id != execution.conversation_id
                or business.workflow_id != execution.workflow_id
            ):
                raise ValueError("Refund context association mismatch")
            return business
        if call.name in refund_tools - {"check_refund_eligibility"}:
            raise ValueError("Refund context is required")
        return BusinessExecutionContext(
            context.execution.user_id, context.execution.task_id, context.execution.run_id
        )

    async def _verify_refund(self, call, context, definition, typed):
        from app.domain.refunds import OriginalRefundCall
        from app.workflows.approvals import ApprovalReference

        business = context.refund_context
        if (
            self.approval_service is None
            or business is None
            or context.approval_binding is None
            or not business.approval_id
            or business.user_id != context.execution.user_id
            or business.conversation_id != context.execution.conversation_id
            or business.task_id != context.execution.task_id
            or business.workflow_id != context.execution.workflow_id
            or business.run_id != context.execution.run_id
        ):
            raise ValueError("Trusted refund context is incomplete")
        original = OriginalRefundCall(
            call.call_id,
            call.name,
            definition.metadata.version,
            call.raw_args,
            typed.model_dump(mode="json"),
        )
        return await self.approval_service.verify_for_call(
            ApprovalReference(business.approval_id),
            original_call=original,
            context=business,
            interrupt_binding=context.approval_binding,
        )

    async def prepare_attempt(
        self, call, *, context, execution_context=None, business_context=None
    ):
        """Preflight the original refund and produce a checkpointable, unspent attempt."""
        import psycopg
        from psycopg_pool import PoolClosed, PoolTimeout

        from app.domain.refunds import canonical_digest
        from app.workflows.approvals import ApprovalError

        if context.origin == "node":
            return self._prepare_node_attempt(call, context, execution_context, business_context)
        definition, initial = self._evaluate(call, context)
        if (
            execution_context is not None
            or business_context is not None
            or definition is None
            or call.name != "refund_order"
            or context.origin != "model"
        ):
            return self._result(
                call,
                context,
                status="policy_denied",
                code="tool_not_allowed",
                message="Tool call is not allowed.",
            )
        if initial.decision is PolicyDecision.DENY:
            return self._denied(call, context, initial, 0, str(uuid4()))
        try:
            verified = await self._verify_refund(call, context, definition, initial.validated_args)
        except (ApprovalError, ValueError):
            return self._result(
                call,
                context,
                status="policy_denied",
                code="approval_not_valid",
                message="Approval is not valid.",
            )
        except (psycopg.Error, PoolClosed, PoolTimeout):
            return self._result(
                call,
                context,
                status="failed",
                code="approval_unavailable",
                message="Approval is unavailable.",
            )
        _, checked = self._evaluate(
            call, context, validated_args=initial.validated_args, verified_approval=verified
        )
        if checked.decision is not PolicyDecision.ALLOW:
            return self._denied(call, context, checked, 0, str(uuid4()))
        args = checked.validated_args.model_dump(mode="json")
        count = context.scope.run_usage().tool_calls
        remaining = context.scope.remaining_active_seconds()
        if remaining <= 0:
            return self._result(
                call,
                context,
                status="policy_denied",
                code="tool_budget_exceeded",
                message="Tool call is not allowed.",
            )
        return PreparedToolAttempt(
            str(uuid4()),
            context.execution.run_id,
            context.execution.task_id,
            call,
            definition.metadata.version,
            args,
            canonical_digest(args),
            context.refund_context.operation_id,
            count,
            count + 1,
            min(definition.metadata.timeout_seconds, remaining),
            asdict(context.refund_context),
            asdict(context.approval_binding),
        )

    def _prepare_node_attempt(self, call, context, execution_context, business_context):
        """Preflight only the frozen memory write pair without executing its handler."""
        from app.agents.types import AgentType, TaskType
        from app.domain.refunds import canonical_digest

        target = execution_context or context
        valid = (
            isinstance(business_context, MemoryBusinessContext)
            and context.agent_type is AgentType.KNOWLEDGE
            and context.task_type is TaskType.MEMORY_MANAGE
            and target.origin == "node"
            and target.agent_type is context.agent_type
            and target.task_type is context.task_type
            and target.node_name == "execute_memory_write"
            and context.node_name in ("prepare_memory_write", "execute_memory_write")
            and call.name == "write_preferences"
            and context.execution == target.execution
            and context.permission_scopes == target.permission_scopes
            and context.run_limits == target.run_limits == context.scope.limits
            and context.scope is target.scope
            and context.argument_constraints.get(call.name)
            == target.argument_constraints.get(call.name)
            and context.allowed_tools == target.allowed_tools
            and bool(context.thread_id)
            and context.thread_id == target.thread_id
            and business_context.user_id == context.execution.user_id
            and business_context.task_id == context.execution.task_id
            and business_context.run_id == context.execution.run_id
            and bool(business_context.operation_id)
            and type(business_context.expected_revision) is int
            and business_context.expected_revision >= 0
            and type(business_context.replay_check_only) is bool
            and (context.node_name != "execute_memory_write" or business_context.replay_check_only)
            and (
                context.node_name != "prepare_memory_write"
                or not business_context.replay_check_only
            )
        )
        definition, decision = self._evaluate(call, target)
        if (
            not valid
            or definition is None
            or target.allowed_tools != frozenset({(call.name, definition.metadata.version)})
            or definition.metadata.approval_required
            or definition.metadata.risk_level != "low"
            or definition.metadata.max_retries != 0
            or definition.metadata.read_only
            or not definition.metadata.has_business_side_effects
            or definition.metadata.idempotency != "operation_id_required"
        ):
            return self._result(
                call,
                context,
                status="policy_denied",
                code="tool_not_allowed",
                message="Tool call is not allowed.",
            )
        if decision.decision is not PolicyDecision.ALLOW:
            return self._denied(call, target, decision, 0, str(uuid4()))
        args = decision.validated_args.model_dump(mode="json")
        if target.argument_constraints.get(
            call.name
        ) != args or business_context.command_digest != canonical_digest(args):
            return self._result(
                call,
                context,
                status="policy_denied",
                code="invalid_tool_arguments",
                message="Tool call is not allowed.",
            )
        count = context.scope.run_usage().tool_calls
        return PreparedToolAttempt(
            str(uuid4()),
            context.execution.run_id,
            context.execution.task_id,
            call,
            definition.metadata.version,
            args,
            canonical_digest(args),
            business_context.operation_id,
            count,
            count + 1,
            min(definition.metadata.timeout_seconds, context.scope.remaining_active_seconds()),
            asdict(business_context),
            {
                "thread_id": context.thread_id,
                "scope_id": context.scope.scope_id,
                "limits": asdict(context.run_limits),
                "scopes_digest": canonical_digest({"scopes": sorted(context.permission_scopes)}),
                "call_digest": canonical_digest(asdict(call)),
            },
            "node",
            context.node_name,
            target.node_name,
        )

    async def execute_prepared(self, attempt, *, context):
        """Revalidate a same-run marker and fresh approval before the only write attempt."""
        import psycopg
        from psycopg_pool import PoolClosed, PoolTimeout

        from app.domain.refunds import canonical_digest
        from app.workflows.approvals import ApprovalError

        if attempt.origin == "node":
            return await self._execute_node_attempt(attempt, context)

        call = attempt.call
        definition = self.registry.get(call.name)
        business = context.refund_context
        if (
            definition is None
            or call.name != "refund_order"
            or context.origin != "model"
            or attempt.origin != "model"
            or attempt.prepared_by_node_name is not None
            or attempt.execution_node_name is not None
            or attempt.run_id != context.execution.run_id
            or attempt.task_id != context.execution.task_id
            or attempt.tool_version != definition.metadata.version
            or business is None
            or asdict(business) != attempt.business_snapshot
            or context.approval_binding is None
            or asdict(context.approval_binding) != attempt.binding_snapshot
            or business.operation_id != attempt.operation_id
            or attempt.args_digest != canonical_digest(attempt.normalized_args)
            or context.scope.run_usage().tool_calls != attempt.baseline_tool_calls
            or attempt.attempted_tool_calls != attempt.baseline_tool_calls + 1
            or attempt.timeout_seconds <= 0
            or attempt.timeout_seconds > definition.metadata.timeout_seconds
        ):
            return self._result(
                call,
                context,
                status="policy_denied",
                code="attempt_invalid",
                message="Tool attempt is invalid.",
            )
        # The typed values were validated before the sync boundary. Reconstruct that
        # trusted snapshot instead of validating or coercing model input a second time.
        typed = definition.args_schema.model_construct(**attempt.normalized_args)
        _, initial = self._evaluate(call, context, validated_args=typed)
        if initial.decision is PolicyDecision.DENY:
            return self._denied(call, context, initial, 0, str(uuid4()))
        if initial.validated_args.model_dump(mode="json") != attempt.normalized_args:
            return self._result(
                call,
                context,
                status="policy_denied",
                code="attempt_invalid",
                message="Tool attempt is invalid.",
            )
        try:
            verified = await self._verify_refund(call, context, definition, initial.validated_args)
        except (ApprovalError, ValueError):
            return self._result(
                call,
                context,
                status="policy_denied",
                code="approval_not_valid",
                message="Approval is not valid.",
            )
        except (psycopg.Error, PoolClosed, PoolTimeout):
            return self._result(
                call,
                context,
                status="failed",
                code="approval_unavailable",
                message="Approval is unavailable.",
            )
        _, checked = self._evaluate(
            call, context, validated_args=initial.validated_args, verified_approval=verified
        )
        result = await self._execute_checked(
            call,
            context,
            definition,
            checked,
            business_context=business,
            verified_approval=verified,
            attempt_timeout=attempt.timeout_seconds,
        )
        return self._record_args(result, checked)

    async def _execute_node_attempt(self, attempt, context):
        from app.domain.refunds import canonical_digest

        call = attempt.call
        definition = self.registry.get(call.name)
        try:
            business = MemoryBusinessContext(**attempt.business_snapshot)
        except (TypeError, ValueError):
            business = None
        if (
            definition is None
            or call.name != "write_preferences"
            or context.origin != "node"
            or context.node_name != "execute_memory_write"
            or attempt.execution_node_name != context.node_name
            or attempt.prepared_by_node_name not in ("prepare_memory_write", "execute_memory_write")
            or attempt.run_id != context.execution.run_id
            or attempt.task_id != context.execution.task_id
            or attempt.tool_version != definition.metadata.version
            or not context.thread_id
            or attempt.binding_snapshot
            != {
                "thread_id": context.thread_id,
                "scope_id": context.scope.scope_id,
                "limits": asdict(context.run_limits),
                "scopes_digest": canonical_digest({"scopes": sorted(context.permission_scopes)}),
                "call_digest": canonical_digest(asdict(call)),
            }
            or context.run_limits != context.scope.limits
            or definition.metadata.approval_required
            or definition.metadata.risk_level != "low"
            or definition.metadata.max_retries != 0
            or definition.metadata.read_only
            or not definition.metadata.has_business_side_effects
            or definition.metadata.idempotency != "operation_id_required"
            or business is None
            or business.user_id != context.execution.user_id
            or business.task_id != context.execution.task_id
            or business.run_id != context.execution.run_id
            or business.operation_id != attempt.operation_id
            or type(business.expected_revision) is not int
            or business.expected_revision < 0
            or type(business.replay_check_only) is not bool
            or business.command_digest != canonical_digest(attempt.normalized_args)
            or (attempt.prepared_by_node_name == "execute_memory_write")
            != business.replay_check_only
            or attempt.args_digest != canonical_digest(attempt.normalized_args)
            or context.scope.run_usage().tool_calls != attempt.baseline_tool_calls
            or attempt.attempted_tool_calls != attempt.baseline_tool_calls + 1
            or not 0 < attempt.timeout_seconds <= definition.metadata.timeout_seconds
            or context.allowed_tools != frozenset({(call.name, definition.metadata.version)})
            or context.argument_constraints.get(call.name) != attempt.normalized_args
        ):
            return self._result(
                call,
                context,
                status="policy_denied",
                code="attempt_invalid",
                message="Tool attempt is invalid.",
            )
        typed = definition.args_schema.model_construct(**attempt.normalized_args)
        _, checked = self._evaluate(call, context, validated_args=typed)
        result = await self._execute_checked(
            call,
            context,
            definition,
            checked,
            business_context=business,
            attempt_timeout=attempt.timeout_seconds,
        )
        return self._record_args(result, checked)

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
        if call.name == "write_preferences":
            return self._result(
                call,
                context,
                status="policy_denied",
                code="tool_not_allowed",
                message="Tool call is not allowed.",
            )
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

    async def _execute_checked(
        self,
        call,
        context,
        definition,
        initial,
        *,
        business_context=None,
        verified_approval=None,
        attempt_timeout=None,
    ):
        execution_id = str(uuid4())
        attempts = 0
        decision = initial
        if call.name == "write_preferences" and attempt_timeout is None:
            return self._result(
                call,
                context,
                status="policy_denied",
                code="tool_not_allowed",
                message="Tool call is not allowed.",
            )
        if decision.decision is not PolicyDecision.ALLOW:
            return self._denied(call, context, decision, attempts, execution_id)
        typed = decision.validated_args
        for retry in range(definition.metadata.max_retries + 1):
            if verified_approval is not None:
                import psycopg
                from psycopg_pool import PoolClosed, PoolTimeout

                from app.workflows.approvals import ApprovalError

                try:
                    verified_approval = await self._verify_refund(call, context, definition, typed)
                except (ApprovalError, ValueError):
                    return self._result(
                        call,
                        context,
                        status="policy_denied",
                        code="approval_not_valid",
                        message="Approval is not valid.",
                        attempts=attempts,
                        execution_id=execution_id,
                    )
                except (psycopg.Error, PoolClosed, PoolTimeout):
                    return self._result(
                        call,
                        context,
                        status="failed",
                        code="approval_unavailable",
                        message="Approval is unavailable.",
                        attempts=attempts,
                        execution_id=execution_id,
                    )
            current_definition, decision = self._evaluate(
                call, context, validated_args=typed, verified_approval=verified_approval
            )
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
            try:
                business = business_context or self._business_context(call, context)
            except ValueError:
                return self._result(
                    call,
                    context,
                    status="policy_denied",
                    code="tool_not_allowed",
                    message="Tool call is not allowed.",
                    attempts=attempts,
                    execution_id=execution_id,
                )
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
            timeout = min(definition.metadata.timeout_seconds, remaining)
            if attempt_timeout is not None:
                timeout = min(timeout, attempt_timeout)
            try:
                async with asyncio.timeout(timeout):
                    response = await definition.handler(typed, business)
            except TimeoutError:
                if call.name == "write_preferences":
                    from app.memory.models import MemoryMutationResult

                    return self._memory_unknown(
                        call,
                        context,
                        MemoryMutationResult(
                            status="unknown",
                            operation_id=business.operation_id,
                            revision=None,
                            changed_fields=[],
                            preferences=None,
                        ),
                        attempts,
                        execution_id,
                    )
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
            except ToolEffectUnknownError as error:
                return self._memory_unknown(call, context, error.data, attempts, execution_id)
            except ToolUnavailableError as error:
                return self._result(
                    call,
                    context,
                    status="failed",
                    code=error.code,
                    message="Tool execution unavailable.",
                    attempts=attempts,
                    effect_status=(
                        "not_started"
                        if isinstance(error, ToolNotStartedError)
                        else "not_applicable"
                        if definition.metadata.read_only
                        else "unknown"
                    ),
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
                    data=response.rejection.data.model_dump(mode="json")
                    if response.rejection.data is not None
                    else None,
                    effect_status="not_started"
                    if call.name == "write_preferences"
                    else "not_applicable",
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

    def _memory_unknown(self, call, context, data, attempts, execution_id):
        return self._result(
            call,
            context,
            status="failed",
            code="memory_result_unknown",
            message="本次偏好写入结果未知，请先核对，再提交新的记忆修改。",
            data=data.model_dump(mode="json"),
            attempts=attempts,
            effect_status="unknown",
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
