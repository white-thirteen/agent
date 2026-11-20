"""Controlled production Order topology before/after V203; no network or DB."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
sys.path.insert(0, str(Path('.').resolve()))
sys.path.insert(0, str(Path('tests').resolve()))
from test_order_graph import Model, Repository, tool_call
from app.agents.types import AgentType, TaskType
from app.domain.orders import MockOrderService
from app.graph.contracts import ExecutionContext, SpecialistInput
from app.graph.specialists.order.builder import build_order_graph
from app.graph.transfers import create_specialist_state
from app.runtime.context import RunExecutionContext
from app.runtime.model_gateway import ModelCallLimits, ModelCallUsage, ModelGateway
from app.runtime.models import RunLimits, RunUsage
from app.runtime.run_scope import RunScope
from app.tools.executor import ToolExecutor
from app.tools.implementations.orders import order_tools
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry
from app.tools.selector import ToolSelector

legacy_source = subprocess.check_output(['git', 'show', 'HEAD:app/graph/specialists/order/builder.py'], text=True, encoding='utf-8')
legacy = {'__name__': 'legacy_order_probe'}
exec(compile(legacy_source, '<HEAD order builder>', 'exec'), legacy)

class ObservedSelector(ToolSelector):
    model_calls = 0
    async def select(self, **kwargs):
        outcome = await super().select(**kwargs)
        self.model_calls += int(outcome.selector_called)
        return outcome

async def run(builder, current):
    registry = ToolRegistry()
    for item in order_tools(MockOrderService(Repository()), timeout_seconds=1, max_retries=1):
        registry.register(item)
    registry.freeze()
    model = Model([tool_call('get_order', {'order_id': 'one'}), AIMessage(content='done')])
    gateway = ModelGateway(model, ModelCallLimits(5, 2, 0))
    selector = ObservedSelector(registry, gateway)
    kwargs = {'selector': selector} if current else {}
    graph = builder(gateway=gateway, registry=registry, executor=ToolExecutor(registry, ToolPolicy()), **kwargs)
    ctx = ExecutionContext(user_id='dev-user', conversation_id='conv', task_id='task', workflow_id='task', run_id='run')
    scope = RunScope(limits=RunLimits(10, 5), model_usage=ModelCallUsage(), run_usage=RunUsage())
    scope.start_active_period()
    request = SpecialistInput(context=ctx, task_id='task', agent_type=AgentType.ORDER, task_type=TaskType.ORDER_QUERY,
                              task_goal='query order', entities={'query_kind':'get','order_id':'one'},
                              messages=[HumanMessage(content='query order')])
    output = await graph.ainvoke(create_specialist_state(request, scope=scope), context=RunExecutionContext(ctx, 'thread', frozenset({'orders:read'}), scope))
    return {'status': output['result'].status, 'business_attempts': scope.model_usage().model_attempts,
            'selector_calls': selector.model_calls if current else 0,
            'bindings': [[schema['function']['name'] for schema in binding] for binding in model.schemas]}

async def main():
    print(json.dumps({'head_before': await run(legacy['build_order_graph'], False),
                      'current': await run(build_order_graph, True)}, default=str, sort_keys=True))
asyncio.run(main())
