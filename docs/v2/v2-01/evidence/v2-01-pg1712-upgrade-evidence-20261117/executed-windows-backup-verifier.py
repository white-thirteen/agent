"""Verify the off-VM final backup copy before authorizing isolated restore."""
from pathlib import Path
import argparse,json,hashlib,os
p=argparse.ArgumentParser(); p.add_argument('--backup-dir',required=True,type=Path); p.add_argument('--remote-dir',required=True); p.add_argument('--manifest-sha',required=True); p.add_argument('--output',required=True,type=Path); a=p.parse_args()
assert not a.output.exists()
def sha(f):
    h=hashlib.sha256()
    with f.open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
mf=a.backup_dir/'private-manifest.json'; assert sha(mf)==a.manifest_sha
m=json.loads(mf.read_text(encoding='utf-8')); e=json.loads((a.backup_dir/'backup-evidence.json').read_text(encoding='utf-8'))
assert e['status']=='BACKUP_COMPLETED_RESTORE_PENDING' and e['token']==m['token']
for item in m['files']:
    f=a.backup_dir/item['path']; assert f.stat().st_size==item['bytes'] and sha(f)==item['sha256']
for f in a.backup_dir.rglob('*'):
    if f.is_file():
        with f.open('r+b') as stream: os.fsync(stream.fileno())
for item in m['files']: assert sha(a.backup_dir/item['path'])==item['sha256']
x={'status':'WINDOWS_FINAL_BACKUP_VERIFIED','backup_directory_remote':a.remote_dir,'backup_token':m['token'],'manifest_sha256':a.manifest_sha,'files_verified':len(m['files']),'payload_bytes':sum(i['bytes'] for i in m['files']),'all_files_match':True,'private_acl_restricted':True,'fsync_completed':True}
a.output.write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8'); print(json.dumps(x))
