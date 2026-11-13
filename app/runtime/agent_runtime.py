"""Single-process admission and independent execution, with task-owned checkpoint budgets."""

import asyncio
import logging
import time
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from math import ceil
from uuid import uuid4

from langchain_core.messages import ToolMessage
from langgraph.types import Command, StateSnapshot
from pydantic import ValidationError

from app.core.errors import AgentNotReadyError, RuntimeRequestError
from app.graph.contracts import (
    ExecutionContext,
    GraphProtocolError,
    PendingTask,
    SpecialistInput,
    SpecialistResult,
)
from app.graph.state import create_turn_state
from app.runtime.context import (
    DemoContext,
    RefundRecoveryContext,
    RunExecutionContext,
    SubmitOptions,
)
from app.runtime.model_gateway import ModelCallUsage
from app.runtime.models import (
    ResumeAcceptance,
    RunHandle,
    RunLimits,
    RunRecord,
    RunStatus,
    RunUsage,
    RunView,
    TaskStatus,
    TaskView,
)
from app.runtime.refund_checkpoint import classify_refund_checkpoint
from app.runtime.run_scope import RunScope
from app.streaming.events import RuntimeEvent
from app.streaming.subscription import EventSubscription, SubscriptionOwner

logger = logging.getLogger(__name__)


def _pending_contradicts(snapshot, call_id):
    values = snapshot.values
    result = values.get("tool_result")
    result_status = (
        result.get("status") if isinstance(result, dict) else getattr(result, "status", None)
    )
    return (
        bool(values.get("execution_result"))
        or values.get("outcome") == "completed"
        or result_status == "success"
        or any(
            isinstance(message, ToolMessage)
            and message.tool_call_id == call_id
            and message.status == "success"
            for message in values.get("messages", [])
        )
        or snapshot.next[0] not in {"recheck_execution", "prepare_refund_attempt", "execute_refund"}
    )


