"""Exercise V203 task reservation with an isolated real PostgreSQL Saver."""
import asyncio
import json
import os
import runpy
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

runpy.run_path('docs/v2/v2-02/evidence/linux-pg-launcher.py')['configure']()
from app.runtime.selection_reservation import SelectionReservation
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    thread = 'v203-reservation-test-' + uuid4().hex
    owner = {'user_id': 'isolated-user', 'conversation_id': 'isolated-conversation', 'task_id': 'isolated-task'}
    async with AsyncPostgresSaver.from_conn_string(os.environ['AGENT_TEST_DATABASE_URL']) as saver:
        first = SelectionReservation(saver, thread_id=thread, owner=owner, run_id='run', source_checkpoint_id='source')
        report = {}
        try:
            await first.begin(1, 1)
            await first.reserve_attempt(2)
            saved = await saver.aget_tuple({'configurable': {'thread_id': thread, 'checkpoint_ns': 'v203-reservation:isolated-task'}})
            report['saved_floor'] = saved.checkpoint['channel_values']['attempts']
            report['saved_rediscoveries'] = saved.checkpoint['channel_values']['rediscoveries']
            second = SelectionReservation(saver, thread_id=thread, owner=owner, run_id='run', source_checkpoint_id='source')
            try:
                await second.load(type('Snapshot', (), {'values': {'model_call_usage': {'model_attempts': 1}}, 'next': ('call',)})())
            except ValueError:
                report['inflight_rejected'] = True
        finally:
            await saver.adelete_thread(thread)
            report['cleanup_thread_absent'] = await saver.aget_tuple({'configurable': {'thread_id': thread, 'checkpoint_ns': 'v203-reservation:isolated-task'}}) is None
        print(json.dumps(report, sort_keys=True))

asyncio.run(main())
