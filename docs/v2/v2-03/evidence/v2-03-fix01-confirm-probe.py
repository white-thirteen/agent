"""Real Saver confirmation of Task reservations against complete Graph checkpoints."""
import asyncio
import json
import os
import runpy
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

runpy.run_path('docs/v2/v2-02/evidence/linux-pg-launcher.py')['configure']()
from app.runtime.selection_reservation import SelectionReservation
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class State(TypedDict):
    user_id: str
    conversation_id: str
    task_id: str
    run_id: str
    model_call_usage: dict
    tool_selection_record: dict
    task_status: str

class Record:
    def model_dump(self, **kwargs):
        return {'rediscovery_count': 1, 'selected': ['get_order']}

async def main():
    owner = {'user_id': 'isolated-user', 'conversation_id': 'isolated-conversation', 'task_id': 'isolated-task'}
    report = {}
    async with AsyncPostgresSaver.from_conn_string(os.environ['AGENT_TEST_DATABASE_URL']) as saver:
        for failing in (True, False):
            thread = 'v203-confirm-test-' + uuid4().hex
            config = {'configurable': {'thread_id': thread}}
            reserve = SelectionReservation(saver, thread_id=thread, owner=owner, run_id='run-1', source_checkpoint_id=None)
            async def node(state):
                await reserve.begin(1, 1)
                await reserve.reserve_attempt(2)
                await reserve.record_outcome(Record(), 'selected')
                if failing:
                    raise RuntimeError('controlled crash')
                return {'model_call_usage': {'model_attempts': 2}, 'tool_selection_record': Record().model_dump(), 'task_status': 'completed'}
            builder = StateGraph(State)
            builder.add_node('node', node)
            builder.add_edge(START, 'node')
            builder.add_edge('node', END)
            graph = builder.compile(checkpointer=saver)
            try:
                initial = {**owner, 'run_id': 'run-1', 'model_call_usage': {'model_attempts': 1}, 'tool_selection_record': {}, 'task_status': 'running'}
                try:
                    await graph.ainvoke(initial, config, durability='sync')
                except RuntimeError:
                    pass
                snapshot = await graph.aget_state(config)
                resumed = SelectionReservation(saver, thread_id=thread, owner=owner, run_id='run-2', source_checkpoint_id=snapshot.config['configurable']['checkpoint_id'])
                try:
                    await resumed.load(snapshot)
                    report['completed_checkpoint_confirmed'] = not resumed.value['inflight']
                except ValueError:
                    report['interrupted_checkpoint_rejected'] = True
            finally:
                await saver.adelete_thread(thread)
                assert await saver.aget_tuple({'configurable': {'thread_id': thread}}) is None
        report['threads_cleaned'] = True
    print(json.dumps(report, sort_keys=True))

asyncio.run(main())
