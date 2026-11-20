"""Controlled progressive tool selection with short-circuiting, reuse, and budget gating."""

import json
import time
from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.types import AgentType, TaskType
from app.graph.contracts import ExecutionContext
from app.runtime.model_gateway import ModelCallContext, ModelCallError, ModelGateway
from app.runtime.run_scope import RunScope
from app.tools.discovery import (
    PurposeSpec,
    SelectedToolEntry,
    ToolSelectionRecord,
    candidates_digest,
    filter_discoverable_briefs,
    scope_digest,
    selection_digest,
)
from app.tools.models import ToolBindingRecord, ToolBrief
from app.tools.registry import ToolRegistry

SELECTOR_SYSTEM_PROMPT = (
    "You are a strict tool selector. Select only from the provided candidate tool names "
    "based on the user's need and trusted purpose. Do not invent tool names, parameters, "
    "or answers. Return structured output only."
)


class SelectorOutput(BaseModel):
    """Structured tool-selection response; never carries arguments or execution instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["use_tools", "no_tool"]
    tool_names: list[str]

    @model_validator(mode="after")
    def validate_selection(self) -> "SelectorOutput":
        if self.action == "no_tool":
            if self.tool_names:
                raise ValueError("no_tool action must have empty tool_names")
            return self
        if not self.tool_names:
            raise ValueError("use_tools action requires at least one tool name")
        if any(not isinstance(name, str) or not name.strip() for name in self.tool_names):
            raise ValueError("Tool names must be nonblank strings")
        if len(set(self.tool_names)) != len(self.tool_names):
            raise ValueError("Tool names must be unique")
        return self


@dataclass(frozen=True, slots=True)
class ToolSelectionOutcome:
    status: Literal["selected", "no_tool", "rejected", "failed"]
    record: ToolSelectionRecord | None = None
    binding: ToolBindingRecord | None = None
    error_code: str | None = None
    method: Literal["deterministic", "singleton", "model", "none"] | None = None
    reused: bool = False
    selector_called: bool = False


class ToolSelector:
    """Short-circuiting, budget-checked, bounded-rediscovery tool selector."""

    def __init__(
        self,
        registry: ToolRegistry,
        gateway: ModelGateway | None = None,
        *,
        max_selector_attempts: int = 2,
        selector_timeout_seconds: float = 15.0,
        max_rediscoveries: int = 1,
    ):
        if max_selector_attempts < 1 or selector_timeout_seconds <= 0 or max_rediscoveries < 0:
            raise ValueError("Invalid ToolSelector configuration")
        self._registry = registry
        self._gateway = gateway
        self._max_selector_attempts = max_selector_attempts
        self._selector_timeout_seconds = selector_timeout_seconds
        self._max_rediscoveries = max_rediscoveries

    async def select(self, **kwargs) -> ToolSelectionOutcome:
        outcome = await self._select(**kwargs)
        locked = kwargs.get("has_pending_calls", False) or kwargs.get(
            "waiting_approval_or_unknown", False
        )
        if not locked:
            await kwargs["scope"].finish_selector_receipt(outcome.status, outcome.error_code)
            if outcome.status == "selected" and outcome.record is not None:
                # Even reuse and deterministic selection precede a business model call.
                await kwargs["scope"].begin_selection(outcome.record.rediscovery_count)
            await kwargs["scope"].record_selection_outcome(outcome.record, outcome.status)
        return outcome

    async def _select(
        self,
        *,
        execution: ExecutionContext,
        agent_type: AgentType,
        task_type: TaskType,
        purpose_spec: PurposeSpec,
        permission_scopes: frozenset[str],
        scope: RunScope,
        need_text: str,
        deterministic_target: str | None = None,
        existing_record: dict | ToolSelectionRecord | None = None,
        has_pending_calls: bool = False,
        waiting_approval_or_unknown: bool = False,
        business_calls_reserved: int = 1,
        business_timeout_per_call: float | None = None,
        required_processing_seconds: float = 0,
        require_tool: bool | None = None,
    ) -> ToolSelectionOutcome:
        # This bound starts before any rediscovery or attempt reservation write.
        selector_deadline = time.monotonic() + self._selector_timeout_seconds
        if business_calls_reserved < 1 or required_processing_seconds < 0:
            raise ValueError("Invalid business reservation")
        if existing_record is None and (has_pending_calls or waiting_approval_or_unknown):
            return ToolSelectionOutcome(status="failed", error_code="tool_selection_missing")
        effective_require_tool = purpose_spec.require_tool if require_tool is None else require_tool
        briefs = filter_discoverable_briefs(
            self._registry,
            purpose_spec=purpose_spec,
            permission_scopes=permission_scopes,
            agent_type=agent_type,
            task_type=task_type,
        )
        need_d = selection_digest(need_text)
        scope_d = scope_digest(permission_scopes)
        cand_d = candidates_digest(briefs)
        cat_ver = self._registry.catalog_version

        generation = 1
        rediscovery_count = 0
        failure_record = None

        if existing_record is not None:
            try:
                rec = (
                    existing_record
                    if isinstance(existing_record, ToolSelectionRecord)
                    else ToolSelectionRecord.model_validate(existing_record)
                )
            except Exception:
                return ToolSelectionOutcome(status="failed", error_code="tool_selection_invalid")

            same_owner = (
                rec.user_id == execution.user_id
                and rec.conversation_id == execution.conversation_id
                and rec.task_id == execution.task_id
                and rec.agent_type is agent_type
                and rec.task_type is task_type
            )
            if not same_owner:
                return ToolSelectionOutcome(status="failed", error_code="tool_selection_mismatch")

            if has_pending_calls or waiting_approval_or_unknown:
                # Forbid rediscovery or tool replacement while calls/approvals/unknowns are active.
                if (
                    rec.purpose != purpose_spec.purpose
                    or rec.catalog_version != cat_ver
                    or rec.rules_version != purpose_spec.rules_version
                ):
                    return ToolSelectionOutcome(status="failed", error_code="tool_selection_stale")
                if not rec.selected:
                    return ToolSelectionOutcome(
                        status="no_tool",
                        record=rec,
                        method=rec.method,
                        reused=True,
                    )
                try:
                    binding = self._registry.resolve_binding(
                        selected=rec.selected_tools,
                        agent_type=agent_type,
                        permission_scopes=permission_scopes,
                        discoverable_only=True,
                        allowed_names=purpose_spec.allowed_tools,
                        expected_catalog_version=rec.catalog_version,
                    )
                except ValueError:
                    return ToolSelectionOutcome(status="rejected", error_code="tool_not_allowed")
                if any(
                    binding.schema_digests.get(entry.name) != entry.schema_digest
                    for entry in rec.selected
                ):
                    return ToolSelectionOutcome(status="failed", error_code="tool_selection_stale")
                return ToolSelectionOutcome(
                    status="selected",
                    record=rec,
                    binding=binding,
                    method=rec.method,
                    reused=True,
                )

            same_context = (
                rec.purpose == purpose_spec.purpose
                and rec.need_digest == need_d
                and rec.scope_digest == scope_d
                and rec.candidates_digest == cand_d
                and rec.catalog_version == cat_ver
                and rec.rules_version == purpose_spec.rules_version
            )
            if same_context:
                if not rec.selected:
                    if not effective_require_tool:
                        return ToolSelectionOutcome(
                            status="no_tool",
                            record=rec,
                            method=rec.method,
                            reused=True,
                        )
                else:
                    try:
                        binding = self._registry.resolve_binding(
                            selected=rec.selected_tools,
                            agent_type=agent_type,
                            permission_scopes=permission_scopes,
                            discoverable_only=True,
                            allowed_names=purpose_spec.allowed_tools,
                            expected_catalog_version=rec.catalog_version,
                        )
                    except ValueError:
                        binding = None
                    if binding is not None and all(
                        binding.schema_digests.get(entry.name) == entry.schema_digest
                        for entry in rec.selected
                    ):
                        return ToolSelectionOutcome(
                            status="selected",
                            record=rec,
                            binding=binding,
                            method=rec.method,
                            reused=True,
                        )

            if rec.rediscovery_count >= self._max_rediscoveries:
                return ToolSelectionOutcome(
                    status="failed", error_code="rediscovery_limit_exceeded"
                )
            generation = rec.generation + 1
            rediscovery_count = rec.rediscovery_count + 1
            failure_record = rec.model_copy(update={"rediscovery_count": rediscovery_count})
            await scope.begin_selection(rediscovery_count)

        def build_record(
            selected_names: list[str],
            binding: ToolBindingRecord | None,
            method: Literal["deterministic", "singleton", "model", "none"],
        ) -> ToolSelectionRecord:
            brief_map = {b.name: b for b in briefs}
            entries = [
                SelectedToolEntry(
                    name=name,
                    version=brief_map[name].version,
                    schema_digest=binding.schema_digests[name],
                )
                for name in selected_names
            ]
            return ToolSelectionRecord(
                user_id=execution.user_id,
                conversation_id=execution.conversation_id,
                task_id=execution.task_id,
                agent_type=agent_type,
                task_type=task_type,
                purpose=purpose_spec.purpose,
                need_digest=need_d,
                scope_digest=scope_d,
                candidates_digest=cand_d,
                catalog_version=cat_ver,
                rules_version=purpose_spec.rules_version,
                selected=entries,
                method=method,
                generation=generation,
                rediscovery_count=rediscovery_count,
            )

        if deterministic_target is not None:
            match = next((b for b in briefs if b.name == deterministic_target), None)
            if match is None:
                definition = self._registry.get(deterministic_target)
                if definition is not None and definition.metadata.enabled:
                    return ToolSelectionOutcome(
                        status="rejected", record=failure_record, error_code="tool_not_allowed"
                    )
                return ToolSelectionOutcome(
                    status="failed", record=failure_record, error_code="capability_unavailable"
                )
            binding = self._registry.resolve_binding(
                selected=[(match.name, match.version)],
                agent_type=agent_type,
                permission_scopes=permission_scopes,
                discoverable_only=True,
                allowed_names=purpose_spec.allowed_tools,
                expected_catalog_version=cat_ver,
            )
            record = build_record([match.name], binding, "deterministic")
            return ToolSelectionOutcome(
                status="selected",
                record=record,
                binding=binding,
                method="deterministic",
            )

        if not briefs:
            if not effective_require_tool:
                record = build_record([], None, "none")
                return ToolSelectionOutcome(status="no_tool", record=record, method="none")
            return ToolSelectionOutcome(
                status="failed", record=failure_record, error_code="capability_unavailable"
            )

        if len(briefs) == 1:
            only = briefs[0]
            binding = self._registry.resolve_binding(
                selected=[(only.name, only.version)],
                agent_type=agent_type,
                permission_scopes=permission_scopes,
                discoverable_only=True,
                allowed_names=purpose_spec.allowed_tools,
                expected_catalog_version=cat_ver,
            )
            record = build_record([only.name], binding, "singleton")
            return ToolSelectionOutcome(
                status="selected",
                record=record,
                binding=binding,
                method="singleton",
            )

        # Multi-candidate model selection: budget pre-check before any Selector call.
        if self._gateway is None:
            return ToolSelectionOutcome(
                status="failed", record=failure_record, error_code="capability_unavailable"
            )

        remaining_attempts = self._gateway.limits.max_attempts - scope.model_usage().model_attempts
        granted_attempts = min(
            self._max_selector_attempts, remaining_attempts - business_calls_reserved
        )
        if granted_attempts < 1:
            return ToolSelectionOutcome(
                status="failed", record=failure_record, error_code="model_limit_exceeded"
            )

        per_call_biz_timeout = (
            business_timeout_per_call
            if business_timeout_per_call is not None
            else self._gateway.limits.timeout_seconds
        )
        reserved_seconds = (
            business_calls_reserved * per_call_biz_timeout + required_processing_seconds
        )
        available_seconds = scope.remaining_active_seconds() - reserved_seconds
        if available_seconds <= 0:
            return ToolSelectionOutcome(
                status="failed", record=failure_record, error_code="model_limit_exceeded"
            )

        # The Run allowance may be tighter than the already fixed Selector bound.
        selector_deadline = min(selector_deadline, time.monotonic() + available_seconds)
        if failure_record is None:
            await scope.begin_selection(rediscovery_count)
        provider_calls = 0
        await scope.start_selector_receipt(execution.task_id, execution.run_id)

        def note_provider_call():
            nonlocal provider_calls
            provider_calls += 1
            scope.note_selector_provider_call()

        payload = self._format_selector_payload(
            purpose_spec=purpose_spec, need_text=need_text, briefs=briefs
        )
        messages = [
            SystemMessage(content=SELECTOR_SYSTEM_PROMPT),
            HumanMessage(content=payload),
        ]
        try:
            result = await self._gateway.invoke_structured(
                messages,
                schema=SelectorOutput,
                context=ModelCallContext(
                    run_id=execution.run_id,
                    task_id=execution.task_id,
                    agent_type=agent_type,
                    deadline_monotonic=selector_deadline,
                    on_attempt=scope.adopt_model_usage,
                    before_attempt=scope.reserve_model_attempt,
                    remaining_call_seconds=lambda: (
                        scope.remaining_active_seconds() - reserved_seconds
                    ),
                    on_provider_call=note_provider_call,
                    on_context_usage=scope.record_selector_usage,
                    history=(),
                    reserved_attempts=business_calls_reserved,
                    max_call_attempts=granted_attempts,
                ),
                model_usage=scope.model_usage(),
            )
            scope.adopt_model_usage(result.model_usage)
        except ModelCallError as error:
            scope.adopt_model_usage(error.model_usage)
            return ToolSelectionOutcome(
                status="failed",
                record=failure_record,
                error_code=error.code,
                selector_called=provider_calls > 0,
            )

        parsed = result.parsed
        if not isinstance(parsed, SelectorOutput):
            return ToolSelectionOutcome(
                status="failed",
                record=failure_record,
                error_code="selector_output_invalid",
                selector_called=True,
            )
        if parsed.action == "no_tool":
            if effective_require_tool:
                return ToolSelectionOutcome(
                    status="failed",
                    record=failure_record,
                    error_code="selector_output_invalid",
                    selector_called=True,
                )
            record = build_record([], None, "model")
            return ToolSelectionOutcome(
                status="no_tool", record=record, method="model", selector_called=True
            )

        brief_by_name = {b.name: b for b in briefs}
        if len(parsed.tool_names) > purpose_spec.max_selected_tools or any(
            name not in brief_by_name for name in parsed.tool_names
        ):
            return ToolSelectionOutcome(
                status="failed",
                record=failure_record,
                error_code="selector_output_invalid",
                selector_called=True,
            )

        try:
            binding = self._registry.resolve_binding(
                selected=[(name, brief_by_name[name].version) for name in parsed.tool_names],
                agent_type=agent_type,
                permission_scopes=permission_scopes,
                discoverable_only=True,
                allowed_names=purpose_spec.allowed_tools,
                expected_catalog_version=cat_ver,
            )
        except ValueError:
            return ToolSelectionOutcome(
                status="failed",
                record=failure_record,
                error_code="selector_output_invalid",
                selector_called=True,
            )

        record = build_record(list(parsed.tool_names), binding, "model")
        return ToolSelectionOutcome(
            status="selected",
            record=record,
            binding=binding,
            method="model",
            selector_called=True,
        )

    @staticmethod
    def _format_selector_payload(
        *, purpose_spec: PurposeSpec, need_text: str, briefs: tuple[ToolBrief, ...]
    ) -> str:
        return json.dumps(
            {
                "purpose": purpose_spec.purpose,
                "need": need_text,
                "candidates": [
                    {"name": brief.name, "description": brief.description} for brief in briefs
                ],
            },
            ensure_ascii=False,
        )
