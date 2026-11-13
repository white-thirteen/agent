"""Classify only authenticated refund checkpoints; unknown shapes are never resumable."""

from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import StateSnapshot

from app.agents.types import AgentType, TaskType
from app.domain.refunds import application_subject, canonical_digest
from app.graph.contracts import ExecutionContext, SpecialistInput, SpecialistResult

SAFE_REFUND_NODES = frozenset(
    {
        "recheck_execution",
        "prepare_refund_attempt",
        "execute_refund",
        "reconcile_operation",
        "record_tool_outcome",
        "record_rejection",
        "compose_refund_reply",
        "map_result",
    }
)


@dataclass(frozen=True, slots=True)
class RefundCheckpoint:
    kind: Literal["pending", "post_gate", "ended", "unknown"]
    child: StateSnapshot | None = None
    interrupt_id: str | None = None
    checkpoint_ns: str | None = None
    checkpoint_id: str | None = None
    bound: bool = False
    result: SpecialistResult | None = None


UNKNOWN = RefundCheckpoint("unknown")


def _matches_request(values, subject):
    try:
        request = SpecialistInput.model_validate(values["request"])
        trusted = request.context
        return (
            request.agent_type is AgentType.REFUND
            and request.task_type is TaskType.REFUND_APPLY
            and all(
                getattr(trusted, key) == subject[key]
                for key in ("user_id", "conversation_id", "task_id", "workflow_id")
            )
            and request.task_id == subject["task_id"]
        )
    except (KeyError, TypeError, ValueError):
        return False


def classify_refund_checkpoint(root, approval, application):
    """Validate owner/task, exact child namespace, original call and latest position."""
    try:
        subject = approval["subject_snapshot"]
        if approval["subject_digest"] != canonical_digest(subject):
            return UNKNOWN
        if (
            application_subject(application) != subject
            or str(application["application_id"]) != subject["application_id"]
            or str(application["operation_id"]) != subject["operation_id"]
            or application["tool_name"] != subject["tool_name"]
            or application["tool_version"] != subject["tool_version"]
            or application["call_id"] != subject["call_id"]
            or application["canonical_args"] != subject["canonical_args"]
            or application["args_digest"] != subject["args_digest"]
        ):
            return UNKNOWN
        root_values = root.values
        trusted = ExecutionContext(
            **{key: root_values[key] for key in ExecutionContext.model_fields}
        )
        if any(
            getattr(trusted, key) != subject[key]
            for key in ("user_id", "conversation_id", "task_id", "workflow_id")
        ):
            return UNKNOWN
        if str(root.config["configurable"]["thread_id"]) != subject["thread_id"]:
            return UNKNOWN
        if not root.next:
            if root_values.get("task_status") not in ("completed", "rejected", "failed"):
                return UNKNOWN
            if root.interrupts or any(task.error or task.interrupts for task in root.tasks):
                return UNKNOWN
            result = SpecialistResult.model_validate(root_values["specialist_result"])
            if (
                result.task_id != subject["task_id"]
                or result.workflow_id != subject["workflow_id"]
                or result.approval_id != str(approval["approval_id"])
                or result.operation_id != subject["operation_id"]
                or result.agent_type is not AgentType.REFUND
                or result.task_type is not TaskType.REFUND_APPLY
                or result.status != root_values["task_status"]
            ):
                return UNKNOWN
            return RefundCheckpoint("ended", result=result)
        if root.next != ("refund",) or len(root.tasks) != 1 or root.tasks[0].name != "refund":
            return UNKNOWN
        children = [
            task.state
            for task in root.tasks
            if isinstance(task.state, StateSnapshot) and task.name == "refund"
        ]
        if len(children) != 1:
            return UNKNOWN
        child = children[0]
        values = child.values
        if not _matches_request(values, subject):
            return UNKNOWN
        call = values["pending_refund_call"]
        if not isinstance(call, dict):
            return UNKNOWN
        original_message = values["original_ai_message"]
        if (
            not isinstance(original_message, AIMessage)
            or original_message.invalid_tool_calls
            or len(original_message.tool_calls) != 1
        ):
            return UNKNOWN
        native = original_message.tool_calls[0]
        if (
            str(values["application_id"]) != subject["application_id"]
            or str(values["operation_id"]) != subject["operation_id"]
            or str(values["approval_id"]) != str(approval["approval_id"])
            or values["subject_digest"] != approval["subject_digest"]
            or call.get("call_id") != subject["call_id"]
            or call.get("name") != subject["tool_name"]
            or call.get("raw_args") != application["raw_args"]
            or native.get("id") != subject["call_id"]
            or native.get("name") != subject["tool_name"]
            or native.get("args") != application["raw_args"]
            or values["tool_version"] != subject["tool_version"]
            or values["canonical_args"] != subject["canonical_args"]
            or subject["args_digest"] != canonical_digest(subject["canonical_args"])
        ):
            return UNKNOWN
        config = child.config["configurable"]
        namespace, checkpoint_id = config["checkpoint_ns"], config["checkpoint_id"]
        if (
            str(config.get("thread_id")) != subject["thread_id"]
            or not namespace
            or not checkpoint_id
        ):
            return UNKNOWN
        existing = (approval["interrupt_id"], approval["checkpoint_ns"], approval["checkpoint_id"])
        bound = all(value is not None for value in existing)
        if any(value is not None for value in existing) and not bound:
            return UNKNOWN
        if bound and existing[1] != namespace:
            return UNKNOWN
        if child.interrupts:
            if (
                len(child.interrupts) != 1
                or child.next != ("approval_gate",)
                or root.tasks[0].error is not None
                or len(root.interrupts) > 1
            ):
                return UNKNOWN
            interrupt = child.interrupts[0]
            if root.interrupts and root.interrupts[0].id != interrupt.id:
                return UNKNOWN
            payload = interrupt.value
            if (
                not isinstance(payload, dict)
                or payload.get("kind") != "refund_approval"
                or str(payload.get("approval_id")) != str(approval["approval_id"])
                or str(payload.get("application_id")) != subject["application_id"]
                or str(payload.get("operation_id")) != subject["operation_id"]
                or payload.get("subject_digest") != approval["subject_digest"]
                or not interrupt.id
                or (bound and existing[0] != interrupt.id)
            ):
                return UNKNOWN
            return RefundCheckpoint("pending", child, interrupt.id, namespace, checkpoint_id, bound)
        if not bound or len(child.next) != 1 or child.next[0] not in SAFE_REFUND_NODES:
            return UNKNOWN
        return RefundCheckpoint("post_gate", child, None, namespace, checkpoint_id, True)
    except (KeyError, TypeError, ValueError, AttributeError):
        return UNKNOWN
