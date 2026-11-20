import pathlib,importlib.util,json,subprocess,os,time,uuid,socket
root=pathlib.Path('/home/white7/agent-db-backups/20261117-rehearsal-7c93e5')
os.umask(0o077)
script=root/'rehearse_v2_01_pg1712_restore-v2.py'
spec=importlib.util.spec_from_file_location('rehearse',script); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
b=root/'pg176-20261117T051950Z-6ddfec59da38'; manifest=json.loads((b/'private-manifest.json').read_text())
r=json.loads((root/'restore-phase.json').read_text()); token=r['token']; candidate=r['container']
assert candidate=='codex-pg1712restore-228a7f5b8d92' and token=='228a7f5b8d92'
p=root/('final-proof-'+uuid.uuid4().hex[:8]); p.mkdir(mode=0o700)
c=m.Commands(p,90)
def inspect():
    d=json.loads(c.run('docker','inspect',candidate,private=True))[0]
    assert d['Config']['Labels']['codex.pg1712restore']==token
    assert [x['Name'] for x in d['Mounts'] if x['Type']=='volume']==[r['volume']]
    assert len(d['NetworkSettings']['Networks'])==1
    network=d['NetworkSettings']['Networks'][r['network']]
    return {'id':d['Id'],'started_at':d['State']['StartedAt'],'running':d['State']['Running'],'volume':r['volume'],'network':r['network'],'ip':network['IPAddress'],'port_bindings':d['NetworkSettings']['Ports']}
def sql(db,value):
    return c.run('docker','exec',candidate,'psql','-X','-qAt','-U','agent_bootstrap','-d',db,'-v','ON_ERROR_STOP=1','-c',value)
e={'token':token,'source_before':m.source_identity(c),'candidate_before':inspect()}
assert sql('postgres',"SELECT current_setting('server_version_num')")=='170012'
t=time.monotonic(); c.run('docker','restart','--time','30',candidate,timeout=90)
for i in range(60):
    try:
        if sql('postgres','SELECT 1')=='1': break
    except RuntimeError: time.sleep(1)
else: raise RuntimeError('candidate restart not ready')
e['restart_seconds']=time.monotonic()-t; e['candidate_after']=inspect(); assert e['candidate_before']['started_at']!=e['candidate_after']['started_at']
e['candidate_packages']=c.run('docker','exec',candidate,'dpkg-query','-W','postgresql-17','postgresql-client-17','postgresql-17-pgvector','postgresql-17-pg-search')
e['restart_fixtures']={}
for db in m.DATABASES:
    schema=r['fixture_schema']; v=json.loads(sql(db,f'SELECT json_build_array(count(*),min(vector_dims(v)),max(vector_dims(v))) FROM {schema}.vectors'))
    hit=sql(db,f"SELECT id FROM {schema}.chunks WHERE body ||| '退款'")
    assert v==[2,1024,1024] and hit=='restore-chunk'
    e['restart_fixtures'][db]={'vectors':v,'bm25_hit':hit,'extensions':sql(db,'SELECT extname||\':\'||extversion FROM pg_extension ORDER BY extname')}
e['source_comparison']=m.live_data_comparison(c,manifest['databases'])
e['source_after']=m.source_identity(c); e['source_identity_unchanged']=e['source_before']==e['source_after']
e['source_config_roles_unchanged']=m.sensitive_state(c)==json.loads((b/'backup-evidence.json').read_text())['sensitive_before']
e['source_data_unchanged']=all(not x['changed_tables'] and x['schema_unchanged'] and x['sequences_unchanged'] for x in e['source_comparison'].values())
e['source_globals_match']=m.globals_digest(m.normalized_globals(c))==json.loads((b/'backup-evidence.json').read_text())['sensitive_before']['roles_sha256']
e['retained_volumes']=c.run('docker','volume','ls','--format','{{.Name}}').splitlines()
e['network_internal']=json.loads(c.run('docker','network','inspect',r['network'],private=True))[0]['Internal']
e['actual_tunnel']={'windows_host':'127.0.0.1','windows_port':15633,'ssh_host':'192.168.150.101','candidate_ip':e['candidate_after']['ip'],'candidate_port':5432,'requested_vm_56321_not_published':True}
e['root_free_bytes']=__import__('shutil').disk_usage('/').free
assert all(e[k] for k in ['source_identity_unchanged','source_config_roles_unchanged','source_data_unchanged','source_globals_match','network_internal'])
e['status']='RESTART_AND_SOURCE_PROTECTION_PASSED'; e['commands']=c.events
m.write_json(root/'final-proof.json',e); m.transfer_owner(p,root); os.chown(root/'final-proof.json',1000,1000); os.sync(); print(json.dumps({'status':e['status'],'restart_seconds':e['restart_seconds'],'free':e['root_free_bytes']}))
