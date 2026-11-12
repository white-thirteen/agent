"""Pure policy decisions over trusted execution context and validated arguments."""

from pydantic import ValidationError

from app.agents.types import AgentType, TaskType
from app.tools.models import ApprovalRequirement, PolicyDecision, PolicyEvaluation


class ToolPolicy:
    def evaluate(
        self, *, call, definition, context, usage, remaining_active_seconds, validated_args=None
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
        elif (
            context.origin != "node"
            or context.agent_type is not AgentType.ORDER
            or context.task_type is not TaskType.ORDER_QUERY
            or context.node_name != "execute_query"
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
