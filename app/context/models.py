"""Serializable context identities and publication contracts; persistence comes later."""

from datetime import datetime
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SessionIdentity(Contract):
    user_id: str
    conversation_id: str

    def archive_ref(self, segment_id: str) -> str:
        # Reference encoding is unambiguous, but never establishes authority.
        return ":".join(
            quote(part, safe="") for part in (self.user_id, self.conversation_id, segment_id)
        )


class Archive(Contract):
    identity: SessionIdentity
    archive_ref: str
    segment_id: str
    message_ids: tuple[str, ...]
    content_hash: str
    source_checkpoint_id: str
    relative_path: str
    file_hash: str | None
    status: Literal["PREPARING", "READY"]


class Summary(Contract):
    identity: SessionIdentity
    summary_id: str
    version: int
    text: str
    archive_refs: tuple[str, ...]
    message_ids: tuple[str, ...]
    parent_summary_id: str | None
    input_hash: str
    status: Literal["BUILDING", "READY"]


class ContextRef(Contract):
    revision: int
    summary_id: str


class ContextRevision(Contract):
    identity: SessionIdentity
    revision: int
    base_revision: int | None
    source_checkpoint_id: str
    message_ids: tuple[str, ...]
    content_hash: str
    archive_refs: tuple[str, ...]
    summary_id: str
    policy_version: str
    model_version: str
    prompt_version: str
    status: Literal["PREPARING", "PUBLISHED", "APPLIED", "STALE"]
    applied_checkpoint_id: str | None = None


class MaintenanceWork(Contract):
    identity: SessionIdentity
    maintenance_id: str
    source_task_id: str
    source_run_id: str
    source_checkpoint_id: str
    message_ids: tuple[str, ...]
    content_hash: str
    policy_version: str
    budget_version: str
    max_attempts: Literal[2] = 2
    total_seconds: Literal[30] = 30
    max_input_tokens: int
    max_output_tokens: int
    deadline_at: datetime
    reserved_attempts: int
    actual_attempts: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    usage_status: Literal["known", "estimated", "unknown"]
    archive_refs: tuple[str, ...]
    summary_id: str | None
    revision: int | None
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "EXHAUSTED", "INTERRUPTED"]


class TokenCount(Contract):
    tokens: int
    status: Literal["known", "estimated"]
    method: str


class PreferenceControl(Contract):
    user_id: str
    command_id: str
    operation_id: str
    command_digest: str
    expected_revision: int
    permission_scopes: frozenset[str]


class PreferenceReceipt(Contract):
    control: PreferenceControl
    status: Literal["PREPARED", "EXECUTING", "APPLIED", "CONFLICT", "UNKNOWN"]


class LegacyMutationSource(Contract):
    task_id: str


class ControlMutationSource(Contract):
    kind: Literal["preference_control"] = "preference_control"
    command_id: str


def mutation_source(last_mutation: dict) -> LegacyMutationSource | ControlMutationSource:
    """Decode old untagged Task entries and new explicit command entries."""
    if "source" in last_mutation:
        return ControlMutationSource.model_validate(last_mutation["source"])
    return LegacyMutationSource(task_id=last_mutation["task_id"])


class PublicMessage(Contract):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    task_id: str
    run_id: str | None = None


class PublicInteraction(Contract):
    """A trusted, complete interaction and its confirmed Task state."""

    task_id: str
    task_status: str
    messages: tuple[PublicMessage, ...]
