import asyncio, concurrent.futures, json, tempfile, threading
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
j=json.load(open('.git/v202-local-pg-private.json',encoding='utf-8'))
dsn=make_conninfo(host=j['host'],port=j['port'],dbname=j['database'],user=j['user'],password=j['password'])
assert j['host']=='127.0.0.1' and int(j['port'])==56422
schema='ctx212_'+uuid4().hex
barrier=threading.Barrier(2,timeout=20)
class Store(ArchiveStore):
 def publish(self,path,data):
  barrier.wait()
  return super().publish(path,data)
async def work(root):
 pool=AsyncConnectionPool(dsn,kwargs={'options':f'-csearch_path={schema}'},open=False,min_size=1,max_size=1)
 async with pool:
  m=ContextManager(ArchiveRepository(pool),Store(root)); i=SessionIdentity(user_id='parallel',conversation_id='one')
  msgs=(PublicMessage(message_id='m1',role='user',content='question',task_id='t'),PublicMessage(message_id='m2',role='assistant',content='answer',task_id='t'))
  interaction=PublicInteraction(task_id='t',task_status='COMPLETED',messages=msgs)
  return await m.publish(i,'cp',[interaction],retain_recent=0,max_messages=2,session_status='COMPLETED')
def run(root):
 asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
 return asyncio.run(work(root))
with psycopg.connect(dsn,autocommit=True) as c:
 assert c.execute("SELECT current_database(),current_user,current_setting('server_version_num'),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()==('agent_context_test','agent_test','170012','codex-v202-local-20261119')
 c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
 try:
  c.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
  c.execute(Path('migrations/008_context_archive.sql').read_text(encoding='utf-8'))
  with tempfile.TemporaryDirectory() as root, concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
   a,b=list(executor.map(run,[root,root])); assert a==b and a.status=='READY'
   assert c.execute('SELECT count(*),min(status) FROM context_archive').fetchone()==(1,'READY')
   print('PASS: two concurrent first publishers, same READY archive, one database row')
 finally:
  c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
  assert c.execute('SELECT count(*) FROM pg_namespace WHERE nspname=%s',(schema,)).fetchone()==(0,)
  print('PASS: unique schema removed')