class AgentRuntime:
    def __init__(
        self,
        graph=None,
        *,
        run_limits: RunLimits,
        queue_capacity: int = 64,
        max_active_runs: int = 8,
        retained_runs: int = 100,
        result_ttl_seconds: float = 1800,
        shutdown_grace_seconds: float = 5,
        approval_service=None,
        refund_service=None,
        scope_resolver=None,
    ):
        self._graph = graph
        self._limits = run_limits
        self._queue_capacity = queue_capacity
        self._max_active = max_active_runs
        self._retained = retained_runs
        self._ttl = result_ttl_seconds
        self._grace = shutdown_grace_seconds
        self._approval_service = approval_service
        self._refund_service = refund_service
        self._scope_resolver = scope_resolver
        self._records: dict[str, RunRecord] = {}
        self._requests: dict[tuple, str] = {}
        self._claims: dict[str, object] = {}
        self._uncertain: set[str] = set()
        self._stopping = False

    @property
    def is_ready(self) -> bool:
        return self._graph is not None and not self._stopping

    async def _inspect_refund_checkpoint(self, approval, application, *, audit=False):
        """Read the current nested snapshot; classification itself never advances a run."""
        if self._graph is None:
            raise AgentNotReadyError()
        try:
            thread_id = approval["subject_snapshot"]["thread_id"]
            root = await self._graph.aget_state(
                {"configurable": {"thread_id": thread_id}}, subgraphs=True
            )

            async def expand(snapshot, visited):
                tasks = []
                for task in snapshot.tasks:
                    child = task.state
                    if isinstance(child, dict):
                        config = child.get("configurable", {})
                        key = (
                            config.get("thread_id"),
                            config.get("checkpoint_ns"),
                            config.get("checkpoint_id"),
                        )
                        if key in visited or not key[1]:
                            child = None
                        else:
                            visited.add(key)
                            child = await self._graph.aget_state(child, subgraphs=True)
                    if isinstance(child, StateSnapshot):
                        child = await expand(child, visited)
                    tasks.append(task._replace(state=child))
                return snapshot._replace(tasks=tuple(tasks))

            root = await expand(root, set())
            if audit:
                # The original audit pointer must resolve exactly. A latest snapshot
                # in the same namespace cannot prove that historical association.
                child = await self._graph.aget_state(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": approval["checkpoint_ns"],
                            "checkpoint_id": approval["checkpoint_id"],
                        }
                    },
                    subgraphs=True,
                )
                if (
                    child.config is None
                    or child.config["configurable"].get("checkpoint_id")
                    != approval["checkpoint_id"]
                    or len(root.tasks) != 1
                ):
                    raise RuntimeRequestError("approval_binding_conflict")
                root = root._replace(tasks=(root.tasks[0]._replace(state=child),))
        except RuntimeRequestError:
            raise
        except (KeyError, TypeError):
            raise RuntimeRequestError("state_unavailable") from None
        except Exception as error:
            logger.warning("State read failed category=%s", type(error).__name__)
            raise RuntimeRequestError("state_unavailable") from None
        return classify_refund_checkpoint(root, approval, application)

    async def repair_approval_binding(self, reference, *, actor):
        """Bind an existing, uniquely verified interrupt without starting a new Run."""
        import psycopg
        from psycopg_pool import PoolClosed, PoolTimeout

        from app.workflows.approvals import ApprovalActor, ApprovalError, InterruptBindingRequest

        if not isinstance(actor, ApprovalActor):
            raise RuntimeRequestError("approval_binding_conflict")
        if self._stopping:
            raise RuntimeRequestError("runtime_stopping")
        if self._graph is None or self._approval_service is None:
            raise RuntimeRequestError("approval_binding_unavailable")
        try:
            approval, application = await self._approval_service.get_application(
                reference.approval_id
            )
        except ApprovalError as error:
            code = (
                "approval_not_found"
                if error.code == "approval_not_found"
                else "approval_binding_conflict"
            )
            raise RuntimeRequestError(code) from None
        except (psycopg.Error, PoolClosed, PoolTimeout):
            raise RuntimeRequestError("approval_binding_unavailable") from None
        thread = approval["subject_snapshot"]["thread_id"]
        if thread in self._claims:
            raise RuntimeRequestError("thread_busy")
        token = object()
        self._claims[thread] = token
        try:
            try:
                approval, application = await self._approval_service.get_application(
                    reference.approval_id
                )
            except ApprovalError as error:
                code = (
                    "approval_not_found"
                    if error.code == "approval_not_found"
                    else "approval_binding_conflict"
                )
                raise RuntimeRequestError(code) from None
            except (psycopg.Error, PoolClosed, PoolTimeout):
                raise RuntimeRequestError("approval_binding_unavailable") from None
            if approval["subject_snapshot"]["thread_id"] != thread:
                raise RuntimeRequestError("approval_binding_conflict")
            inspected = await self._inspect_refund_checkpoint(approval, application)
            if inspected.kind != "pending":
                raise RuntimeRequestError("approval_binding_conflict")
            if inspected.bound:
                audit = await self._inspect_refund_checkpoint(approval, application, audit=True)
                if audit.kind != "pending" or not audit.bound:
                    raise RuntimeRequestError("approval_binding_conflict")
            elif approval["decision"] != "PENDING":
                raise RuntimeRequestError("approval_binding_conflict")
            binding = InterruptBindingRequest(
                inspected.interrupt_id,
                inspected.checkpoint_ns,
                approval["checkpoint_id"] if inspected.bound else inspected.checkpoint_id,
                approval["subject_digest"],
                approval["decision"],
            )
            try:
                await self._approval_service.bind_interrupt(reference.approval_id, binding)
            except ApprovalError:
                raise RuntimeRequestError("approval_binding_conflict") from None
            except (psycopg.Error, PoolClosed, PoolTimeout):
                raise RuntimeRequestError("approval_binding_unavailable") from None
            return {
                "approval_id": reference.approval_id,
                "binding_status": "bound",
                "repaired": not inspected.bound,
            }
        finally:
            self._release(thread, token)

    async def resume_approval(self, reference, *, actor):
        """Admit an original approval continuation under the existing thread gate."""
        import psycopg
        from psycopg_pool import PoolClosed, PoolTimeout

        from app.domain.refunds import OriginalRefundCall, RefundRejected, canonical_digest
        from app.tools.models import PreparedToolAttempt
        from app.workflows.approvals import ApprovalActor, ApprovalError

        if not isinstance(actor, ApprovalActor):
            raise RuntimeRequestError("approval_binding_conflict")
        if self._stopping:
            raise RuntimeRequestError("runtime_stopping")
        if self._graph is None or self._approval_service is None or self._scope_resolver is None:
            raise RuntimeRequestError("approval_resume_unavailable")
        try:
            approval, application = await self._approval_service.get_application(
                reference.approval_id
            )
        except ApprovalError as error:
            code = (
                "approval_not_found"
                if error.code == "approval_not_found"
                else "approval_binding_conflict"
            )
            raise RuntimeRequestError(code) from None
        except (psycopg.Error, PoolClosed, PoolTimeout):
            raise RuntimeRequestError("approval_resume_unavailable") from None
        subject = approval["subject_snapshot"]
        thread = subject["thread_id"]
        if thread in self._claims:
            active = next(
                (
                    item
                    for item in self._records.values()
                    if item.context.thread_id == thread
                    and item.context.user_id == subject["user_id"]
                    and item.context.conversation_id == subject["conversation_id"]
                    and item.execution.context.task_id == subject["task_id"]
                    and item.run_status is RunStatus.RUNNING
                ),
                None,
            )
            if active:
                return ResumeAcceptance(
                    False,
                    active.context.run_id,
                    subject["task_id"],
                    subject["operation_id"],
                    "running",
                )
            raise RuntimeRequestError("thread_busy")
        if len(self._claims) >= self._max_active:
            raise RuntimeRequestError("runtime_busy")
        token = object()
        self._claims[thread] = token
        accepted = False
        try:
            try:
                approval, application = await self._approval_service.get_application(
                    reference.approval_id
                )
            except ApprovalError:
                raise RuntimeRequestError("approval_binding_conflict") from None
            except (psycopg.Error, PoolClosed, PoolTimeout):
                raise RuntimeRequestError("approval_resume_unavailable") from None
            subject = approval["subject_snapshot"]
            if subject["thread_id"] != thread:
                raise RuntimeRequestError("approval_binding_conflict")
            state = await self._inspect_refund_checkpoint(approval, application)
            if state.kind == "ended":
                return ResumeAcceptance(
                    False,
                    None,
                    subject["task_id"],
                    subject["operation_id"],
                    state.result.status,
                    state.result,
                )
            if state.kind not in ("pending", "post_gate") or not state.bound:
                raise RuntimeRequestError("execution_uncertain")
            child = state.child.values
            try:
                model_usage = ModelCallUsage(**child["model_call_usage"])
                run_usage = RunUsage(**child["run_usage"])
                if (
                    type(model_usage.model_attempts) is not int
                    or model_usage.model_attempts < 0
                    or type(run_usage.tool_calls) is not int
                    or run_usage.tool_calls < 0
                    or type(run_usage.active_elapsed_ms) is not int
                    or run_usage.active_elapsed_ms < 0
                ):
                    raise ValueError("Invalid child usage")
            except (KeyError, TypeError, ValueError):
                raise RuntimeRequestError("execution_uncertain") from None
            recovery = None
            complete_usage = True
            if state.kind == "post_gate":
                if self._refund_service is None:
                    raise RuntimeRequestError("execution_uncertain")
                try:
                    operation = await self._refund_service.get_operation(
                        user_id=subject["user_id"], operation_id=subject["operation_id"]
                    )
                except (psycopg.Error, PoolClosed, PoolTimeout, RefundRejected):
                    raise RuntimeRequestError("execution_uncertain") from None
                if (
                    not operation
                    or operation["application_id"] != subject["application_id"]
                    or operation["status"] not in ("SUCCEEDED", "PENDING")
                ):
                    raise RuntimeRequestError("execution_uncertain")
                marker = child.get("prepared_attempt")
                if marker is None and operation["status"] == "SUCCEEDED":
                    complete_usage = False
                if marker is not None:
                    try:
                        if (
                            not isinstance(marker, PreparedToolAttempt)
                            or marker.task_id != subject["task_id"]
                            or marker.call.call_id != subject["call_id"]
                            or marker.call.name != subject["tool_name"]
                            or marker.call.raw_args != application["raw_args"]
                            or marker.tool_version != subject["tool_version"]
                            or marker.normalized_args != subject["canonical_args"]
                            or marker.args_digest != canonical_digest(subject["canonical_args"])
                            or marker.operation_id != subject["operation_id"]
                            or marker.origin != "model"
                            or marker.prepared_by_node_name is not None
                            or marker.execution_node_name is not None
                            or marker.attempted_tool_calls != marker.baseline_tool_calls + 1
                            or marker.business_snapshot.get("user_id") != subject["user_id"]
                            or marker.business_snapshot.get("conversation_id")
                            != subject["conversation_id"]
                            or marker.business_snapshot.get("thread_id") != thread
                            or marker.business_snapshot.get("task_id") != subject["task_id"]
                            or marker.business_snapshot.get("workflow_id") != subject["workflow_id"]
                            or marker.business_snapshot.get("operation_id")
                            != subject["operation_id"]
                            or marker.business_snapshot.get("application_id")
                            != subject["application_id"]
                            or marker.business_snapshot.get("approval_id") != reference.approval_id
                            or marker.business_snapshot.get("run_id") != marker.run_id
                            or marker.business_snapshot.get("expected_call_digest")
                            != canonical_digest(
                                {
                                    "call_id": subject["call_id"],
                                    "name": subject["tool_name"],
                                    "version": subject["tool_version"],
                                    "args": subject["canonical_args"],
                                }
                            )
                            or marker.binding_snapshot.get("interrupt_id")
                            != approval["interrupt_id"]
                            or marker.binding_snapshot.get("checkpoint_ns")
                            != approval["checkpoint_ns"]
                            or marker.binding_snapshot.get("checkpoint_id")
                            != approval["checkpoint_id"]
                        ):
                            raise ValueError("Invalid marker association")
                        attempts = marker.attempted_tool_calls
                        timeout = marker.timeout_seconds
                        if (
                            type(attempts) is not int
                            or attempts < 0
                            or not 0 < timeout <= self._limits.active_timeout_seconds
                        ):
                            raise ValueError("Invalid marker budget")
                        run_usage = RunUsage(
                            max(run_usage.tool_calls, attempts),
                            run_usage.active_elapsed_ms + ceil(timeout * 1000),
                        )
                        complete_usage = False
                    except (AttributeError, TypeError, ValueError):
                        raise RuntimeRequestError("execution_uncertain") from None
                disposition = "succeeded" if operation["status"] == "SUCCEEDED" else "not_executed"
                if disposition == "not_executed" and _pending_contradicts(
                    state.child, subject["call_id"]
                ):
                    raise RuntimeRequestError("execution_uncertain")
                # Only the saved execute boundary bounds the possibly active handler window.
                if disposition == "not_executed" and (
                    marker is None or state.child.next != ("execute_refund",)
                ):
                    raise RuntimeRequestError("execution_uncertain")
                if disposition == "not_executed" and (
                    run_usage.tool_calls >= self._limits.max_tool_calls
                    or run_usage.active_elapsed_ms >= self._limits.active_timeout_seconds * 1000
                ):
                    raise RuntimeRequestError("execution_uncertain")
                original = OriginalRefundCall(
                    application["call_id"],
                    application["tool_name"],
                    application["tool_version"],
                    application["raw_args"],
                    application["canonical_args"],
                )
                recovery = RefundRecoveryContext(
                    thread,
                    subject["task_id"],
                    subject["workflow_id"],
                    subject["application_id"],
                    reference.approval_id,
                    subject["operation_id"],
                    subject["call_id"],
                    original.call_digest(),
                    state.checkpoint_ns,
                    state.checkpoint_id,
                    marker.attempt_id if marker else None,
                    disposition,
                    operation["execution_result"] if disposition == "succeeded" else None,
                    marker is not None
                    and state.child.next in (("execute_refund",), ("record_tool_outcome",)),
                )
            try:
                await self._approval_service.prepare_resume(
                    reference.approval_id,
                    interrupt_id=approval["interrupt_id"],
                    checkpoint_ns=approval["checkpoint_ns"],
                )
            except ApprovalError as error:
                code = (
                    "approval_pending"
                    if error.code == "approval_pending"
                    else "approval_binding_conflict"
                )
                raise RuntimeRequestError(code) from None
            except (psycopg.Error, PoolClosed, PoolTimeout):
                raise RuntimeRequestError("approval_resume_unavailable") from None
            if self._stopping:
                raise RuntimeRequestError("runtime_stopping")
            try:
                previous_run_id = SpecialistInput.model_validate(child["request"]).context.run_id
            except (KeyError, TypeError, ValueError):
                raise RuntimeRequestError("execution_uncertain") from None
            run_id = str(uuid4())
            trusted = ExecutionContext(
                user_id=subject["user_id"],
                conversation_id=subject["conversation_id"],
                task_id=subject["task_id"],
                workflow_id=subject["workflow_id"],
                run_id=run_id,
            )
            scopes = self._scope_resolver(subject["user_id"])
            context = DemoContext(
                subject["user_id"], subject["conversation_id"], thread, run_id, "", scopes
            )
            record = None
            scope = RunScope(
                limits=self._limits,
                model_usage=model_usage,
                run_usage=run_usage,
                emit=lambda code: self._progress(record, code),
            )
            execution = RunExecutionContext(
                trusted,
                thread,
                scopes,
                scope,
                "resume" if state.kind == "pending" else "reconcile",
                recovery,
            )
            record = RunRecord(context, execution, None, ("", "approval_resume"), datetime.now(UTC))
            record.usage_complete = complete_usage
            self._records[run_id] = record
            graph_input = (
                Command(resume={state.interrupt_id: {"approval_id": reference.approval_id}})
                if state.kind == "pending"
                else None
            )
            coroutine = self._execute(record, graph_input, token)
            try:
                record.task = asyncio.create_task(coroutine, name=f"agent-run:{run_id}")
            except BaseException:
                coroutine.close()
                self._records.pop(run_id, None)
                raise
            record.task.add_done_callback(lambda task: self._task_done(record, token, task))
            self._publish(record, "workflow_resumed", {"previous_run_id": previous_run_id})
            accepted = True
            return ResumeAcceptance(
                True, run_id, subject["task_id"], subject["operation_id"], "running"
            )
        finally:
            if not accepted:
                self._release(thread, token)

    async def can_resume_approval(self, reference):
        """Read-only current eligibility; admission rechecks everything under the gate."""
        import psycopg
        from psycopg_pool import PoolClosed, PoolTimeout

        from app.domain.refunds import RefundRejected, canonical_digest
        from app.tools.models import PreparedToolAttempt
        from app.workflows.approvals import ApprovalError

        if (
            self._stopping
            or self._graph is None
            or self._approval_service is None
            or self._scope_resolver is None
        ):
            return False
        try:
            approval, application = await self._approval_service.get_application(
                reference.approval_id
            )
            thread = approval["subject_snapshot"]["thread_id"]
            if thread in self._claims or len(self._claims) >= self._max_active:
                return False
            self._scope_resolver(approval["subject_snapshot"]["user_id"])
            inspected = await self._inspect_refund_checkpoint(approval, application)
            if not inspected.bound or inspected.kind not in ("pending", "post_gate"):
                return False
            child_values = inspected.child.values
            model_usage = ModelCallUsage(**child_values["model_call_usage"])
            run_usage = RunUsage(**child_values["run_usage"])
            SpecialistInput.model_validate(child_values["request"])
            if (
                type(model_usage.model_attempts) is not int
                or model_usage.model_attempts < 0
                or type(run_usage.tool_calls) is not int
                or run_usage.tool_calls < 0
                or type(run_usage.active_elapsed_ms) is not int
                or run_usage.active_elapsed_ms < 0
            ):
                return False
            if approval["decision"] == "PENDING" and approval["expires_at"] > approval["db_now"]:
                return False
            if inspected.kind == "post_gate":
                if self._refund_service is None:
                    return False
                subject = approval["subject_snapshot"]
                operation = await self._refund_service.get_operation(
                    user_id=subject["user_id"], operation_id=subject["operation_id"]
                )
                if (
                    not operation
                    or operation["application_id"] != subject["application_id"]
                    or operation["status"] not in ("SUCCEEDED", "PENDING")
                ):
                    return False
                marker = inspected.child.values.get("prepared_attempt")
                if marker is not None and (
                    not isinstance(marker, PreparedToolAttempt)
                    or marker.task_id != subject["task_id"]
                    or marker.call.call_id != subject["call_id"]
                    or marker.call.name != subject["tool_name"]
                    or marker.call.raw_args != application["raw_args"]
                    or marker.tool_version != subject["tool_version"]
                    or marker.normalized_args != subject["canonical_args"]
                    or marker.args_digest != canonical_digest(subject["canonical_args"])
                    or marker.operation_id != subject["operation_id"]
                    or marker.origin != "model"
                    or marker.prepared_by_node_name is not None
                    or marker.execution_node_name is not None
                    or marker.attempted_tool_calls != marker.baseline_tool_calls + 1
                    or marker.business_snapshot.get("user_id") != subject["user_id"]
                    or marker.business_snapshot.get("conversation_id") != subject["conversation_id"]
                    or marker.business_snapshot.get("thread_id") != thread
                    or marker.business_snapshot.get("task_id") != subject["task_id"]
                    or marker.business_snapshot.get("workflow_id") != subject["workflow_id"]
                    or marker.business_snapshot.get("operation_id") != subject["operation_id"]
                    or marker.business_snapshot.get("application_id") != subject["application_id"]
                    or marker.business_snapshot.get("approval_id") != reference.approval_id
                    or marker.business_snapshot.get("run_id") != marker.run_id
                    or marker.business_snapshot.get("expected_call_digest")
                    != canonical_digest(
                        {
                            "call_id": subject["call_id"],
                            "name": subject["tool_name"],
                            "version": subject["tool_version"],
                            "args": subject["canonical_args"],
                        }
                    )
                    or marker.binding_snapshot.get("interrupt_id") != approval["interrupt_id"]
                    or marker.binding_snapshot.get("checkpoint_ns") != approval["checkpoint_ns"]
                    or marker.binding_snapshot.get("checkpoint_id") != approval["checkpoint_id"]
                    or type(marker.attempted_tool_calls) is not int
                    or marker.attempted_tool_calls < 0
                    or not 0 < marker.timeout_seconds <= self._limits.active_timeout_seconds
                ):
                    return False
                if operation["status"] == "PENDING":
                    if _pending_contradicts(inspected.child, subject["call_id"]):
                        return False
                    if marker is None or inspected.child.next != ("execute_refund",):
                        return False
                    usage = inspected.child.values["run_usage"]
                    count = usage["tool_calls"]
                    elapsed = usage["active_elapsed_ms"]
                    if marker is not None:
                        if (
                            not isinstance(marker, PreparedToolAttempt)
                            or marker.operation_id != subject["operation_id"]
                            or marker.task_id != subject["task_id"]
                            or marker.call.call_id != subject["call_id"]
                            or marker.normalized_args != subject["canonical_args"]
                            or not 0 < marker.timeout_seconds <= self._limits.active_timeout_seconds
                        ):
                            return False
                        count = max(count, marker.attempted_tool_calls)
                        elapsed += ceil(marker.timeout_seconds * 1000)
                    if (
                        count >= self._limits.max_tool_calls
                        or elapsed >= self._limits.active_timeout_seconds * 1000
                    ):
                        return False
            return True
        except ApprovalError:
            raise RuntimeRequestError("approval_binding_conflict") from None
        except (psycopg.Error, PoolClosed, PoolTimeout):
            raise RuntimeRequestError("approval_resume_unavailable") from None
        except (KeyError, TypeError, ValueError, AttributeError):
            return False
        except RefundRejected:
            return False

    async def submit(
        self,
        context: DemoContext,
        *,
        options: SubmitOptions,
        subscription_owner: SubscriptionOwner | None = None,
    ) -> RunHandle:
        self._prune()
        if self._stopping:
            raise RuntimeRequestError("runtime_stopping")
        if self._graph is None:
            raise AgentNotReadyError()
        key = (context.user_id, context.conversation_id, options.request_id)
        fingerprint = (context.message, options.input_mode)
        previous = self._requests.get(key) if options.request_id is not None else None
        if previous is not None:
            record = self._records[previous]
            if record.context.thread_id != context.thread_id:
                raise RuntimeRequestError("run_not_found")
            if record.fingerprint != fingerprint:
                raise RuntimeRequestError("request_id_conflict")
            subscription = self._attach(record, subscription_owner) if subscription_owner else None
            return self._handle(record, subscription)
        thread = context.thread_id
        if thread in self._uncertain:
            raise RuntimeRequestError("execution_uncertain")
        if thread in self._claims:
            raise RuntimeRequestError("thread_busy")
        if len(self._claims) >= self._max_active:
            raise RuntimeRequestError("runtime_busy")
        token = object()
        self._claims[thread] = token
        accepted = False
        record = None
        try:
            saved = await self._load_state(
                user_id=context.user_id, conversation_id=context.conversation_id, thread_id=thread
            )
            if self._stopping:
                raise RuntimeRequestError("runtime_stopping")
            mode = self._input_mode(saved, options)
            task_id = saved["task_id"] if mode == "continue" else str(uuid4())
            trusted = ExecutionContext(
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                task_id=task_id,
                workflow_id=task_id,
                run_id=context.run_id,
            )
            prepared = create_turn_state(trusted, context.message, task_mode=mode, saved_task=saved)
            scope = RunScope(
                limits=self._limits,
                model_usage=ModelCallUsage(**prepared["model_call_usage"]),
                run_usage=RunUsage(**prepared["run_usage"]),
                emit=lambda code: self._progress(record, code),
            )
            execution = RunExecutionContext(trusted, thread, context.permission_scopes, scope)
            record = RunRecord(
                context, execution, options.request_id, fingerprint, datetime.now(UTC)
            )
            # No awaits from registration through owner adoption, task creation and return.
            self._records[context.run_id] = record
            if options.request_id is not None:
                self._requests[key] = context.run_id
            subscription = self._attach(record, subscription_owner) if subscription_owner else None
            coroutine = self._execute(record, prepared, token)
            try:
                record.task = asyncio.create_task(coroutine, name=f"agent-run:{context.run_id}")
            except BaseException:
                coroutine.close()
                raise
            record.task.add_done_callback(lambda task: self._task_done(record, token, task))
            accepted = True
            return self._handle(record, subscription)
        finally:
            if not accepted:
                if record is not None:
                    if record.subscription is not None:
                        record.subscription.close()
                    self._records.pop(context.run_id, None)
                    if options.request_id is not None:
                        self._requests.pop(key, None)
                self._release(thread, token)

    def _input_mode(self, saved, options):
        if not saved:
            return "new"
        status = TaskStatus(saved["task_status"])
        if status in (TaskStatus.WAITING_APPROVAL, TaskStatus.PAUSED):
            raise RuntimeRequestError("task_blocked")
        if status is TaskStatus.FAILED and options.input_mode == "auto":
            raise RuntimeRequestError("explicit_new_task_required")
        if status is TaskStatus.NEEDS_INPUT and options.input_mode == "auto":
            return "continue"
        return "new"

    async def _load_state(self, *, user_id, conversation_id, thread_id):
        try:
            snapshot = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        except Exception as error:
            logger.warning("State read failed category=%s", type(error).__name__)
            raise RuntimeRequestError("state_unavailable") from None
        if snapshot.next or getattr(snapshot, "interrupts", ()):
            self._uncertain.add(thread_id)
            raise RuntimeRequestError("execution_uncertain")
        saved = snapshot.values
        if not saved:
            return None
        try:
            trusted = ExecutionContext(**{key: saved[key] for key in ExecutionContext.model_fields})
            if trusted.user_id != user_id or trusted.conversation_id != conversation_id:
                raise ValueError("State owner mismatch")
            status = TaskStatus(saved["task_status"])
            if status is TaskStatus.RUNNING:
                self._uncertain.add(thread_id)
                raise RuntimeRequestError("execution_uncertain")
            for name, fields in (
                ("model_call_usage", ("model_attempts",)),
                ("run_usage", ("tool_calls", "active_elapsed_ms")),
            ):
                values = saved[name]
                if set(values) != set(fields) or any(
                    type(values[key]) is not int or values[key] < 0 for key in fields
                ):
                    raise ValueError("Invalid usage snapshot")
            if status is TaskStatus.NEEDS_INPUT:
                pending = PendingTask.model_validate(saved["pending_task"])
                for key in ("user_id", "conversation_id", "task_id", "workflow_id"):
                    if getattr(pending, key) != getattr(trusted, key):
                        raise ValueError("Invalid pending association")
                if not isinstance(saved["task_message_ids"], list):
                    raise ValueError("Invalid task message scope")
        except (KeyError, TypeError, ValueError, ValidationError):
            raise RuntimeRequestError("state_unavailable") from None
        return saved

    async def _execute(self, record, prepared, token):
        scope = record.execution.scope
        scope.start_active_period()
        try:
            if (
                scope.remaining_active_seconds() <= 0
                and record.execution.execution_mode == "normal"
            ):
                raise TimeoutError
            async with asyncio.timeout(None) as deadline:
                remaining = scope.remaining_active_seconds()
                # Exhausted recovery may only perform guarded reconciliation and closure.
                # Its wall-clock cleanup bound grants no additional execution budget.
                deadline.reschedule(
                    asyncio.get_running_loop().time()
                    + (remaining if remaining > 0 else self._limits.active_timeout_seconds)
                )
                scope.bind_deadline(deadline)
                result = await self._graph.ainvoke(
                    prepared,
                    {"configurable": {"thread_id": record.context.thread_id}},
                    context=record.execution,
                    durability="sync",
                )
                if result.get("__interrupt__"):
                    await self._finalize_approval_pause(record, result["__interrupt__"])
                    return
                actual = ExecutionContext(
                    **{key: result[key] for key in ExecutionContext.model_fields}
                )
                if actual != record.execution.context or not scope.finished:
                    raise GraphProtocolError("Graph did not commit an ordinary run finish")
                if result["model_call_usage"] != asdict(scope.model_usage()) or result[
                    "run_usage"
                ] != asdict(scope.run_usage()):
                    raise GraphProtocolError("Graph returned inconsistent budget settlement")
                status = TaskStatus(result["task_status"])
                if status not in (
                    TaskStatus.COMPLETED,
                    TaskStatus.REJECTED,
                    TaskStatus.NEEDS_INPUT,
                    TaskStatus.FAILED,
                ):
                    raise GraphProtocolError("Graph returned a nonordinary result")
                record.task_status = status
                record.run_status = {
                    TaskStatus.NEEDS_INPUT: RunStatus.WAITING_INPUT,
                    TaskStatus.FAILED: RunStatus.FAILED,
                }.get(status, RunStatus.COMPLETED)
                record.final_answer = result.get("final_answer")
                record.sources = [
                    source.model_dump(mode="json") for source in result.get("sources", [])
                ]
                record.error = result.get("error")
                if record.execution.execution_mode in ("resume", "reconcile"):
                    self._uncertain.discard(record.context.thread_id)
                self._finalize(record)
        except asyncio.CancelledError:
            self._fail_uncertain(record, "run_interrupted")
        except TimeoutError:
            self._fail_uncertain(record, "budget_exceeded")
        except Exception as error:
            logger.error(
                "Run failed run_id=%s task_id=%s category=%s",
                record.context.run_id,
                record.execution.context.task_id,
                type(error).__name__,
            )
            self._fail_uncertain(record, "agent_execution_failed")
        finally:
            self._release(record.context.thread_id, token)

    async def _finalize_approval_pause(self, record, interrupts):
        """Publish waiting only after reading and binding the real child interrupt."""
        from app.workflows.approvals import InterruptBindingRequest

        if (
            self._approval_service is None
            or len(interrupts) != 1
            or not record.execution.scope.finished
        ):
            self._fail_uncertain(record, "pause_binding_unavailable")
            return
        interrupt = interrupts[0]
        payload = interrupt.value
        try:
            if not isinstance(payload, dict) or payload.get("kind") != "refund_approval":
                raise ValueError("Unexpected interrupt")
            approval_id = payload["approval_id"]
            approval, application = await self._approval_service.get_application(approval_id)
            subject = approval["subject_snapshot"]
            if (
                subject["thread_id"] != record.context.thread_id
                or subject["user_id"] != record.context.user_id
                or subject["conversation_id"] != record.context.conversation_id
                or subject["task_id"] != record.execution.context.task_id
            ):
                raise ValueError("Interrupt association mismatch")
            inspected = await self._inspect_refund_checkpoint(approval, application)
            if inspected.kind != "pending" or inspected.interrupt_id != interrupt.id:
                raise ValueError("Interrupt checkpoint mismatch")
            if not inspected.bound:
                await self._approval_service.bind_interrupt(
                    approval_id,
                    InterruptBindingRequest(
                        inspected.interrupt_id,
                        inspected.checkpoint_ns,
                        inspected.checkpoint_id,
                        approval["subject_digest"],
                        approval["decision"],
                    ),
                )
        except Exception as error:
            logger.warning("Approval pause binding failed category=%s", type(error).__name__)
            self._fail_uncertain(record, "pause_binding_unavailable")
            return
        record.task_status = TaskStatus.WAITING_APPROVAL
        record.run_status = RunStatus.WAITING_APPROVAL
        self._publish(
            record,
            "workflow_paused",
            {
                "application_id": subject["application_id"],
                "approval_id": approval_id,
                "reason": "waiting_approval",
            },
        )
        self._finalize(record)

    def _fail_uncertain(self, record, code):
        if record.ended_at is not None:
            return
        self._uncertain.add(record.context.thread_id)
        record.execution.scope.abort_active_period()
        record.usage_complete = False
        record.task_status = TaskStatus.FAILED
        record.run_status = RunStatus.FAILED
        record.final_answer = None
        record.sources = []
        record.error = {"code": code, "message": "Execution requires reconciliation."}
        self._finalize(record)

    def _finalize(self, record):
        if record.ended_at is not None:
            return
        record.ended_at = datetime.now(UTC)
        record.finished_at = time.monotonic()
        self._publish(
            record, "status", {"run_status": record.run_status, "task_status": record.task_status}
        )
        if record.final_answer:
            self._publish(record, "token", {"content": record.final_answer})
        if record.error:
            self._publish(
                record, "error", {**record.error, "usage_complete": record.usage_complete}
            )
        self._publish(
            record, "done", {"run_status": record.run_status, "task_status": record.task_status}
        )
        self._prune()

    def _task_done(self, record, token, task):
        # A task cancelled before its first step never enters _execute's finally.
        if task.cancelled() and record.ended_at is None:
            self._fail_uncertain(record, "run_interrupted")
        self._release(record.context.thread_id, token)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Run cleanup failure category=%s", type(task.exception()).__name__)

    def _release(self, thread, token):
        if self._claims.get(thread) is token:
            del self._claims[thread]

    def _handle(self, record, subscription):
        task_id = record.execution.context.task_id
        return RunHandle(record.context.run_id, task_id, task_id, subscription)

    def _event(self, record, kind, data):
        record.sequence += 1
        return RuntimeEvent(
            kind, record.context.run_id, record.execution.context.task_id, record.sequence, data
        )

    def _publish(self, record, kind, data):
        event = self._event(record, kind, data)
        if record.subscription is not None:
            record.subscription.publish(event)

    def _progress(self, record, code):
        if code in ("routing",):
            self._publish(
                record,
                "status",
                {"code": code, "run_status": record.run_status, "task_status": record.task_status},
            )

    def _attach(self, record, owner):
        if record.subscription is not None:
            raise RuntimeRequestError(
                "subscription_exists", status_url=f"/agent/runs/{record.context.run_id}/status"
            )

        def detach(subscription_id):
            if (
                record.subscription is not None
                and record.subscription.subscription_id == subscription_id
            ):
                if record.subscription.slow:
                    logger.warning(
                        "Subscription closed code=subscriber_slow run_id=%s task_id=%s",
                        record.context.run_id,
                        record.execution.context.task_id,
                    )
                record.subscription = None

        subscription = EventSubscription(self._queue_capacity, detach)
        record.subscription = subscription
        owner.adopt(subscription)
        view = self._view(record)
        payload = asdict(view)
        payload["started_at"] = view.started_at.isoformat()
        payload["ended_at"] = view.ended_at.isoformat() if view.ended_at else None
        subscription.publish(
            self._event(
                record,
                "status",
                {
                    "snapshot": True,
                    "view": payload,
                    "run_status": record.run_status,
                    "task_status": record.task_status,
                },
            )
        )
        if record.ended_at is not None:
            subscription.publish(
                self._event(
                    record,
                    "done",
                    {"run_status": record.run_status, "task_status": record.task_status},
                )
            )
        return subscription

    def _view(self, record):
        task_id = record.execution.context.task_id
        return RunView(
            record.context.run_id,
            task_id,
            task_id,
            record.run_status,
            record.task_status,
            record.final_answer,
            deepcopy(record.sources),
            deepcopy(record.error),
            record.execution.scope.model_usage(),
            record.execution.scope.run_usage(),
            record.usage_complete,
            record.started_at,
            record.ended_at,
        )

    def _find(self, *, user_id, conversation_id, run_id):
        self._prune()
        record = self._records.get(run_id)
        if record is None or (record.context.user_id, record.context.conversation_id) != (
            user_id,
            conversation_id,
        ):
            raise RuntimeRequestError("run_not_found")
        return record

    async def get_run(self, *, user_id, conversation_id, run_id) -> RunView:
        return self._view(
            self._find(user_id=user_id, conversation_id=conversation_id, run_id=run_id)
        )

    async def subscribe(
        self, *, user_id, conversation_id, run_id, subscription_owner: SubscriptionOwner
    ) -> EventSubscription:
        return self._attach(
            self._find(user_id=user_id, conversation_id=conversation_id, run_id=run_id),
            subscription_owner,
        )

    async def get_state(self, *, user_id, conversation_id, thread_id) -> TaskView | None:
        for record in self._records.values():
            if record.context.thread_id == thread_id and record.run_status is RunStatus.RUNNING:
                if (record.context.user_id, record.context.conversation_id) != (
                    user_id,
                    conversation_id,
                ):
                    raise RuntimeRequestError("run_not_found")
                view = self._view(record)
                return TaskView(
                    view.task_id,
                    view.workflow_id,
                    view.task_status,
                    view.run_id,
                    view.model_call_usage,
                    view.run_usage,
                )
        saved = await self._load_state(
            user_id=user_id, conversation_id=conversation_id, thread_id=thread_id
        )
        if saved is None:
            return None
        return TaskView(
            saved["task_id"],
            saved["workflow_id"],
            TaskStatus(saved["task_status"]),
            saved["run_id"],
            ModelCallUsage(**saved["model_call_usage"]),
            RunUsage(**saved["run_usage"]),
            "execution_uncertain" if thread_id in self._uncertain else None,
        )

    async def _query_checkpoint(self, *, user_id, conversation_id, thread_id):
        if self._graph is None:
            raise AgentNotReadyError()
        try:
            snapshot = await self._graph.aget_state(
                {"configurable": {"thread_id": thread_id}}, subgraphs=True
            )
        except Exception as error:
            logger.warning("State read failed category=%s", type(error).__name__)
            raise RuntimeRequestError("state_unavailable") from None
        values = snapshot.values
        if values:
            try:
                trusted = ExecutionContext(
                    **{key: values[key] for key in ExecutionContext.model_fields}
                )
            except (KeyError, TypeError, ValueError, ValidationError):
                raise RuntimeRequestError("state_unavailable") from None
            if (trusted.user_id, trusted.conversation_id) != (user_id, conversation_id):
                raise RuntimeRequestError("run_not_found")
        return snapshot

    async def current_task(self, *, user_id, conversation_id, thread_id):
        snapshot = await self._query_checkpoint(
            user_id=user_id, conversation_id=conversation_id, thread_id=thread_id
        )
        values = snapshot.values
        active = next(
            (
                record
                for record in self._records.values()
                if record.context.thread_id == thread_id and record.run_status is RunStatus.RUNNING
            ),
            None,
        )
        if active and (active.context.user_id, active.context.conversation_id) != (
            user_id,
            conversation_id,
        ):
            raise RuntimeRequestError("run_not_found")
        if not values:
            if not active:
                return None
            return {
                "task_id": active.execution.context.task_id,
                "workflow_id": active.execution.context.workflow_id,
                "task_status": active.task_status,
                "run_id": active.context.run_id,
                "refund": None,
                "blocking_reason": None,
            }
        status = active.task_status if active else values.get("task_status")
        refund = None
        blocking_reason = None
        if not active and snapshot.next:
            status = "paused"
            blocking_reason = "execution_uncertain"
            child = next(
                (task.state for task in snapshot.tasks if isinstance(task.state, StateSnapshot)),
                None,
            )
            if child is None and len(snapshot.tasks) == 1:
                child_config = snapshot.tasks[0].state
                if isinstance(child_config, dict):
                    try:
                        child = await self._graph.aget_state(child_config, subgraphs=True)
                    except Exception as error:
                        logger.warning("State read failed category=%s", type(error).__name__)
                        raise RuntimeRequestError("state_unavailable") from None
            if child and child.interrupts and self._approval_service:
                import psycopg
                from psycopg_pool import PoolClosed, PoolTimeout

                from app.workflows.approvals import ApprovalError

                try:
                    approval, application = await self._approval_service.get_application(
                        child.values["approval_id"]
                    )
                    classified = await self._inspect_refund_checkpoint(approval, application)
                    if classified.kind == "pending" and classified.bound:
                        status = "waiting_approval"
                        blocking_reason = None
                        subject = approval["subject_snapshot"]
                        refund = {
                            "application_id": subject["application_id"],
                            "operation_id": subject["operation_id"],
                            "approval_id": str(approval["approval_id"]),
                            "amount": subject["amount"],
                            "currency": subject["currency"],
                            "approval_decision": approval["decision"],
                        }
                    else:
                        blocking_reason = "execution_uncertain"
                except (ApprovalError, KeyError):
                    blocking_reason = "execution_uncertain"
                except (psycopg.Error, PoolClosed, PoolTimeout):
                    raise RuntimeRequestError("state_unavailable") from None
        elif not active and status == "running":
            status = "paused"
            blocking_reason = "execution_uncertain"
        elif not active and values.get("specialist_result"):
            try:
                result = SpecialistResult.model_validate(values["specialist_result"])
            except ValidationError:
                raise RuntimeRequestError("state_unavailable") from None
            if result.agent_type.value == "refund":
                refund = {
                    "application_id": None,
                    "operation_id": result.operation_id,
                    "approval_id": result.approval_id,
                    "summary": result.summary,
                }
        try:
            status = TaskStatus(status)
        except (TypeError, ValueError):
            raise RuntimeRequestError("state_unavailable") from None
        return {
            "task_id": values.get("task_id"),
            "workflow_id": values.get("workflow_id"),
            "task_status": status,
            "run_id": active.context.run_id if active else None,
            "refund": refund,
            "blocking_reason": blocking_reason,
        }

    async def refund_status(self, *, user_id, conversation_id, thread_id, application_id):
        import psycopg
        from psycopg_pool import PoolClosed, PoolTimeout

        from app.domain.refunds import RefundRejected

        if self._refund_service is None:
            raise AgentNotReadyError()
        try:
            result = await self._refund_service.get_application_status(
                user_id=user_id, conversation_id=conversation_id, application_id=application_id
            )
        except (psycopg.Error, PoolClosed, PoolTimeout):
            raise RuntimeRequestError("state_unavailable") from None
        except RefundRejected:
            raise RuntimeRequestError("execution_uncertain") from None
        if not result or result.get("thread_id") != thread_id:
            raise RuntimeRequestError("run_not_found")
        return {key: value for key, value in result.items() if key != "thread_id"}

    def _prune(self):
        now = time.monotonic()
        terminal = sorted(
            (record for record in self._records.values() if record.finished_at is not None),
            key=lambda record: record.finished_at,
        )
        excess = max(0, len(terminal) - self._retained)
        for index, record in enumerate(terminal):
            if index >= excess and now - record.finished_at < self._ttl:
                continue
            if record.subscription is not None:
                record.subscription.close()
            self._records.pop(record.context.run_id, None)
            if record.request_id is not None:
                self._requests.pop(
                    (record.context.user_id, record.context.conversation_id, record.request_id),
                    None,
                )

    async def shutdown(self) -> None:
        self._stopping = True
        tasks = [
            record.task
            for record in self._records.values()
            if record.task is not None and not record.task.done()
        ]
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=self._grace)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        for record in self._records.values():
            if record.subscription is not None:
                record.subscription.close()
