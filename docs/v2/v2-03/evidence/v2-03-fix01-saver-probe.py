"""Isolated Saver probe: failed node versus committed checkpoint, no model calls."""
import asyncio
import json
import os
import runpy
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

runpy.run_path('docs/v2/v2-02/evidence/linux-pg-launcher.py')['configure']()
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class State(TypedDict):
    attempts: int

async def main():
    thread = 'v203-fix01-probe-' + uuid4().hex
    config = {'configurable': {'thread_id': thread}}
    local = {'attempts': 0, 'fail': True}
    async with AsyncPostgresSaver.from_conn_string(os.environ['AGENT_TEST_DATABASE_URL']) as saver:
        async def node(state):
            local['attempts'] += 1
            if local['fail']:
                raise RuntimeError('controlled interruption after in-memory attempt')
            return {'attempts': state['attempts'] + 1}
        graph = StateGraph(State)
        graph.add_node('call', node)
        graph.add_edge(START, 'call')
        graph.add_edge('call', END)
        graph = graph.compile(checkpointer=saver)
        report = {'guard': 'launcher: agent_demo_test / agent_test / PG 170012 / codex-task131-0e62'}
        try:
            try:
                await graph.ainvoke({'attempts': 0}, config, durability='sync')
            except RuntimeError:
                report['failure'] = 'controlled node exception'
            snapshot = await graph.aget_state(config)
            saved = await saver.aget_tuple(snapshot.config)
            report.update(local_attempts_after_failure=local['attempts'], checkpoint_values=snapshot.values,
                          next_nodes=list(snapshot.next), pending_write_channels=[item[1] for item in saved.pending_writes])
            local['fail'] = False
            result = await graph.ainvoke(None, config, durability='sync')
            report.update(local_attempts_after_resume=local['attempts'], resumed_values=result)
        finally:
            await saver.adelete_thread(thread)
            report['cleanup_thread_absent'] = await saver.aget_tuple(config) is None
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))

asyncio.run(main())
