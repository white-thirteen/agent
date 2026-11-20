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
        async def node(state):
            await reserve.begin(1, 1)
            await reserve.reserve_attempt(2)
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
