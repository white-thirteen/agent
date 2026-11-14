"""Validated internal graph contracts, separate from HTTP and model credentials."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.agents.types import AgentType, TaskType

Identifier = Annotated[str, Field(min_length=1, max_length=128)]
TaskGoal = Annotated[str, Field(min_length=1, max_length=4000)]
Question = Annotated[str, Field(min_length=1, max_length=2000)]


class GraphProtocolError(ValueError):
    """A graph boundary received inconsistent state or task associations."""


class GraphContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        revalidate_instances="always",
        allow_inf_nan=False,
        hide_input_in_errors=True,
    )


class ExecutionContext(GraphContract):
    """Server-supplied associations. Validation does not authenticate their owner."""

    user_id: Identifier
    conversation_id: Identifier
    workflow_id: Identifier
    task_id: Identifier
    run_id: Identifier

    @model_validator(mode="after")
    def validate_task_alias(self) -> Self:
        if self.workflow_id != self.task_id:
            raise ValueError("workflow_id must equal task_id")
        return self


class RouteDecision(GraphContract):
    """Supervisor output; contains no trusted identity or arbitrary node name."""

    agent_type: AgentType
    task_type: TaskType
    task_goal: TaskGoal
    entities: dict[str, JsonValue] = Field(default_factory=dict)
    needs_clarification: bool = Field(default=False, strict=True)
    missing_fields: list[Identifier] = Field(default_factory=list, max_length=16)
    clarification_question: Question | None = None

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        if self.agent_type is not self.task_type.target_agent:
            raise ValueError("Task type does not belong to the selected agent")
        if self.task_type is TaskType.CLARIFICATION and not self.needs_clarification:
            raise ValueError("Clarification tasks must request clarification")
        _validate_missing_input(
            self.needs_clarification, self.missing_fields, self.clarification_question
        )
        return self


class PendingTask(GraphContract):
    """Preserve the original business goal across normal clarification turns."""

    user_id: Identifier
    conversation_id: Identifier
    workflow_id: Identifier
    task_id: Identifier
    task_type: TaskType
    task_goal: TaskGoal
    entities: dict[str, JsonValue] = Field(default_factory=dict)
    missing_fields: list[Identifier] = Field(min_length=1, max_length=16)
    clarification_question: Question
    task_message_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_pending_input(self) -> Self:
        _validate_missing_input(True, self.missing_fields, self.clarification_question)
        return self


class SupervisorOutput(GraphContract):
    kind: Literal["route", "unsupported"]
    decision: RouteDecision | None = None

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        if (self.kind == "route") != (self.decision is not None):
            raise ValueError("Only route outputs must carry a decision")
        return self


class PublicCitation(GraphContract):
    """Server-built citation with no model URL, content, vector or private profile."""

    evidence_id: Identifier
    document_id: Identifier
    document_version: Identifier
    chunk_id: Identifier
    source_title: Annotated[str, Field(min_length=1, max_length=500)]
    source_key: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")]
    section: str | None
    page: int | None
    checked_at: datetime


class FailureDetails(GraphContract):
    code: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")]
    message: Annotated[str, Field(min_length=1, max_length=2000)]


class ResultStatus(StrEnum):
    COMPLETED = "completed"
    NEEDS_INPUT = "needs_input"
    REJECTED = "rejected"
    FAILED = "failed"


class SpecialistInput(GraphContract):
    context: ExecutionContext
    task_id: Identifier
    agent_type: AgentType
    task_type: TaskType
    task_goal: TaskGoal
    entities: dict[str, JsonValue] = Field(default_factory=dict)
    messages: list[AnyMessage] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_specialist_input(self) -> Self:
        _validate_specialist_owner(self.agent_type, self.task_type)
        if self.task_id != self.context.task_id:
            raise ValueError("Specialist task must match its context")
        for message in self.messages:
            if not isinstance(message, (HumanMessage, AIMessage)):
                raise ValueError("Specialist context only accepts public human/AI messages")
            if isinstance(message, AIMessage) and (
                message.tool_calls or message.invalid_tool_calls
            ):
                raise ValueError("Tool-call history belongs to the private specialist state")
        return self


class SpecialistResult(GraphContract):
    """Structured facts and references; never an entire child state or tool history."""

    workflow_id: Identifier
    run_id: Identifier
    task_id: Identifier
    agent_type: AgentType
    task_type: TaskType
    status: ResultStatus
    summary: Annotated[str, Field(min_length=1, max_length=4000)]
    facts: dict[str, JsonValue] = Field(default_factory=dict)
    entities: dict[str, JsonValue] = Field(default_factory=dict)
    sources: list[PublicCitation] = Field(default_factory=list, max_length=5)
    missing_fields: list[Identifier] = Field(default_factory=list, max_length=16)
    clarification_question: Question | None = None
    operation_id: Identifier | None = None
    approval_id: Identifier | None = None
    error: FailureDetails | None = None
    approved_answer: Annotated[str, Field(min_length=1, max_length=32000)] | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        _validate_specialist_owner(self.agent_type, self.task_type)
        _validate_missing_input(
            self.status is ResultStatus.NEEDS_INPUT,
            self.missing_fields,
            self.clarification_question,
        )
        if (self.status is ResultStatus.FAILED) != (self.error is not None):
            raise ValueError("Only failed results must include error details")
        if self.status is ResultStatus.COMPLETED:
            if self.task_type is TaskType.KNOWLEDGE_QA:
                if not self.sources or not self.approved_answer:
                    raise ValueError("Completed QA requires sources and approved answer")
            elif not self.facts:
                raise ValueError("Completed business results require structured facts")
            if self.task_type is TaskType.REFUND_APPLY and self.operation_id is None:
                raise ValueError("Completed side effects require a business operation reference")
            if self.task_type is TaskType.REFUND_APPLY and self.approval_id is None:
                raise ValueError("Completed refunds require an approval reference")
            if self.task_type is TaskType.MEMORY_MANAGE and self.sources:
                raise ValueError("Memory results must not include knowledge sources")
        return self


def _validate_specialist_owner(agent_type: AgentType, task_type: TaskType) -> None:
    if agent_type is AgentType.SUPERVISOR or agent_type is not task_type.target_agent:
        raise ValueError("Task must belong to the selected specialist agent")


def _validate_missing_input(
    needs_input: bool, missing_fields: list[str], question: str | None
) -> None:
    if len(missing_fields) != len(set(missing_fields)):
        raise ValueError("Missing field names must be unique")
    if needs_input:
        if not missing_fields or question is None:
            raise ValueError("Clarification requires missing fields and a question")
    elif missing_fields or question is not None:
        raise ValueError("Ready tasks cannot include unresolved clarification fields")
