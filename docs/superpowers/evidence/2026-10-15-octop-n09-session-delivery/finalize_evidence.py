"""Accept current session delivery only from completed frozen-input gates."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parent/'2026-10-15-octop-n09-actor-status'
def read(p): return json.loads((HERE/p).read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(p):
    lines=[line for line in (HERE/p).read_text().splitlines() if re.search(r'\d+ passed',line)]
    assert lines,p
    line=lines[-1]
    return {'summary':line,'passed':int(re.search(r'(\d+) passed',line)[1]),'skipped':int(re.search(r'(\d+) skipped',line)[1]) if ' skipped' in line else 0}
for name in ['session-final-related','session-native-integration','postgres-native','static','backend-image-build','image-runtime','backend-full','upgrade','brand-staged']:
    d=read(name+'-result.json')
    assert d['complete'] and d['returncode']==0,name
inputs=read('inputs.json')['sha256']
assert all(sha(ROOT/p)==h for p,h in inputs.items())
b=read('backend-driver.json')
assert b['complete'] and b['returncode']==0 and b['all_inputs_unchanged']
image=read('image-proof.json')
assert image['backend_image']==b['backend_image'] and image['owned_test_container_removed']
assert all(v['matches'] and sha(ROOT/p)==v['sha256'] for p,v in image['files'].items())
pg=read('postgres.json')
assert pg['passed'] and pg['returncode']==0 and pg['owned_container_removed']
u=read('upgrade.json')
assert u['complete'] and u['host_changed'] is False and len(u['versions'])==3 and all(v['returncode']==0 for v in u['versions'])
base=json.loads((BASE/'validation.json').read_text())
front={p:h for p,h in json.loads((BASE/'inputs.json').read_text())['sha256'].items() if p.startswith('frontend/')}
assert all(inputs[p]==h for p,h in front.items())
source=base['source_distribution_inventory_reuse']
assert all(sha(ROOT/p)==h for p,h in source['sha256'].items())
service=base['service_image_reuse']
assert all(sha(ROOT/p)==h for p,h in service['sha256'].items())
logs=sorted((HERE/'logs').glob('*.log'))+[HERE/'postgres-runtime.log']
v={'base_commit':'40b7971','branch':'codex/octop-integration','status':'original_auth_session_expiry_and_http_delivery_accepted_M1_pending','backend':stats('logs/backend-full.log'),'related':stats('logs/session-final-related.log'),'native_routes':stats('logs/session-native-integration.log'),'postgres':stats('postgres-runtime.log')|{'actual_scope':'original User/Session tables on owned PostgreSQL, TIMESTAMPTZ and legacy optional-column queries, real logout and idle SSE delivery plus original native artifact/history/Range routes; mocked tenant resolver selects the explicit owned scope; no real deployment','owned_container_removed':True},'image':image,'image_tests':stats('logs/image-runtime.log'),'upgrade':{'complete':True,'host_changed':False,'host_inputs':len(u['host_contract_sha256s']),'stages':[v['pytest'].splitlines()[-1] for v in u['versions']]},'input_count':len(inputs),'frontend_reuse':{'base_commit':'40b7971','unchanged_input_count':len(front),'scope':base['frontend_reuse']},'source_distribution_inventory_reuse':source,'service_image_reuse':service,'boundaries':['M1 not exited; N08 not started','session lease covers authenticated HTTP admission and response/stream delivery only; token stays transient and is not placed in Run/graph/persistent state','already delegated remote work and side effects are not claimed cancelled or rolled back','no universal WebSocket/session cancellation, generic Secret/Connector lifecycle, real model/tool/SSH/Kubernetes/ticket/remote CI claim','all original N/O/F goals and gates retained; no push/deploy/release'],'raw_log_sha256':{p.relative_to(HERE).as_posix():sha(p) for p in logs}}
(HERE/'validation.json').write_text(json.dumps(v,indent=2)+'\n')
print(json.dumps({k:v[k] for k in ['status','backend','postgres','image_tests','upgrade','input_count']}))
