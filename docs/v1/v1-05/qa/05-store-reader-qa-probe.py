import asyncio, json, os, sys, subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path.cwd()/'tests'))
from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from app.infrastructure.store import store_resources
from app.memory.manager import MemoryManager, preference_namespace
from app.memory.reader import MemoryReader
from app.tools.implementations.memory import read_preferences_tool
from app.tools.registry import ToolRegistry
from app.tools.policy import ToolPolicy
from app.tools.executor import ToolExecutor
from app.graph.specialists.preferences import read_optional_preferences
from app.graph.specialists.order.builder import build_order_graph
from app.graph.specialists.refund.builder import build_refund_graph
from app.graph.specialists.knowledge.builder import build_knowledge_graph
from app.graph.transfers import create_specialist_state
from app.agents.types import AgentType, TaskType
from langgraph.store.base import PutOp
from test_memory_reader import setup, profile
from test_memory_postgres import database_snapshot
from scripts import run_async

async def main():
 base=Settings()
 validate_test_target(base.test_database_url,base.database_url)
 tag='qa531-'+uuid4().hex
 users=(tag+'-a',tag+'-b')
 s=Settings(_env_file=None,app_env='test',database_url=base.test_database_url,test_database_url=base.test_database_url,demo_user_ids=users)
 pool=await open_pool(s)
 before=await database_snapshot(pool)
 events=[]
 try:
  async with store_resources(s) as resource:
   manager=MemoryManager(resource,user_ids=users)
   await resource.abatch([PutOp(preference_namespace(users[0]),'profile',profile(answer_language='en',answer_style='concise'))])
   class CountResource:
    def __init__(self): self.calls=0
    async def aget(self,*args):
     self.calls+=1
     return await resource.aget(*args)
   counter=CountResource()
   registry=ToolRegistry()
   registry.register(read_preferences_tool(MemoryReader(MemoryManager(counter,user_ids=users)),enabled=True));registry.freeze()
   executor=ToolExecutor(registry,ToolPolicy())
   for agent,task in [(AgentType.ORDER,TaskType.ORDER_QUERY),(AgentType.REFUND,TaskType.REFUND_APPLY),(AgentType.KNOWLEDGE,TaskType.KNOWLEDGE_QA)]:
    _,_,_,runtime,state=setup(counter,scopes=frozenset({'memory:read','knowledge:read'}))
    ctx=runtime.context.context.model_copy(update={'user_id':users[0],'conversation_id':tag+'-'+agent.value,'task_id':tag+'-'+agent.value,'workflow_id':tag+'-'+agent.value})
    runtime.context=replace(runtime.context,context=ctx,thread_id=tag+'-thread-'+agent.value)
    request=state['request'].model_copy(update={'context':ctx,'task_id':ctx.task_id,'agent_type':agent,'task_type':task,'messages':[]})
    if agent is AgentType.ORDER: graph=build_order_graph(gateway=None,registry=registry,executor=executor)
    elif agent is AgentType.REFUND: graph=build_refund_graph(gateway=None,registry=registry,executor=executor,approval_service=None,refund_service=None)
    else: graph=build_knowledge_graph(gateway=object(),registry=registry,executor=executor,profile='test')
    out=await graph.ainvoke(create_specialist_state(request,scope=runtime.context.scope),context=runtime.context)
    assert out['result'].status=='needs_input' and out['memory_context']['preferences']=={'answer_language':'en','answer_style':'concise'}
    assert out['run_usage']['tool_calls']==1 and out['memory_read_record']['result']['attempts']==1
    assert not out['messages']
    events.append(agent.value+' real PG preparation PASS')
   assert counter.calls==3
   assert (await manager.snapshot(user_id=users[1])).status=='empty'
   _,_,_,runtime,state=setup(counter,scopes=frozenset())
   ctx=runtime.context.context.model_copy(update={'user_id':users[0]});runtime.context=replace(runtime.context,context=ctx)
   state['request']=state['request'].model_copy(update={'context':ctx})
   denied=await read_optional_preferences(state,runtime,registry=registry,executor=executor,node='prepare_query')
   assert denied['memory_read_status']=='denied' and denied['memory_read_record']['result']['attempts']==0 and counter.calls==3
   events.append('missing scope zero Store access PASS')
   await resource.abatch([PutOp(preference_namespace(users[0]),'profile',profile(answer_language='en',answer_style='PRIVATE_BAD'))])
   partial=await manager.snapshot(user_id=users[0]);assert partial.status=='partial' and partial.preferences=={'answer_language':'en'} and 'PRIVATE_BAD' not in partial.model_dump_json()
   events.append('real PG partial safe projection PASS')
   await resource.abatch([PutOp(preference_namespace(users[0]),'profile',profile(answer_language='en'))])
  code='''from app.core.config import Settings
from app.infrastructure.store import store_resources
from app.memory.manager import MemoryManager
from scripts import run_async
import os
async def main():
 s=Settings().model_copy(update={"database_url":Settings().test_database_url})
 async with store_resources(s) as r:
  u=os.environ['QA531_USER'];print((await MemoryManager(r,user_ids=(u,)).snapshot(user_id=u)).model_dump_json())
run_async(main())'''
  process=await asyncio.to_thread(subprocess.run,[sys.executable,'-c',code],env={**os.environ,'QA531_USER':users[0]},capture_output=True,timeout=30)
  assert process.returncode==0 and not process.stderr
  assert json.loads(process.stdout)['preferences']=={'answer_language':'en'}
  events.append('complete new Python process persistence PASS')
  async with store_resources(s) as resource:
   # Corruption fixture uses exact owned row only. Store API correctly only permits object writes.
   async with pool.connection() as conn:
    await conn.execute("UPDATE store SET value='[]'::jsonb WHERE prefix=%s AND key='profile'",('.'.join(preference_namespace(users[0])),))
   try:
    await MemoryManager(resource,user_ids=users).snapshot(user_id=users[0])
   except BaseException as exc:
    events.append('non-object profile exception '+type(exc).__name__+' '+str(exc)[:120])
    from app.tools.models import ToolUnavailableError
    assert isinstance(exc,ToolUnavailableError) and exc.code=='memory_profile_invalid', 'Non-object JSON not safely classified'
   else: raise AssertionError('Corrupt profile accepted')
   events.append('real PG nonobject safe classification PASS')
 finally:
  async with store_resources(s) as resource:
   await resource.abatch([PutOp(preference_namespace(users[0]),'profile',None)])
  assert await database_snapshot(pool)==before
  await pool.close()
  print(json.dumps({'events':events,'exact_cleanup_and_all_public_rows_columns_unchanged':True},ensure_ascii=False))
run_async(main())
