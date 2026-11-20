"""Load pre-V203 refund graph from HEAD, then resume its real Saver interrupt with current graph."""
import asyncio
import json
import os
import runpy
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
runpy.run_path('docs/v2/v2-02/evidence/linux-pg-launcher.py')['configure']()
sys.path.insert(0, str(Path('tests').resolve()))
from runtime_support import context, run_to_end
from test_refund_full_controlled import ControlledApprovals, ControlledOrders, ControlledRefunds, Provider
from app.agents.types import AgentType
from app.graph.builder import build_supervisor_graph
from app.graph.specialists.knowledge.builder import build_knowledge_graph
from app.graph.specialists.order.builder import build_order_graph
from app.graph.specialists.refund.builder import build_refund_graph
from app.runtime.agent_runtime import AgentRuntime, RunLimits
from app.runtime.model_gateway import ModelCallLimits, ModelGateway
from app.tools.executor import ToolExecutor
from app.tools.implementations.orders import order_tools
from app.tools.implementations.refunds import refund_node_tools, refund_order_tool
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from app.workflows.approvals import ApprovalReference, LocalDemoApprovalActor

if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

legacy_source = subprocess.check_output(['git', 'show', 'HEAD:app/graph/specialists/refund/builder.py'], text=True, encoding='utf-8')
legacy = {'__name__': 'legacy_refund_probe'}
exec(compile(legacy_source, '<HEAD refund builder>', 'exec'), legacy)

class ObservedPolicy(ToolPolicy):
    decisions = []
    def evaluate(self, **kwargs):
        result = super().evaluate(**kwargs)
        self.decisions.append((kwargs['call'].call_id, result.decision.value))
        return result

class NeverSelect:
    calls = 0
    async def select(self, **kwargs):
        self.calls += 1
        raise AssertionError('Selector must not run for an old approval resume')

async def main():
    thread = 'v203-old-refund-' + uuid4().hex
    report = {'legacy_source': 'HEAD:app/graph/specialists/refund/builder.py', 'domain': 'controlled services'}
    runtime = old_runtime = None
    async with AsyncPostgresSaver.from_conn_string(os.environ['AGENT_TEST_DATABASE_URL']) as saver:
        try:
            provider, refunds = Provider(), ControlledRefunds()
            gateway = ModelGateway(provider, ModelCallLimits(8, 5, 0), context_window=8192, output_reserve=128)
            approvals = ControlledApprovals(refunds)
            registry = ToolRegistry()
            for definition in (*order_tools(ControlledOrders(), timeout_seconds=1, max_retries=0),
                               *refund_node_tools(refunds, approvals, timeout_seconds=1),
                               refund_order_tool(refunds, timeout_seconds=1)):
                registry.register(definition)
            registry.freeze()
            policy = ObservedPolicy()
            executor = ToolExecutor(registry, policy, approval_service=approvals)
            def make_graph(builder, **kwargs):
                return build_supervisor_graph(gateway=gateway, checkpointer=saver, specialists={
                    AgentType.ORDER: build_order_graph(gateway=gateway, registry=registry, executor=executor),
                    AgentType.REFUND: builder(gateway=gateway, registry=registry, executor=executor,
                        approval_service=approvals, refund_service=refunds, **kwargs),
                    AgentType.KNOWLEDGE: build_knowledge_graph(),
                })
            def make_runtime(graph):
                return AgentRuntime(graph, run_limits=RunLimits(30,12), approval_service=approvals,
                    refund_service=refunds, scope_resolver=lambda user: frozenset({'orders:read','refunds:request'}))
            old_runtime = make_runtime(make_graph(legacy['build_refund_graph']))
            ctx = replace(context(user='v203-old-user', conversation='v203-old-conv', thread=thread, message='refund order-1'),
                          permission_scopes=frozenset({'orders:read','refunds:request'}))
            handle, view, _ = await run_to_end(old_runtime, ctx)
            await old_runtime._records[handle.run_id].task
            assert view.task_status == 'waiting_approval'
            snapshot = await old_runtime._graph.aget_state({'configurable': {'thread_id': thread}}, subgraphs=True)
            child = snapshot.tasks[0].state
            raw = await saver.aget_tuple(child.config)
            values = raw.checkpoint['channel_values']
            report['legacy_record_absent'] = not values.get('tool_selection_record')
            before = values['pending_refund_call']['call_id'], values['operation_id']
            old_version, old_args = values['tool_version'], values['canonical_args']
            old_subject = dict(approvals.row['subject_snapshot'])
            policy.decisions.clear()
            await old_runtime.shutdown()
            selector = NeverSelect()
            runtime = make_runtime(make_graph(build_refund_graph, selector=selector))
            actor = LocalDemoApprovalActor().get_actor()
            await approvals.decide(approvals.row['approval_id'], actor=actor, decision='APPROVED', expected_subject_digest=approvals.row['subject_digest'])
            handle = await runtime.resume_approval(ApprovalReference(approvals.row['approval_id']), actor=actor)
            await runtime._records[handle.run_id].task
            result = await runtime.get_run(user_id=ctx.user_id, conversation_id=ctx.conversation_id, run_id=handle.run_id)
            try:
                repeated = await runtime.resume_approval(ApprovalReference(approvals.row['approval_id']), actor=actor)
                if repeated.run_id in runtime._records:
                    await runtime._records[repeated.run_id].task
                report['repeat_resume'] = 'accepted_or_reused'
            except Exception as error:
                report['repeat_resume'] = type(error).__name__
            report.update(task_status=result.task_status, selector_calls=selector.calls, original_call_id=before[0],
                          call_id_unchanged=refunds.row['call_id'] == before[0],
                          operation_unchanged=refunds.fact['operation_id'] == before[1],
                          version_unchanged=refunds.row['tool_version'] == old_version,
                          args_unchanged=refunds.row['canonical_args'] == old_args,
                          subject_unchanged=approvals.row['subject_snapshot'] == old_subject,
                          policy_rechecked=any(call_id == before[0] for call_id, decision in policy.decisions),
                          policy_decisions=policy.decisions, effect_count=refunds.effect_count)
        finally:
            if runtime:
                await runtime.shutdown()
            if old_runtime:
                await old_runtime.shutdown()
            await saver.adelete_thread(thread)
            report['thread_cleaned'] = await saver.aget_tuple({'configurable': {'thread_id': thread}}) is None
    print(json.dumps(report, default=str, sort_keys=True))

asyncio.run(main())
