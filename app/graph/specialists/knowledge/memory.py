"""Finite Human commands and the existing MemoryManage workflow's durable steps."""

import re
from dataclasses import asdict, replace
from uuid import NAMESPACE_URL, uuid5

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agents.types import AgentType, TaskType
from app.domain.refunds import canonical_digest
from app.graph.contracts import FailureDetails, GraphProtocolError, SpecialistResult
from app.graph.specialists.preferences import read_optional_preferences
from app.graph.state import SpecialistState
from app.memory.models import MemoryCommand, MemoryMutationResult
from app.runtime.context import RunExecutionContext
from app.runtime.models import RunUsage
from app.tools.models import (
    MemoryBusinessContext,
    ParsedToolCall,
    PolicyDecision,
    PreparedToolAttempt,
    ToolExecutionContext,
    ToolExecutionResult,
)

FORMAT_MESSAGE = (
    "请单独使用明确格式：请记住：回答语言=中文/英语；请修改记忆：回答风格=简洁/详细；"
    "请删除记忆：回答语言/回答风格；请删除全部偏好记忆；请查看偏好记忆。"
)
UNKNOWN_MESSAGE = "本次偏好写入结果未知，请先核对，再提交新的记忆修改。"


def parse_explicit_memory_command(text: str) -> MemoryCommand | None:
    """Full-string grammar: quoted, mixed or free text never grants a write."""
    text = re.sub(r"\s+", "", text).replace(":", "：").rstrip("。.!！")
    fields = {"回答语言": "answer_language", "回答风格": "answer_style"}
    if text == "请查看偏好记忆":
        return MemoryCommand(operation="read")
    if text == "请删除全部偏好记忆":
        return MemoryCommand(operation="clear")
    match = re.fullmatch(r"请删除(?:记忆：(回答语言|回答风格)|我的(回答语言|回答风格)偏好)", text)
    if match:
        return MemoryCommand(operation="delete", field=fields[match[1] or match[2]])
    match = re.fullmatch(r"请(?:记住|修改记忆)：(回答语言|回答风格)=(中文|英语|简洁|详细)", text)
    if match:
        field = fields[match[1]]
        values = {"中文": "zh-CN", "英语": "en", "简洁": "concise", "详细": "detailed"}
        value = values[match[2]]
        if (field == "answer_language") == (value in ("zh-CN", "en")):
            return MemoryCommand(operation="upsert", field=field, value=value)
    return None


class MemoryState(SpecialistState, total=False):
    memory_command: dict | None
    source_message_id: str | None
    prepared_attempt: PreparedToolAttempt | None
    memory_result: dict | None
    outcome: str | None
    error_code: str | None


