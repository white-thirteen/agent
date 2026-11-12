"""Per-Run serial budget coordination. Persist only the returned immutable snapshots."""

import asyncio
import time
from collections.abc import Callable

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
        self._model = model_usage
        self._baseline = run_usage
        self._tools = run_usage.tool_calls
        self._started: float | None = None
        self._finished: RunUsage | None = None
        self._deadline: asyncio.Timeout | None = None
        self._emit = emit

    def model_usage(self) -> ModelCallUsage:
        return self._model

    @property
    def limits(self) -> RunLimits:
        return self._limits

    def adopt_model_usage(self, updated: ModelCallUsage) -> None:
        if updated.model_attempts < self._model.model_attempts:
            raise ValueError("Model usage cannot decrease")
        self._model = updated

    def run_usage(self) -> RunUsage:
        if self._finished is not None:
            return self._finished
        elapsed = int((time.monotonic() - self._started) * 1000) if self._started is not None else 0
        return RunUsage(self._tools, self._baseline.active_elapsed_ms + elapsed)

    def adopt_tool_usage(self, updated: RunUsage) -> None:
        if updated.tool_calls < self._tools:
            raise ValueError("Tool usage cannot decrease")
        self._tools = updated.tool_calls

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
