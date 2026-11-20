"""Independent real-Saver interruption, receipts and committed-result probe."""
import asyncio, json, os, runpy, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from app.runtime.selection_reservation import SelectionReservation
from app.tools.discovery import PurposeSpec
from app.tools.selector import ToolSelector, SelectorOutput
from app.agents.types import AgentType, TaskType
from app.graph.contracts import ExecutionContext
from app.runtime.model_gateway import ModelGateway, ModelCallLimits
from test_tool_progressive_disclosure import _build_full_registry, _scope, _structured_resp, ControlledSelectorAndBusinessModel

class State(TypedDict):
 user_id:str; conversation_id:str; task_id:str; run_id:str; model_call_usage:dict; tool_selection_record:dict; selector_receipts:list; task_status:str

async def scenario(thread,owner,mode):
 async with AsyncPostgresSaver.from_conn_string(os.environ['AGENT_TEST_DATABASE_URL']) as saver:
  reserve=SelectionReservation(saver,thread_id=thread,owner=owner,run_id='run1',source_checkpoint_id=None)
  scope=_scope(); scope.selection_reservation=reserve
  model=ControlledSelectorAndBusinessModel([_structured_resp(SelectorOutput(action='use_tools',tool_names=['get_order']))])
  selector=ToolSelector(_build_full_registry(),ModelGateway(model,ModelCallLimits(8,10,0)))
  purpose=PurposeSpec('qa.multi',AgentType.ORDER,TaskType.ORDER_QUERY,frozenset({'get_order','list_orders'}))
  execution=ExecutionContext(**owner,workflow_id=owner['task_id'],run_id='run1')
  async def node(state):
   out=await selector.select(execution=execution,agent_type=AgentType.ORDER,task_type=TaskType.ORDER_QUERY,purpose_spec=purpose,permission_scopes=frozenset({'orders:read'}),scope=scope,need_text='query')
   assert out.status=='selected' and out.selector_called
   if mode=='kill': os._exit(71)
   if mode=='exception': raise RuntimeError('controlled interruption')
   return {'model_call_usage':{'model_attempts':scope.model_usage().model_attempts},'tool_selection_record':out.record.model_dump(mode='json'),'selector_receipts':scope.selector_receipts,'task_status':'completed'}
  graph=StateGraph(State);graph.add_node('call',node);graph.add_edge(START,'call');graph.add_edge('call',END);graph=graph.compile(checkpointer=saver)
  cfg={'configurable':{'thread_id':thread}}
  try:
   await graph.ainvoke({**owner,'run_id':'run1','model_call_usage':{'model_attempts':0},'tool_selection_record':{},'selector_receipts':[],'task_status':'running'},cfg,durability='sync')
  except RuntimeError as error:
   if mode!='exception' or str(error)!='controlled interruption': raise
  snap=await graph.aget_state(cfg); stored=await saver.aget_tuple(snap.config); snap=snap._replace(values=stored.checkpoint['channel_values'])
  resumed=SelectionReservation(saver,thread_id=thread,owner=owner,run_id='run2',source_checkpoint_id=snap.config['configurable']['checkpoint_id'])
  try:
   await resumed.load(snap); outcome='confirmed'
  except ValueError:
   outcome='rejected_unknown'
  print(json.dumps({'mode':mode,'outcome':outcome,'root_attempts':snap.values['model_call_usage']['model_attempts'],'floor':resumed.value['attempts'],'receipts':resumed.value['selector_receipts'],'inflight':resumed.value['inflight']},ensure_ascii=True),flush=True)
  assert outcome==('confirmed' if mode=='success' else 'rejected_unknown')
  assert resumed.value['attempts']==1 and len(resumed.value['selector_receipts'])==1
  if mode=='success':
   await resumed.begin_existing(1);assert resumed.value['attempts']==1

async def parent():
 runpy.run_path(str(ROOT/'docs/v2/v2-02/evidence/linux-pg-launcher.py'))['configure']()
 async with AsyncPostgresSaver.from_conn_string(os.environ['AGENT_TEST_DATABASE_URL']) as saver:
  for mode in ('exception','success','kill'):
   token=uuid4().hex;thread='v203-independent-'+token;owner={'user_id':'qa-'+token,'conversation_id':'qa-'+token,'task_id':'qa-'+token}
   try:
    if mode=='kill':
     p=subprocess.run([sys.executable,__file__,'child',thread,json.dumps(owner)],capture_output=True,timeout=45)
     assert p.returncode==71, f'child exit {p.returncode}; stderr={p.stderr.decode(errors="replace")}'
     cfg={'configurable':{'thread_id':thread,'checkpoint_ns':'v203-reservation:'+owner['task_id']}}
     saved=await saver.aget_tuple(cfg);value=saved.checkpoint['channel_values'];root=await saver.aget_tuple({'configurable':{'thread_id':thread}})
     print(json.dumps({'mode':'kill','exit':p.returncode,'floor':value['attempts'],'root_attempts':root.checkpoint['channel_values']['model_call_usage']['model_attempts'],'inflight':value['inflight'],'receipts':value['selector_receipts']},ensure_ascii=True),flush=True)
     assert value['attempts']==1 and value['inflight'] and root.checkpoint['channel_values']['model_call_usage']['model_attempts']==0 and len(value['selector_receipts'])==1
    else: await scenario(thread,owner,mode)
   finally:
    await saver.adelete_thread(thread)
    assert await saver.aget_tuple({'configurable':{'thread_id':thread}}) is None
    assert await saver.aget_tuple({'configurable':{'thread_id':thread,'checkpoint_ns':'v203-reservation:'+owner['task_id']}}) is None
    print(json.dumps({'mode':mode,'cleaned':True}),flush=True)

if os.name=='nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
if len(sys.argv)>1: asyncio.run(scenario(sys.argv[2],json.loads(sys.argv[3]),'kill'))
else: asyncio.run(parent())
