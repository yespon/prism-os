"""Verify final terminal results and combine independently frozen coverage scopes."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def read(p): return json.loads((HERE/p).read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(name):
    t=(HERE/'logs'/name).read_text()
    m=re.findall(r'(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) warnings)? in ',t)
    assert m,name
    return {'passed':int(m[-1][0]),'skipped':int(m[-1][1] or 0)}
for name in ['static-final','backend-image-build','service-image-build','image-runtime','service-image-http','backend-full','postgres','frontend-full','frontend-build','frontend-format-typecheck','frontend-format-related','upgrade']:
    d=read(name+'-result.json')
    assert d['complete'] and d['returncode']==0,name
backend=read('backend-inputs.json')['sha256']
frontend=read('frontend-inputs.json')['sha256']
assert not set(backend)&set(frontend)
inputs=backend|frontend
assert all(sha(ROOT/p)==h for p,h in inputs.items())
b=read('backend-driver.json')
assert b['complete'] and b['returncode']==0 and b['backend_inputs_unchanged']
f=read('frontend-build-proof.json')
assert f['complete'] and f['returncode']==0 and f['inputs_unchanged'] and f['strict_typecheck_and_generated_routes']
assert f['traces'] and all(not v['missing'] for v in f['traces'].values())
formatting=read('format-only-proof.json')
previous=read('frontend-inputs-before-format.json')['sha256']
changed=[p for p in previous if previous[p]!=frontend[p]]
assert changed==[formatting['path']] and formatting['identical_javascript']
assert previous[changed[0]]==formatting['before_sha256'] and frontend[changed[0]]==formatting['after_sha256']
current=(ROOT/changed[0]).read_bytes()
old=current.replace(b'            key={identity.key}\n',b'            key={identity.key} \n',1)
assert hashlib.sha256(old).hexdigest()==formatting['before_sha256']
assert len(old)==len(current)+1
image=read('image-proof.json')
assert image['backend_image']==b['backend_image'] and image['provisioner_image']==b['provisioner_image']
assert image['owned_test_container_removed'] and all(v['matches'] and sha(ROOT/p)==v['sha256'] for p,v in image['files'].items())
pg=read('postgres.json')
assert pg['passed'] and pg['returncode']==0 and pg['owned_container_removed'] and stats('postgres-runtime.log')['passed']==23
u=read('upgrade.json')
assert u['complete'] and u['host_changed'] is False and len(u['versions'])==3 and all(v['returncode']==0 for v in u['versions'])
base=HERE.parent/'2026-10-15-octop-n09-remote-command-leases'
old=json.loads((base/'inputs.json').read_text())['sha256']
source_paths=[p for p in old if p.startswith(('vendor/octop/','backend/packages/octop-capabilities/')) or p in {'scripts/octop_sync.py','scripts/octop_external.py','scripts/octop_inventory.py','scripts/octop_source_fetch.py','backend/uv.lock','frontend/pnpm-lock.yaml'}]
assert all(sha(ROOT/p)==old[p] for p in source_paths)
for name in ['source','external','inventory']:
    receipt=json.loads((base/(name+'-result.json')).read_text())
    assert receipt['complete'] and receipt['returncode']==0
validation={'base_commit':'f7aac71','branch':'codex/octop-integration','status':'credential_asset_current_authority_and_encrypted_lifecycle_accepted_milestone_one_pending','backend':stats('backend-full.log')|{'returncode':0},'related':stats('credential-runtime.log'),'secret_compatibility':stats('credential-lifecycle.log'),'postgres':stats('postgres-runtime.log')|{'returncode':0,'owned_container_removed':True,'actual_selected_scope':'original asset and Keychain HTTP, consistency and rotation tests'},'images':image,'image_tests':stats('image-runtime.log'),'frontend':{'full_log':'logs/frontend-full.log','full_receipt':'frontend-full-result.json','build_id':f['build_id'],'strict':True,'traces':len(f['traces']),'missing_trace_inputs':0,'input_count':len(frontend),'format_only_reuse':formatting,'post_format_component_tests':6,'post_format_typecheck_returncode':0,'scope':'277 full tests and strict build before one trailing-space cleanup; 503 identical source files, identical emitted JSX JavaScript for the remaining file, current typecheck and six dependent component tests after cleanup'},'upgrade':{'complete':True,'host_changed':False,'host_inputs':len(u['host_contract_sha256s']),'post_run_adjustment':'one trailing frontend space; identical emitted JavaScript; all backend test inputs unchanged','stages':[v['pytest'].splitlines()[-1] for v in u['versions']]},'backend_input_count':len(backend),'frontend_input_count':len(frontend),'input_count':len(inputs),'source_distribution_inventory_reuse':{'base_commit':'f7aac71','unchanged_input_count':len(source_paths),'sha256':{p:old[p] for p in source_paths},'scope':'pinned retained upstream/source policy, external distributions, generated O/F inventory and dependency locks only'},'boundaries':['M1 not exited; N08 not started','real SSH/Kubernetes/model/external-tool/ticket acceptance pending','generic Secret purposes outside original SSH/ticket remain','maintenance key rotation only; no online cross-service key-rotation claim','remaining experts/delegation/independent Office/external runtime and all original exits retained','no push/deploy/release'],'raw_log_sha256':{p.relative_to(HERE).as_posix():sha(p) for p in sorted((HERE/'logs').iterdir()) if p.is_file()}}
(HERE/'inputs.json').write_text(json.dumps({'base_commit':'f7aac71','sha256':inputs},indent=2)+'\n')
(HERE/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
print(json.dumps({k:validation[k] for k in ['status','backend','postgres','image_tests','frontend','upgrade','input_count']}))
