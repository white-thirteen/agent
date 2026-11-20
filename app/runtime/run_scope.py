"""Per-Run serial budget coordination. Persist only the returned immutable snapshots."""

import asyncio
import time
from collections.abc import Callable
from uuid import uuid4

from app.runtime.model_gateway import ModelCallUsage
from app.runtime.models import RunLimits, RunUsage


class RunScope:
    def __init__(
        self,
        *,
        limits: RunLimits,
        model_usage: ModelCallUsage,
        run_usage: RunUsage,
        emit: Callable[[str], None] = lambda code: None,
    ):
        self._limits = limits
        self._scope_id = str(uuid4())
        self._model = model_usage
        self._baseline = run_usage
        self._tools = run_usage.tool_calls
        self._started: float | None = None
        self._finished: RunUsage | None = None
        self._deadline: asyncio.Timeout | None = None
        self._emit = emit
        self._context_view = None
        self._selector_receipts = []
        self._selector_pending = None
        self.selection_reservation = None
        self.context_history_override = None

    def record_context_view(self, view):
        self._context_view = view

    def record_context_usage(self, usage):
        if self._context_view is not None:
            from dataclasses import asdict

            self._context_view = {**self._context_view, "provider_usage": asdict(usage)}

    @property
    def selector_receipts(self):
        return list(self._selector_receipts)

    def adopt_selector_receipts(self, receipts):
        """Merge Task receipts by stable ID when restoring a committed state."""
        existing = {item["id"]: item for item in self._selector_receipts}
        for receipt in receipts:
            prior = existing.get(receipt["id"])
            if prior is not None and prior != receipt:
                raise ValueError("Selector receipt mismatch")
            if prior is None:
                self._selector_receipts.append(receipt)
                existing[receipt["id"]] = receipt

    async def start_selector_receipt(self, task_id, run_id):
        self._selector_pending = {
            "id": str(uuid4()),
            "task_id": task_id,
            "run_id": run_id,
            "status": "pending_unknown",
            "provider_calls": None,
            "usage": None,
            "reserved_attempts": None,
            "error_code": None,
        }
        self._selector_initial_attempts = self._model.model_attempts
        self._selector_provider_calls = 0
        self.adopt_selector_receipts([self._selector_pending])
        if self.selection_reservation is not None:
            await self.selection_reservation.record_receipts(self._selector_receipts)

    def note_selector_provider_call(self):
        self._selector_provider_calls += 1

    def record_selector_usage(self, usage):
        from dataclasses import asdict

        self._selector_pending["usage"] = asdict(usage)

    async def finish_selector_receipt(self, status, error_code):
        if self._selector_pending is None:
            return
        receipt = self._selector_pending
        self._selector_pending = None
        receipt["provider_calls"] = self._selector_provider_calls
        receipt["reserved_attempts"] = self._model.model_attempts - self._selector_initial_attempts
        receipt["status"] = status if self._selector_provider_calls else "not_started"
        receipt["error_code"] = error_code
        if not self._selector_provider_calls:
            receipt["usage"] = None
        if self.selection_reservation is not None:
            await self.selection_reservation.record_receipts(self._selector_receipts)

    @property
    def context_view(self):
        return self._context_view

    def model_usage(self) -> ModelCallUsage:
        return self._model

    @property
    def limits(self) -> RunLimits:
        return self._limits

    @property
    def scope_id(self) -> str:
        return self._scope_id

    def adopt_model_usage(self, updated: ModelCallUsage) -> None:
        if updated.model_attempts < self._model.model_attempts:
            raise ValueError("Model usage cannot decrease")
        self._model = updated

    async def begin_selection(self, rediscoveries: int) -> None:
        if self.selection_reservation is not None:
            await self.selection_reservation.begin(self._model.model_attempts, rediscoveries)

    async def record_selection_outcome(self, record, status) -> None:
        if self.selection_reservation is not None:
            await self.selection_reservation.record_outcome(record, status)

    async def reserve_model_attempt(self, updated: ModelCallUsage) -> None:
        if self.selection_reservation is not None:
            await self.selection_reservation.reserve_attempt(updated.model_attempts)

    def run_usage(self) -> RunUsage:
        if self._finished is not None:
            return self._finished
        elapsed = int((time.monotonic() - self._started) * 1000) if self._started is not None else 0
        return RunUsage(self._tools, self._baseline.active_elapsed_ms + elapsed)

    def adopt_tool_usage(self, updated: RunUsage) -> None:
        if updated.tool_calls < self._tools:
            raise ValueError("Tool usage cannot decrease")
        self._tools = updated.tool_calls

    def inherit_attempt_elapsed(self, elapsed_ms: int) -> None:
        """A lost result may have spent the entire persisted attempt timeout."""
        current = self.run_usage().active_elapsed_ms
        if elapsed_ms > current:
            self._baseline = RunUsage(
                self._baseline.tool_calls,
                self._baseline.active_elapsed_ms + elapsed_ms - current,
            )

    def remaining_active_seconds(self) -> float:
        return self._limits.active_timeout_seconds - self.run_usage().active_elapsed_ms / 1000

    def budget_exhausted(self) -> bool:
        return self.remaining_active_seconds() <= 0 or self._tools >= self._limits.max_tool_calls

    def bind_deadline(self, deadline: asyncio.Timeout | None) -> None:
        self._deadline = deadline

    def start_active_period(self) -> None:
        self._started = time.monotonic()

    def finish_active_period(self) -> RunUsage:
        if self._finished is None:
            self._finished = self.run_usage()
            # Final checkpoint commit is cleanup, outside the already frozen active period.
            if self._deadline is not None:
                self._deadline.reschedule(None)
        return self._finished

    @property
    def finished(self) -> bool:
        return self._finished is not None

    def abort_active_period(self) -> None:
        """Freeze confirmed local usage after failure, without retrying graph settlement."""
        self._deadline = None
        if self._finished is None:
            self._finished = self.run_usage()

    def emit_status(self, code: str) -> None:
        self._emit(code)
