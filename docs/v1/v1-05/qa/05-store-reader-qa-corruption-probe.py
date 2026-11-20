import sys,json
from pathlib import Path
from dataclasses import replace
from uuid import uuid4
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,str(Path.cwd()/'tests'))
from app.core.config import Settings
from app.infrastructure.postgres import open_pool,validate_test_target
from app.infrastructure.store import store_resources
from app.memory.manager import MemoryManager,preference_namespace
from app.memory.reader import MemoryReader
from app.tools.implementations.memory import read_preferences_tool
from app.tools.registry import ToolRegistry
from app.tools.executor import ToolExecutor
from app.tools.policy import ToolPolicy
from app.graph.specialists.order.builder import build_order_graph
from app.graph.transfers import create_specialist_state
from test_memory_reader import setup,profile
from test_memory_postgres import database_snapshot
from langgraph.store.base import PutOp
from scripts import run_async
async def main():
 base=Settings();validate_test_target(base.test_database_url,base.database_url)
 user='qa531-corrupt-'+uuid4().hex
 s=Settings(_env_file=None,app_env='test',database_url=base.test_database_url,test_database_url=base.test_database_url,demo_user_ids=(user,))
 pool=await open_pool(s);before=await database_snapshot(pool);evidence={}
 try:
  async with store_resources(s) as r:
   registry=ToolRegistry();registry.register(read_preferences_tool(MemoryReader(MemoryManager(r,user_ids=(user,))),enabled=True));registry.freeze()
   graph=build_order_graph(gateway=None,registry=registry,executor=ToolExecutor(registry,ToolPolicy()))
   async def invoke():
    _,_,_,runtime,state=setup(r)
    ctx=runtime.context.context.model_copy(update={'user_id':user})
    runtime.context=replace(runtime.context,context=ctx)
    request=state['request'].model_copy(update={'context':ctx,'messages':[]})
    return await graph.ainvoke(create_specialist_state(request,scope=runtime.context.scope),context=runtime.context)
   await r.abatch([PutOp(preference_namespace(user),'profile',{**profile(),'schema_version':2})])
   out=await invoke()
   assert out['result'].status=='needs_input' and out['memory_read_status']=='unavailable'
   assert out['memory_read_record']['result']['status']=='failed' and out['memory_read_record']['result']['code']=='memory_profile_invalid'
   evidence['unknown_schema']='failed/memory_profile_invalid, optional core needs_input PASS'
   async with pool.connection() as conn:
    await conn.execute("UPDATE store SET value='[]'::jsonb WHERE prefix=%s AND key='profile'",('.'.join(preference_namespace(user)),))
   try: await invoke()
   except Exception as exc:
    evidence['nonobject_compiled_order_graph']={'exception':type(exc).__name__,'message':str(exc),'expected':'failed/memory_profile_invalid; optional core continues'}
   else: raise AssertionError('Expected current corruption reproduction did not occur')
 finally:
  async with store_resources(s) as r: await r.abatch([PutOp(preference_namespace(user),'profile',None)])
  assert await database_snapshot(pool)==before
  await pool.close();evidence['exact_cleanup_all_public_rows_columns_unchanged']=True
  print(json.dumps(evidence))
run_async(main())
