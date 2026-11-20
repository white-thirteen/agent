import asyncio,json,tempfile
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg_pool import AsyncConnectionPool
from app.context.archive_store import ArchiveStore
from app.context.manager import ContextManager
from app.context.models import SessionIdentity,PublicInteraction,PublicMessage
from app.context.repository import ArchiveRepository
j=json.load(open('.git/v202-local-pg-private.json',encoding='utf-8')); dsn=make_conninfo(host=j['host'],port=j['port'],dbname=j['database'],user=j['user'],password=j['password'])
assert j['host']=='127.0.0.1' and int(j['port'])==56422
schema='ctx212_'+uuid4().hex
async def run():
 async with await psycopg.AsyncConnection.connect(dsn,autocommit=True) as c:
  row=await (await c.execute("SELECT current_database(),current_user,current_setting('server_version_num'),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()")).fetchone()
  assert row==('agent_context_test','agent_test','170012','codex-v202-local-20261119')
  await c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
  try:
   await c.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
   await c.execute(Path('migrations/008_context_archive.sql').read_text(encoding='utf-8'))
   async with AsyncConnectionPool(dsn,kwargs={'options':f'-csearch_path={schema}'},open=False,min_size=1,max_size=2) as pool:
    with tempfile.TemporaryDirectory() as root:
     repo=ArchiveRepository(pool); m=ContextManager(repo,ArchiveStore(root)); ident=SessionIdentity(user_id='u',conversation_id='c')
     for k,t in [('a','target'),('b','target'),('c','other')]:
      msgs=(PublicMessage(message_id=k+'1',role='user',content=k,task_id=t),PublicMessage(message_id=k+'2',role='assistant',content=k,task_id=t))
      item=PublicInteraction(task_id=t,task_status='COMPLETED',messages=msgs)
      await m.publish(ident,'cp',[item],retain_recent=0,max_messages=2,session_status='COMPLETED')
     task=await repo.candidates(ident,limit=2,task_id='target'); assert [r.message_ids[0] for r in task]==['b1','a1']
     message=await repo.candidates(ident,limit=1,message_id='a1'); assert message[0].message_ids[0]=='a1'
     other=await repo.candidates(SessionIdentity(user_id='u',conversation_id='other'),limit=3,task_id='target'); assert other==[]
     print('PASS: task spanning two segments, message anchor and same-user other-conversation isolation')
  finally:
   await c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
   assert await (await c.execute('SELECT count(*) FROM pg_namespace WHERE nspname=%s',(schema,))).fetchone()==(0,)
   print('PASS: unique schema removed')
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); asyncio.run(run())
