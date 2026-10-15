from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parent/'2026-10-15-octop-n09-session-delivery'
def read(p): return json.loads((HERE/p).read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(p):
    line=[x for x in (HERE/p).read_text().splitlines() if re.search(r'\d+ passed',x)][-1]
    return {'summary':line,'passed':int(re.search(r'(\d+) passed',line)[1]),'skipped':int(re.search(r'(\d+) skipped',line)[1]) if ' skipped' in line else 0}
for n in ['socket-final-related','postgres-current','static','backend-image-build','image-runtime','backend-full','upgrade','brand-staged']:
    d=read(n+'-result.json'); assert d['complete'] and d['returncode']==0,n
inputs=read('inputs.json')['sha256']
assert all(sha(ROOT/p)==h for p,h in inputs.items())
b=read('backend-driver.json'); assert b['complete'] and b['returncode']==0 and b['all_inputs_unchanged']
image=read('image-proof.json'); assert image['backend_image']==b['backend_image'] and image['owned_test_container_removed']
assert all(v['matches'] and sha(ROOT/p)==v['sha256'] for p,v in image['files'].items())
pg=read('postgres.json'); assert pg['passed'] and pg['returncode']==0 and pg['owned_container_removed']
u=read('upgrade.json'); assert u['complete'] and u['host_changed'] is False and len(u['versions'])==3 and all(v['returncode']==0 for v in u['versions'])
base=json.loads((BASE/'validation.json').read_text())
front={p:h for p,h in json.loads((BASE/'inputs.json').read_text())['sha256'].items() if p.startswith('frontend/')}
assert all(inputs[p]==h for p,h in front.items())
for k in ['source_distribution_inventory_reuse','service_image_reuse']:
    assert all(sha(ROOT/p)==h for p,h in base[k]['sha256'].items())
logs=sorted((HERE/'logs').glob('*.log'))+[HERE/'postgres-runtime.log']
v={'base_commit':'f76e3eb','branch':'codex/octop-integration','status':'terminal_connection_current_session_accepted_M1_pending','backend':stats('logs/backend-full.log'),'related':stats('logs/socket-final-related.log'),'postgres':stats('postgres-runtime.log')|{'actual_scope':'owned PostgreSQL Config plus original User/Session TIMESTAMPTZ in socket tests; real local bash PTY except explicit isolated backpressure unit; original shared terminal fixtures use explicitly owned SQLite Auth; no real SSH/deployment','owned_container_removed':True},'image':image,'image_tests':stats('logs/image-runtime.log'),'upgrade':{'complete':True,'host_changed':False,'host_inputs':len(u['host_contract_sha256s']),'stages':[x['pytest'].splitlines()[-1] for x in u['versions']]},'input_count':len(inputs),'frontend_reuse':{'base_commit':'f76e3eb','unchanged_input_count':len(front),'scope':base['frontend_reuse']},'source_distribution_inventory_reuse':base['source_distribution_inventory_reuse'],'service_image_reuse':base['service_image_reuse'],'boundaries':['M1 not exited; N08 not started','connection-specific session authorization remains transient and independent from shared PTY resource authorization','closing/revoking one socket is not proof of remote cancellation or rollback','no cross-origin policy, real SSH/Kubernetes/model/ticket, generic Secret, delegated lifecycle or remote CI acceptance','all original N/O/F goals and gates retained; no push/deploy/release'],'raw_log_sha256':{p.relative_to(HERE).as_posix():sha(p) for p in logs}}
(HERE/'validation.json').write_text(json.dumps(v,indent=2)+'\n')
print(json.dumps({k:v[k] for k in ['status','backend','postgres','image_tests','upgrade','input_count']}))
