from pathlib import Path
import gzip,hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parent/'2026-10-15-octop-n09-socket-sessions'
def read(p): return json.loads((HERE/p).read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(p):
    line=[x for x in (HERE/p).read_text().splitlines() if re.search(r'\d+ passed',x)][-1]
    return {'summary':line,'passed':int(re.search(r'(\d+) passed',line)[1]),'skipped':int(re.search(r'(\d+) skipped',line)[1]) if ' skipped' in line else 0}
for n in ['docx-bounded-related','postgres-bounded','bounded-static','bounded-backend-image-build','bounded-image-runtime','bounded-backend-full','bounded-upgrade','brand-bounded','demo-bounded']:
    d=read(n+'-result.json'); assert d['complete'] and d['returncode']==0,n
inputs=read('inputs-bounded.json')['sha256']
assert all(sha(ROOT/p)==h for p,h in inputs.items())
b=read('backend-driver-bounded.json'); assert b['complete'] and b['returncode']==0 and b['all_inputs_unchanged']
image=read('image-proof-bounded.json'); assert image['backend_image']==b['backend_image'] and image['owned_test_container_removed']
assert all(v['matches'] and sha(ROOT/p)==v['sha256'] for p,v in image['files'].items())
pg=read('postgres-bounded.json'); assert pg['passed'] and pg['returncode']==0 and pg['owned_container_removed']
u=read('upgrade-bounded.json'); assert u['complete'] and u['host_changed'] is False and len(u['versions'])==3 and all(v['returncode']==0 for v in u['versions'])
base=json.loads((BASE/'validation.json').read_text())
front={p:h for p,h in json.loads((BASE/'inputs.json').read_text())['sha256'].items() if p.startswith('frontend/')}
assert all(inputs[p]==h for p,h in front.items())
for k in ['source_distribution_inventory_reuse','service_image_reuse']:
    assert all(sha(ROOT/p)==h for p,h in base[k]['sha256'].items())
logs=sorted((HERE/'logs').glob('*.log'))+[HERE/'postgres-runtime.log',HERE/'postgres-runtime-bounded.log']
v={'base_commit':'4b3cf2c','branch':'codex/octop-integration','status':'independent_docx_baseline_and_atomic_owned_output_accepted_full_Office_M1_pending','backend':stats('logs/bounded-backend-full.log'),'related':stats('logs/docx-bounded-related.log'),'postgres':stats('postgres-runtime-bounded.log')|{'actual_scope':'owned actual PostgreSQL original Tenant/member/thread/Agent facts; Auth User rows in explicitly owned SQLite test identity store; actual DOCX bytes, independent reader and HTTP download; not real external model or deployment','owned_container_removed':True},'image':image,'image_tests':stats('logs/bounded-image-runtime.log'),'upgrade':{'complete':True,'host_changed':False,'host_inputs':len(u['host_contract_sha256s']),'stages':[x['pytest'].splitlines()[-1] for x in u['versions']]},'input_count':len(inputs),'frontend_reuse':{'base_commit':'4b3cf2c','unchanged_input_count':len(front),'scope':base['frontend_reuse']},'source_distribution_inventory_reuse':base['source_distribution_inventory_reuse'],'service_image_reuse':base['service_image_reuse'],'boundaries':['M1 not exited; N08 not started','original file authority verifies current member/account/thread/native selection before and after document operations; no new execution or authorization tables','new binary outputs use held ancestors, full staged write/fsync and original no-replace atomic publication; uncertain post-publication authorization preserves complete result without success/replay','DOCX baseline only; advanced layout/tracked changes/TOC/desktop rendering, XLSX/PPTX/PDF and full Office remain pending; no real external model/ticket/SSH/Kubernetes/delegation/remote CI acceptance','all original N/O/F goals and gates retained; no push/deploy/release'],'raw_log_sha256':{p.relative_to(HERE).as_posix():sha(p) for p in logs}}
previous=read('inputs.json')['sha256']
snapshots={}
for source,name in [('backend/packages/harness/deerflow/tools/builtins/office_docx.py','office_docx-pre-limits.py.gz'),('backend/tests/test_office_docx.py','test_office_docx-pre-limits.py.gz')]:
    assert hashlib.sha256(gzip.decompress((HERE/name).read_bytes())).hexdigest()==previous[source]
    snapshots[name]={'sha256':sha(HERE/name),'uncompressed_sha256':previous[source]}
v['pre_limits_source_snapshots']=snapshots
demo=read('demo.json')
assert all(sha(HERE/p)==d['sha256'] for p,d in demo['files'].items())
v['demo']=demo
(HERE/'validation.json').write_text(json.dumps(v,indent=2)+'\n')
print(json.dumps({k:v[k] for k in ['status','backend','postgres','image_tests','upgrade','input_count']}))
