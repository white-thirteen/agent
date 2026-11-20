"""Task-scoped selector consumption checkpoints, separate from Graph node completion."""

from langgraph.checkpoint.base import empty_checkpoint

from app.tools.discovery import selection_digest


class SelectionReservation:
    """Persist in-flight attempt floors through the existing Saver public API."""

    def __init__(self, saver, *, thread_id, owner, run_id, source_checkpoint_id):
        self.saver = saver
        self.owner = owner
        self.run_id = run_id
        self.source_checkpoint_id = source_checkpoint_id
        self.config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "v203-reservation:" + owner["task_id"],
            }
        }
        self.value = None

    async def load(self, snapshot, *, reconcile_original=False):
        state = snapshot.values
        saved = await self.saver.aget_tuple(self.config)
        if saved is None:
            return
        self.value = saved.checkpoint["channel_values"]
        self.config = saved.config
        if any(self.value.get(k) != v for k, v in self.owner.items()):
            raise ValueError("Selection reservation owner mismatch")
        if self.value["inflight"] and reconcile_original:
            if selection_digest(state.get("tool_selection_record")) != self.value.get(
                "outcome_digest"
            ):
                raise ValueError("Original selection association mismatch")
            return
        if self.value["inflight"]:
            self.config = saved.config
            await self.confirm(snapshot)
            if self.value["inflight"]:
                raise ValueError("Selection reservation result is unknown")
        if self.value["source"] != (self.source_checkpoint_id or ""):
            raise ValueError("Selection reservation checkpoint mismatch")
        if state["model_call_usage"]["model_attempts"] < self.value["attempts"]:
            raise ValueError("Selection reservation usage mismatch")
        record = state.get("tool_selection_record") or {}
        if record.get("rediscovery_count", 0) < self.value["rediscoveries"]:
            raise ValueError("Selection reservation count mismatch")

    async def _write(self):
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = self.value.copy()
        versions = {key: checkpoint["id"] for key in self.value}
        checkpoint["channel_versions"] = versions
        self.config = await self.saver.aput(
            self.config, checkpoint, {"source": "update", "step": -1, "parents": {}}, versions
        )

    async def begin(self, attempts, rediscoveries):
        if self.value is not None and (
            attempts < self.value["attempts"] or rediscoveries < self.value["rediscoveries"]
        ):
            raise ValueError("Selection reservation cannot decrease")
        receipts = self.value.get("selector_receipts", []) if self.value else []
        self.value = {
            **self.owner,
            "selector_receipts": receipts,
            "source": self.source_checkpoint_id or "",
            "attempts": attempts,
            "rediscoveries": rediscoveries,
            "inflight": True,
            "run_id": self.run_id,
            "outcome_digest": "",
        }
        await self._write()

    async def begin_existing(self, attempts, *, reconcile_original=False):
        if (
            self.value is None
            or (self.value["inflight"] and not reconcile_original)
            or attempts < self.value["attempts"]
        ):
            raise ValueError("Selection reservation cannot resume")
        self.value["attempts"] = attempts
        self.value["source"] = self.source_checkpoint_id or ""
        self.value["run_id"] = self.run_id
        self.value["inflight"] = True
        await self._write()

    async def confirm_pause(self, child_values, *, root_checkpoint_id):
        from app.graph.contracts import SpecialistInput

        request = SpecialistInput.model_validate(child_values["request"])
        if (
            any(getattr(request.context, key) != value for key, value in self.owner.items())
            or request.context.run_id != self.value["run_id"]
            or selection_digest(child_values.get("tool_selection_record"))
            != self.value["outcome_digest"]
            or child_values.get("model_call_usage", {}).get("model_attempts", -1)
            < self.value["attempts"]
            or (child_values.get("tool_selection_record") or {}).get("rediscovery_count", 0)
            < self.value["rediscoveries"]
        ):
            raise ValueError("Approval selection result not committed")
        self.value["source"] = root_checkpoint_id
        self.value["inflight"] = False
        await self._write()

    async def record_outcome(self, record, status):
        if self.value is not None and self.value["inflight"]:
            self.value["outcome_digest"] = selection_digest(
                record.model_dump(mode="json") if record is not None else None
            )
            self.value["outcome_status"] = status
            await self._write()

    async def record_receipts(self, receipts):
        if self.value is not None and self.value["inflight"]:
            self.value["selector_receipts"] = receipts
            await self._write()

    async def reserve_attempt(self, attempts):
        if self.value is not None and self.value["inflight"]:
            if attempts <= self.value["attempts"]:
                raise ValueError("Model attempt reservation must increase")
            self.value["attempts"] = attempts
            await self._write()

    async def confirm(self, snapshot):
        if self.value is None or not self.value["inflight"]:
            return
        state = snapshot.values
        record = state.get("tool_selection_record") or {}
        if (
            snapshot.next
            or not self.value.get("outcome_digest")
            or state.get("run_id") != self.value["run_id"]
            or selection_digest(state.get("tool_selection_record")) != self.value["outcome_digest"]
            or (
                self.value["outcome_status"] not in ("selected", "no_tool")
                and state.get("task_status") not in ("failed", "rejected")
            )
            or any(state.get(k) != v for k, v in self.owner.items())
            or state.get("model_call_usage", {}).get("model_attempts", -1) < self.value["attempts"]
            or record.get("rediscovery_count", 0) < self.value["rediscoveries"]
        ):
            raise ValueError("Selection result not committed")
        self.value["source"] = snapshot.config["configurable"]["checkpoint_id"]
        self.value["inflight"] = False
        await self._write()
