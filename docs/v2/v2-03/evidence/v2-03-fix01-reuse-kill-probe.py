"""Same Task reuse: a new Run dies during its business model attempt."""
import asyncio
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

runpy.run_path('docs/v2/v2-02/evidence/linux-pg-launcher.py')['configure']()
sys.path.insert(0, str(Path('tests').resolve()))
from test_tool_progressive_disclosure import _build_full_registry, _scope
from app.agents.types import AgentType, TaskType
from app.graph.contracts import ExecutionContext
from app.runtime.model_gateway import ModelCallContext, ModelCallLimits, ModelGateway
from app.runtime.selection_reservation import SelectionReservation
from app.tools.discovery import PurposeSpec
from app.tools.selector import ToolSelector
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
OWNER = {'user_id': 'v203-user', 'conversation_id': 'v203-conv', 'task_id': 'v203-task'}
PURPOSE = PurposeSpec(purpose='probe.reuse', agent_type=AgentType.ORDER, task_type=TaskType.ORDER_QUERY, allowed_tools=frozenset({'get_order'}))

class State(TypedDict):
    user_id: str
    conversation_id: str
    task_id: str
    run_id: str
    model_call_usage: dict
    tool_selection_record: dict
    task_status: str

class Killer:
    async def ainvoke(self, messages):
        os._exit(71)

async def scenario(thread, second):
    config = {'configurable': {'thread_id': thread}}
    async with AsyncPostgresSaver.from_conn_string(os.environ['AGENT_TEST_DATABASE_URL']) as saver:
        prior = await saver.aget_tuple(config)
        root_id = prior.config['configurable']['checkpoint_id'] if prior else None
        scope = _scope(model_attempts=1)
        reservation = SelectionReservation(saver, thread_id=thread, owner=OWNER, run_id='run-2' if second else 'run-1', source_checkpoint_id=root_id)
        registry = _build_full_registry()
        selector = ToolSelector(registry)
        execution = ExecutionContext(**OWNER, workflow_id=OWNER['task_id'], run_id='run-2' if second else 'run-1')
        if second:
            from types import SimpleNamespace
            await reservation.load(SimpleNamespace(values=prior.checkpoint['channel_values'], config=prior.config, next=()))
        scope.selection_reservation = reservation
        async def node(state):
            out = await selector.select(execution=execution, agent_type=AgentType.ORDER, task_type=TaskType.ORDER_QUERY, purpose_spec=PURPOSE, permission_scopes=frozenset({'orders:read'}), scope=scope, need_text='same', existing_record=state.get('tool_selection_record'))
            if second:
                assert out.reused and not out.selector_called
                gateway = ModelGateway(Killer(), ModelCallLimits(8, 10, 0))
                await gateway.invoke([HumanMessage(content='controlled')], context=ModelCallContext('run-2', OWNER['task_id'], AgentType.ORDER, before_attempt=scope.reserve_model_attempt), model_usage=scope.model_usage())
            return {'tool_selection_record': out.record.model_dump(mode='json'), 'model_call_usage': {'model_attempts': 1}, 'task_status': 'needs_input'}
        builder = StateGraph(State)
        builder.add_node('node', node)
        builder.add_edge(START, 'node')
        builder.add_edge('node', END)
        graph = builder.compile(checkpointer=saver)
        initial = {**OWNER, 'run_id': execution.run_id, 'model_call_usage': {'model_attempts': 1}, 'tool_selection_record': prior.checkpoint['channel_values']['tool_selection_record'] if prior else None, 'task_status': 'running'}
        await graph.ainvoke(initial, config, durability='sync')
        snapshot = await graph.aget_state(config)
        actual = await saver.aget_tuple(snapshot.config)
        await reservation.confirm(snapshot._replace(values=actual.checkpoint['channel_values']))

async def parent():
    thread = 'v203-reuse-kill-' + uuid4().hex
    report = {}
    async with AsyncPostgresSaver.from_conn_string(os.environ['AGENT_TEST_DATABASE_URL']) as saver:
        try:
            await scenario(thread, False)
            process = subprocess.run([sys.executable, __file__, '--child', thread], capture_output=True, timeout=30)
            report['child_exit'] = process.returncode
            assert process.returncode == 71
            saved = await saver.aget_tuple({'configurable': {'thread_id': thread, 'checkpoint_ns': 'v203-reservation:' + OWNER['task_id']}})
            report.update(attempt_floor=saved.checkpoint['channel_values']['attempts'], rediscovery_floor=saved.checkpoint['channel_values']['rediscoveries'], inflight=saved.checkpoint['channel_values']['inflight'])
            root = await saver.aget_tuple({'configurable': {'thread_id': thread}})
            report['root_attempts'] = root.checkpoint['channel_values']['model_call_usage']['model_attempts']
        finally:
            await saver.adelete_thread(thread)
            report['thread_cleaned'] = await saver.aget_tuple({'configurable': {'thread_id': thread}}) is None
    print(json.dumps(report, sort_keys=True))

asyncio.run(scenario(sys.argv[2], True) if len(sys.argv) > 1 else parent())
