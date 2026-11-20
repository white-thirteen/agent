"""Private local launcher: redirect existing full gate to guarded validation only."""
import argparse,os,runpy,sys,pathlib
sys.path.insert(0,str(pathlib.Path.cwd()))
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from dotenv import dotenv_values
from app.core.config import Settings
p=argparse.ArgumentParser(); p.add_argument('--port',required=True,type=int); p.add_argument('--comment',required=True); p.add_argument('--output',required=True); p.add_argument('--qwen-evidence',required=True); a=p.parse_args()
assert a.port!=5432
original=Settings(); admin=dotenv_values('.env').get('AGENT_DATABASE_ADMIN_URL'); assert admin
urls={'AGENT_DATABASE_URL':original.database_url.get_secret_value(),'AGENT_TEST_DATABASE_URL':original.test_database_url.get_secret_value(),'AGENT_DATABASE_ADMIN_URL':admin}
def redirected(value):
    x=conninfo_to_dict(value); x['port']=str(a.port); x.pop('hostaddr',None); return make_conninfo(**x)
urls={k:redirected(v) for k,v in urls.items()}
with psycopg.connect(urls['AGENT_DATABASE_ADMIN_URL'],autocommit=True,options='-c default_transaction_read_only=on') as c:
    row=c.execute("SELECT current_setting('server_version_num'),shobj_description(oid,'pg_database') FROM pg_database WHERE datname='postgres'").fetchone()
    assert row==('170012',a.comment),'Unexpected validation target; no tests started'
os.environ.update(urls)
sys.argv=['scripts.verify_06_delivery','--output',a.output,'--qwen-evidence',a.qwen_evidence]
print('VALIDATION_TARGET_GUARD_PASSED; original database endpoints excluded',flush=True)
runpy.run_module('scripts.verify_06_delivery',run_name='__main__')
