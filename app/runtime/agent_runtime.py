"""Single-process admission and independent execution, with task-owned checkpoint budgets."""

import asyncio
import logging
import time
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from app.core.errors import AgentNotReadyError, RuntimeRequestError
from app.graph.contracts import ExecutionContext, GraphProtocolError, PendingTask
from app.graph.state import create_turn_state
from app.runtime.context import DemoContext, RunExecutionContext, SubmitOptions
from app.runtime.model_gateway import ModelCallUsage
from app.runtime.models import (
    RunHandle,
    RunLimits,
    RunRecord,
    RunStatus,
    RunUsage,
    RunView,
    TaskStatus,
    TaskView,
)
from app.runtime.run_scope import RunScope
from app.streaming.events import RuntimeEvent
from app.streaming.subscription import EventSubscription, SubscriptionOwner

logger = logging.getLogger(__name__)


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
    ):
        self._graph = graph
        self._limits = run_limits
        self._queue_capacity = queue_capacity
        self._max_active = max_active_runs
        self._retained = retained_runs
        self._ttl = result_ttl_seconds
        self._grace = shutdown_grace_seconds
        self._records: dict[str, RunRecord] = {}
        self._requests: dict[tuple, str] = {}
        self._claims: dict[str, object] = {}
        self._uncertain: set[str] = set()
        self._stopping = False

    @property
    def is_ready(self) -> bool:
        return self._graph is not None and not self._stopping

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
            async with asyncio.timeout(None) as deadline:
                if not scope.budget_exhausted():
                    deadline.reschedule(
                        asyncio.get_running_loop().time() + scope.remaining_active_seconds()
                    )
                scope.bind_deadline(deadline)
                result = await self._graph.ainvoke(
                    prepared,
                    {"configurable": {"thread_id": record.context.thread_id}},
                    context=record.execution,
                    durability="sync",
                )
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