def build_memory_graph(*, registry, executor):
    """The wrapper supplies a parsed command and invokes with inherited Saver/sync."""

    def usage(runtime):
        return {
            "run_usage": asdict(runtime.context.scope.run_usage()),
            "model_call_usage": asdict(runtime.context.scope.model_usage()),
        }

    def context(runtime, args, node):
        execution = runtime.context
        definition = registry.get("write_preferences")
        return ToolExecutionContext(
            execution.context,
            AgentType.KNOWLEDGE,
            TaskType.MEMORY_MANAGE,
            node,
            execution.permission_scopes,
            "node",
            frozenset({("write_preferences", definition.metadata.version)})
            if definition
            else frozenset(),
            {"write_preferences": args},
            execution.scope.limits,
            execution.scope,
            thread_id=execution.thread_id,
        )

    def outcome(result):
        return (
            "completed"
            if result.status == "success"
            else "rejected"
            if result.status in ("policy_denied", "business_rejected")
            and result.code != "tool_budget_exceeded"
            else "failed"
        )

    def record(call, result, runtime, version):
        return {
            "call": asdict(call),
            "args_digest": canonical_digest(call.raw_args),
            "tool_version": version,
            "origin": "node",
            "node_name": "execute_memory_write",
            "task_id": runtime.context.context.task_id,
            "run_id": runtime.context.context.run_id,
            "normalized_args": result.normalized_args,
            "result": asdict(result),
        }

    def prepare_memory_command(state, runtime: Runtime[RunExecutionContext]):
        request = state["request"]
        if (
            request.context != runtime.context.context
            or request.task_type is not TaskType.MEMORY_MANAGE
        ):
            raise GraphProtocolError("Memory request association mismatch")
        if state.get("memory_command") is None or not state.get("source_message_id"):
            return {"outcome": "needs_input"}
        MemoryCommand.model_validate(state["memory_command"])
        return {
            "outcome": None,
            "error_code": None,
            "memory_result": None,
            "prepared_attempt": None,
            "call_records": {},
        }

    async def read_preferences(state, runtime):
        return await read(state, runtime, "read_preferences")

    async def read(state, runtime, node):
        update = await read_optional_preferences(
            state, runtime, registry=registry, executor=executor, node=node
        )
        if update.get("outcome"):
            return update
        result = update["memory_read_record"]["result"]
        if result["status"] != "success":
            return {
                **update,
                "outcome": "rejected" if result["status"] == "policy_denied" else "failed",
                "error_code": result["code"],
            }
        return update

    async def prepare_memory_write(
        state, config: RunnableConfig, runtime: Runtime[RunExecutionContext]
    ):
        # A real graph boundary must persist this node before the write node runs.
        conf = config.get("configurable", {})
        if not conf.get("__pregel_checkpointer") or conf.get("__pregel_durability") != "sync":
            return {"outcome": "failed", "error_code": "memory_checkpoint_required"}
        update = await read(state, runtime, "prepare_memory_write")
        if update.get("outcome"):
            return update
        args = state["memory_command"]
        ctx = runtime.context.context
        operation = str(uuid5(NAMESPACE_URL, f"memory:{ctx.task_id}:preferences:0"))
        call = ParsedToolCall(
            "node:"
            + str(
                uuid5(NAMESPACE_URL, f"{ctx.task_id}:execute_memory_write:write_preferences:1:0")
            ),
            "write_preferences",
            args,
        )
        business = MemoryBusinessContext(
            ctx.user_id,
            ctx.task_id,
            ctx.run_id,
            operation,
            canonical_digest(args),
            update["memory_context"]["revision"] or 0,
            False,
        )
        prepared = await executor.prepare_attempt(
            call,
            context=context(runtime, args, "prepare_memory_write"),
            execution_context=context(runtime, args, "execute_memory_write"),
            business_context=business,
        )
        if not isinstance(prepared, PreparedToolAttempt):
            definition = registry.get(call.name)
            records = dict(update["call_records"])
            records[call.call_id] = record(
                call, prepared, runtime, definition.metadata.version if definition else None
            )
            return {
                **update,
                "call_records": records,
                "outcome": outcome(prepared),
                "error_code": prepared.code,
                **usage(runtime),
            }
        return {**update, "prepared_attempt": prepared, **usage(runtime)}

    async def execute_memory_write(state, runtime: Runtime[RunExecutionContext]):
        marker = state.get("prepared_attempt")
        if not isinstance(marker, PreparedToolAttempt):
            return {"outcome": "failed", "error_code": "memory_result_unknown"}
        args = state["memory_command"]
        target = context(runtime, args, "execute_memory_write")
        records = dict(state.get("call_records", {}))
        previous = records.get(marker.call.call_id)
        scope = runtime.context.scope
        if marker.binding_snapshot["scope_id"] != scope.scope_id:
            current = scope.run_usage()
            saved_usage = state.get("run_usage", {})
            scope.adopt_tool_usage(
                replace(
                    current,
                    tool_calls=max(
                        current.tool_calls,
                        saved_usage.get("tool_calls", 0),
                        marker.attempted_tool_calls,
                    ),
                )
            )
            # A lost result may have spent its full timeout. Retain all confirmed
            # cumulative usage too, including earlier check-only attempts.
            scope.inherit_attempt_elapsed(
                saved_usage.get("active_elapsed_ms", 0) + int(marker.timeout_seconds * 1000)
            )
        if previous:
            if previous["call"] != asdict(marker.call) or previous[
                "args_digest"
            ] != canonical_digest(args):
                raise GraphProtocolError("Memory call association conflict")
            checked = await executor.assess(marker.call, context=target)
            if (
                previous["result"]["effect_status"] != "unknown"
                and (state.get("memory_result") or {}).get("status") != "unknown"
                and checked.decision is PolicyDecision.ALLOW
            ):
                raw = previous["result"]
                result = ToolExecutionResult(**{**raw, "run_usage": RunUsage(**raw["run_usage"])})
                return {
                    "outcome": outcome(result),
                    "error_code": result.code,
                    "memory_result": result.data,
                    **usage(runtime),
                }
        replay = (
            marker.run_id != runtime.context.context.run_id
            or marker.binding_snapshot["scope_id"] != scope.scope_id
            or scope.run_usage().tool_calls != marker.baseline_tool_calls
            or previous is not None
        )
        unknown = state.get("memory_result") or MemoryMutationResult(
            status="unknown",
            operation_id=marker.operation_id,
            revision=None,
            changed_fields=[],
            preferences=None,
        ).model_dump(mode="json")
        if replay:
            # The previous write may have consumed its full attempt. No new Run
            # may reset either tools or active time before checking the original op.
            business = MemoryBusinessContext(
                **{
                    **marker.business_snapshot,
                    "run_id": runtime.context.context.run_id,
                    "replay_check_only": True,
                }
            )
            prepared = await executor.prepare_attempt(
                marker.call, context=target, business_context=business
            )
            if not isinstance(prepared, PreparedToolAttempt):
                records[marker.call.call_id] = record(
                    marker.call, prepared, runtime, marker.tool_version
                )
                return {
                    "outcome": "failed",
                    "error_code": "memory_result_unknown",
                    "memory_result": unknown,
                    "call_records": records,
                    **usage(runtime),
                }
            marker = prepared
        result = await executor.execute_prepared(marker, context=target)
        records[marker.call.call_id] = record(marker.call, result, runtime, marker.tool_version)
        data = result.data
        if replay and result.status == "policy_denied":
            data = unknown
        return {
            "call_records": records,
            "memory_result": data,
            "outcome": "failed" if data and data["status"] == "unknown" else outcome(result),
            "error_code": "memory_result_unknown"
            if data and data["status"] == "unknown"
            else result.code,
            **usage(runtime),
        }

    def map_memory_result(state, runtime):
        request = state["request"]
        status = state.get("outcome") or "completed"
        data = state.get("memory_result")
        summary = "偏好记忆操作已完成。"
        facts = {}
        if status == "completed":
            if state["memory_command"]["operation"] == "read":
                snapshot = state["memory_read_record"]["result"]["data"]
                facts = {
                    "preferences": snapshot["preferences"],
                    "revision": snapshot["revision"],
                    "status": snapshot["status"],
                }
                summary = (
                    ("当前偏好记忆：" + str(snapshot["preferences"]))
                    if snapshot["preferences"]
                    else "尚无偏好记忆。"
                )
                if snapshot["status"] == "partial":
                    summary += "部分偏好无效，已剔除。"
            else:
                facts = {"memory_result": data}
                summary = (
                    "偏好记忆已保存。"
                    if state["memory_command"]["operation"] == "upsert"
                    else "偏好已删除；保留最小版本和幂等关联，聊天及执行快照仍可能保留历史。"
                )
        elif status == "needs_input":
            summary = FORMAT_MESSAGE
        elif state.get("error_code") == "memory_result_unknown":
            summary = UNKNOWN_MESSAGE
            facts = {"memory_result": data} if data else {}
        else:
            summary = "偏好记忆操作未完成。"
            facts = {"memory_result": data} if data else {}
        result = SpecialistResult(
            **{
                key: getattr(runtime.context.context, key)
                for key in ("workflow_id", "run_id", "task_id")
            },
            agent_type=request.agent_type,
            task_type=request.task_type,
            status=status,
            summary=summary,
            facts=facts,
            sources=[],
            missing_fields=["memory_command"] if status == "needs_input" else [],
            clarification_question=summary if status == "needs_input" else None,
            operation_id=data["operation_id"] if data else None,
            error=FailureDetails(
                code=state.get("error_code") or "memory_unavailable", message=summary
            )
            if status == "failed"
            else None,
        )
        return {"result": result, **usage(runtime)}

    graph = StateGraph(MemoryState, context_schema=RunExecutionContext)
    for name, node in [
        ("prepare_memory_command", prepare_memory_command),
        ("read_preferences", read_preferences),
        ("prepare_memory_write", prepare_memory_write),
        ("execute_memory_write", execute_memory_write),
        ("map_memory_result", map_memory_result),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "prepare_memory_command")
    graph.add_conditional_edges(
        "prepare_memory_command",
        lambda state: (
            "map_memory_result"
            if state.get("outcome")
            else "read_preferences"
            if state["memory_command"]["operation"] == "read"
            else "prepare_memory_write"
        ),
    )
    graph.add_edge("read_preferences", "map_memory_result")
    graph.add_conditional_edges(
        "prepare_memory_write",
        lambda state: "map_memory_result" if state.get("outcome") else "execute_memory_write",
    )
    graph.add_edge("execute_memory_write", "map_memory_result")
    graph.add_edge("map_memory_result", END)
    return graph.compile()
