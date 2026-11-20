"""Abrupt process loss after durable reservation, followed by a fresh Saver reader."""
import asyncio
import json
import os
import runpy
import subprocess
import sys
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

runpy.run_path('docs/v2/v2-02/evidence/linux-pg-launcher.py')['configure']()
from app.runtime.selection_reservation import SelectionReservation
from app.agents.types import AgentType, TaskType
from app.graph.contracts import ExecutionContext
from app.runtime.model_gateway import ModelGateway, ModelCallLimits
from app.tools.discovery import PurposeSpec
from app.tools.selector import ToolSelector, SelectorOutput
sys.path.insert(0, str(__import__('pathlib').Path('tests').resolve()))
from test_tool_progressive_disclosure import _build_full_registry, _scope, _structured_resp, ControlledSelectorAndBusinessModel
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
OWNER = {'user_id': 'v203-user', 'conversation_id': 'v203-conv', 'task_id': 'v203-task'}

class State(TypedDict):
    user_id: str
    conversation_id: str
    task_id: str
    run_id: str
    model_call_usage: dict
    tool_selection_record: dict
    task_status: str

async def child(thread):
    async with AsyncPostgresSaver.from_conn_string(os.environ['AGENT_TEST_DATABASE_URL']) as saver:
        reserve = SelectionReservation(saver, thread_id=thread, owner=OWNER, run_id='run-1', source_checkpoint_id=None)
        registry = _build_full_registry()
        scope = _scope(model_attempts=1)
        scope.selection_reservation = reserve
        model = ControlledSelectorAndBusinessModel([_structured_resp(SelectorOutput(action='use_tools', tool_names=['list_orders']))])
        selector = ToolSelector(registry, ModelGateway(model, ModelCallLimits(8, 10, 0)))
        purpose = PurposeSpec(purpose='v203.probe', agent_type=AgentType.ORDER, task_type=TaskType.ORDER_QUERY, allowed_tools=frozenset({'get_order', 'list_orders'}))
        execution = ExecutionContext(user_id=OWNER['user_id'], conversation_id=OWNER['conversation_id'], task_id=OWNER['task_id'], workflow_id=OWNER['task_id'], run_id='run-1')
        args = dict(execution=execution, agent_type=AgentType.ORDER, task_type=TaskType.ORDER_QUERY, purpose_spec=purpose, permission_scopes=frozenset({'orders:read'}), scope=scope)
        first = await selector.select(**args, need_text='single', deterministic_target='get_order')
        async def node(state):
            result = await selector.select(**args, need_text='list', existing_record=first.record)
            assert result.status == 'selected' and result.selector_called
            os._exit(71)
        graph = StateGraph(State)
        graph.add_node('node', node)
        graph.add_edge(START, 'node')
        graph.add_edge('node', END)
        graph = graph.compile(checkpointer=saver)
        await graph.ainvoke({**OWNER, 'run_id': 'run-1', 'model_call_usage': {'model_attempts': 1}, 'tool_selection_record': {}, 'task_status': 'running'}, {'configurable': {'thread_id': thread}}, durability='sync')

async def parent():
    thread = 'v203-kill-test-' + uuid4().hex
    report = {}
    async with AsyncPostgresSaver.from_conn_string(os.environ['AGENT_TEST_DATABASE_URL']) as saver:
        try:
            process = subprocess.run([sys.executable, __file__, '--child', thread], capture_output=True, timeout=30)
            report['child_exit'] = process.returncode
            assert process.returncode == 71
            cfg = {'configurable': {'thread_id': thread, 'checkpoint_ns': 'v203-reservation:' + OWNER['task_id']}}
            saved = await saver.aget_tuple(cfg)
            report['attempt_floor'] = saved.checkpoint['channel_values']['attempts']
            report['rediscovery_floor'] = saved.checkpoint['channel_values']['rediscoveries']
            report['inflight'] = saved.checkpoint['channel_values']['inflight']
            root = await saver.aget_tuple({'configurable': {'thread_id': thread}})
            report['root_attempts'] = root.checkpoint['channel_values']['model_call_usage']['model_attempts']
        finally:
            await saver.adelete_thread(thread)
            report['thread_cleaned'] = await saver.aget_tuple({'configurable': {'thread_id': thread}}) is None
    print(json.dumps(report, sort_keys=True))

asyncio.run(child(sys.argv[2]) if len(sys.argv) > 1 else parent())
