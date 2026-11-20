import sys,pathlib,argparse,json,asyncio,time
sys.path.insert(0,str(pathlib.Path.cwd()))
import psycopg,httpx,uvicorn
from dotenv import dotenv_values
from app.core.config import Settings
from app.main import create_app
from scripts import run_async
p=argparse.ArgumentParser(); p.add_argument('--docker-receipt',required=True,type=pathlib.Path); p.add_argument('--output',required=True,type=pathlib.Path); a=p.parse_args(); assert not a.output.exists()
r=json.loads(a.docker_receipt.read_text(encoding='utf-8')); s=Settings()
with psycopg.connect(dotenv_values('.env')['AGENT_DATABASE_ADMIN_URL'],autocommit=True,options='-c default_transaction_read_only=on') as c:
    row=c.execute("SELECT current_setting('server_version_num'),system_identifier::text FROM pg_control_system()").fetchone()
    assert row==('170012',r['system_identifier'])
async def check():
    app=create_app(s); server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8633,log_level='critical'))
    task=asyncio.create_task(server.serve()); started=time.monotonic(); result={'server_version_num':row[0],'system_identifier':row[1],'embedding_enabled':s.embedding_enabled}
    try:
        async with asyncio.timeout(180):
            while not server.started:
                if task.done(): await task; raise AssertionError('Health application exited before readiness')
                await asyncio.sleep(.1)
        async with httpx.AsyncClient() as client:
            h=await client.get('http://127.0.0.1:8633/health'); h.raise_for_status(); result['health']=h.json()
        assert result['health']['database_status']==result['health']['checkpoint_status']==result['health']['store_status']=='ready'
        assert result['health']['agent_ready']
        result['startup_seconds']=round(time.monotonic()-started,3)
    finally:
        server.should_exit=True; await task
    result['business_pool_closed']=app.state.pool.closed; result['checkpoint_pool_closed']=app.state.checkpoint_pool.closed
    assert result['business_pool_closed'] and result['checkpoint_pool_closed']
    result['remaining_async_tasks']=[t.get_name() for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]; assert not result['remaining_async_tasks']
    result['status']='POST_UPGRADE_APPLICATION_HEALTH_PASSED'; return result
result=run_async(check()); a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'status':result['status'],'startup_seconds':result['startup_seconds']}))
