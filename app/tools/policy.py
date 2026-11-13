"""Pure policy decisions over trusted execution context and validated arguments."""

from pydantic import ValidationError

from app.agents.types import AgentType, TaskType
from app.tools.models import ApprovalRequirement, PolicyDecision, PolicyEvaluation


class ToolPolicy:
    def evaluate(
        self,
        *,
        call,
        definition,
        context,
        usage,
        remaining_active_seconds,
        validated_args=None,
        verified_approval=None,
    ) -> PolicyEvaluation:
        def deny(code, validated_args=None):
            return PolicyEvaluation(
                PolicyDecision.DENY, code, "Tool call is not allowed.", validated_args
            )

        if definition is None:
            return deny("tool_not_allowed")
        meta = definition.metadata
        if not meta.enabled or (meta.name, meta.version) not in context.allowed_tools:
            return deny("tool_not_allowed")
        if (
            context.agent_type not in meta.allowed_agents
            or not meta.required_scopes <= context.permission_scopes
        ):
            return deny("tool_not_allowed")
        if context.task_type.target_agent is not context.agent_type:
            return deny("tool_not_allowed")
        if context.origin == "model":
            if context.node_name is not None:
                return deny("tool_not_allowed")
            if context.agent_type is AgentType.REFUND and meta.name != "refund_order":
                return deny("tool_not_allowed")
        else:
            if meta.name == "write_preferences" and "memory:write" not in context.permission_scopes:
                return deny("tool_not_allowed")
            allowed_nodes = {
                (AgentType.ORDER, TaskType.ORDER_QUERY, "execute_query"): {
                    "get_order",
                    "list_orders",
                },
                (AgentType.REFUND, TaskType.REFUND_APPLY, "load_order"): {"get_order"},
                (AgentType.REFUND, TaskType.REFUND_APPLY, "check_eligibility"): {
                    "check_refund_eligibility"
                },
                (AgentType.REFUND, TaskType.REFUND_APPLY, "recheck_execution"): {
                    "check_refund_eligibility"
                },
                (AgentType.REFUND, TaskType.REFUND_APPLY, "prepare_application"): {
                    "prepare_refund_application"
                },
                (AgentType.REFUND, TaskType.REFUND_APPLY, "persist_approval"): {
                    "register_refund_approval"
                },
                (AgentType.REFUND, TaskType.REFUND_APPLY, "record_rejection"): {
                    "close_refund_application"
                },
                (AgentType.KNOWLEDGE, TaskType.MEMORY_MANAGE, "execute_memory_write"): {
                    "write_preferences"
                },
            }
            if context.origin != "node" or meta.name not in allowed_nodes.get(
                (context.agent_type, context.task_type, context.node_name), set()
            ):
                return deny("tool_not_allowed")
        try:
            args = (
                validated_args
                if validated_args is not None
                else definition.args_schema.model_validate(call.raw_args)
            )
        except ValidationError:
            return deny("invalid_tool_arguments")
        values = args.model_dump(mode="json")
        for key, value in context.argument_constraints.get(meta.name, {}).items():
            if values.get(key) != value:
                return deny("invalid_tool_arguments", args)
        if usage.tool_calls >= context.run_limits.max_tool_calls or remaining_active_seconds <= 0:
            return deny("tool_budget_exceeded", args)
        if meta.approval_required or meta.risk_level == "high":
            if verified_approval is not None:
                from app.domain.refunds import canonical_digest

                subject = verified_approval.subject
                business = context.refund_context
                if (
                    business is None
                    or verified_approval.approval_id != business.approval_id
                    or verified_approval.application_id != business.application_id
                    or verified_approval.operation_id != business.operation_id
                    or verified_approval.subject_digest != canonical_digest(subject)
                    or subject.get("application_id") != business.application_id
                    or subject.get("operation_id") != business.operation_id
                    or subject.get("thread_id") != business.thread_id
                    or subject.get("args_digest") != canonical_digest(values)
                    or subject.get("user_id") != context.execution.user_id
                    or subject.get("conversation_id") != context.execution.conversation_id
                    or subject.get("task_id") != context.execution.task_id
                    or subject.get("workflow_id") != context.execution.workflow_id
                    or subject.get("call_id") != call.call_id
                    or subject.get("tool_name") != meta.name
                    or subject.get("tool_version") != meta.version
                    or subject.get("canonical_args") != values
                ):
                    return deny("approval_not_valid", args)
                return PolicyEvaluation(PolicyDecision.ALLOW, "allowed", "Tool call allowed.", args)
            approval = ApprovalRequirement(
                call.call_id,
                meta.name,
                meta.version,
                values,
                context.execution.user_id,
                context.execution.task_id,
                context.execution.workflow_id,
            )
            return PolicyEvaluation(
                PolicyDecision.REQUIRE_APPROVAL,
                "approval_not_available",
                "Approval is not available.",
                args,
                approval,
            )
        return PolicyEvaluation(PolicyDecision.ALLOW, "allowed", "Tool call allowed.", args)
