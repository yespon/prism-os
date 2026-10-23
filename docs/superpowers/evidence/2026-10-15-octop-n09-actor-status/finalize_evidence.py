"""Derive acceptance exclusively from final, complete receipts and immutable inputs."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parent/'2026-10-15-octop-n09-credential-assets'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name): return json.loads((HERE/name).read_text())
def stats(name):
    s=(HERE/name).read_text()
    lines=[line for line in s.splitlines() if re.search(r'\d+ passed',line)]
    assert lines,name
    line=lines[-1]
    return {'summary':line,'passed':int(re.search(r'(\d+) passed',line)[1]),'skipped':int(re.search(r'(\d+) skipped',line)[1]) if ' skipped' in line else 0}
for name in ['actor-default-fixed','actor-proxy-current','actor-governed-action','actor-thread-fixtures','static-current','postgres','backend-image-build-final','image-compatible-runtime','image-namespace-confirmed','actor-custom-identities','upgrade','upgrade-fixture','brand-staged']:
    result=read(name+'-result.json')
    assert result['complete'] and result['returncode']==0,name
backend=read('backend-inputs-current.json')['sha256']
frontend=read('frontend-inputs.json')['sha256']
assert all(sha(ROOT/p)==h for p,h in (backend|frontend).items())
previous=read('backend-inputs-final.json')['sha256']
changed=[p for p in backend if backend[p]!=previous[p]]
assert changed==['backend/tests/test_custom_agent.py'],changed
image=read('image-proof-final.json')
assert image['owned_test_container_removed'] and all(v['matches'] and sha(ROOT/p)==v['sha256'] for p,v in image['files'].items())
coverage=read('backend-coverage.json')
assert coverage['complete'] and coverage['unresolved_failures']==0
assert read('image-compatible-scope.json')['image']==image['backend_image']
assert read('image-namespace-limit.json')['image']==image['backend_image']
pg=read('postgres.json')
assert pg['passed'] and pg['owned_container_removed'] and pg['returncode']==0
u=read('upgrade.json')
assert u['complete'] and u['host_changed'] is False and len(u['versions'])==3 and all(v['returncode']==0 for v in u['versions'])
uf=read('upgrade-fixture.json')
assert uf['complete'] and uf['host_changed'] is False and len(uf['versions'])==3 and all(v['returncode']==0 for v in uf['versions'])
base_validation=json.loads((BASE/'validation.json').read_text())
assert frontend==json.loads((BASE/'frontend-inputs.json').read_text())['sha256']
reused=base_validation['source_distribution_inventory_reuse']
assert all(sha(ROOT/p)==h for p,h in reused['sha256'].items())
service_paths=['docker/provisioner/app.py','docker/provisioner/scoped_commands.py','docker/provisioner/requirements.lock','docker/provisioner/Dockerfile']
assert all(sha(ROOT/p)==json.loads((BASE/'backend-inputs.json').read_text())['sha256'][p] for p in service_paths)
logs=sorted((HERE/'logs').glob('*.log'))+[HERE/'postgres-runtime.log']
validation={
 'base_commit':'c496fbe','branch':'codex/octop-integration',
 'status':'original_account_current_authority_accepted_with_explicit_container_scope_M1_pending',
 'backend':{k:coverage[k] for k in ['passed','skipped','method','full_returncode','unresolved_failures']},
 'postgres':stats('postgres-runtime.log')|{'owned_container_removed':True,'scope':'20 account/runtime tests plus 23 HTTP/file tests; actor_databases uses actual Config and original User facts on the same owned PostgreSQL; shared HTTP/command fixtures use PostgreSQL Config with their explicit isolated SQLite Auth store'},
 'governed_action':stats('logs/actor-governed-action.log')|{'scope':'original Policy/Action/Audit, transport observer zero calls after authority withdrawal; not a real external ticket call'},
 'image':image,'image_tests':stats('logs/image-compatible-runtime.log')|{'explicit_deselection':'three actual Local command tests require namespaces unavailable under default Docker; passed on host/PostgreSQL; unfiltered failed attempts retained'},
 'upgrade':{'complete':True,'host_changed':False,'host_inputs':len(u['host_contract_sha256s']),'stages':[v['pytest'].splitlines()[-1] for v in u['versions']],'post_probe_fixture_correction':read('fixture-only-proof.json'),'current_fixture_stages':[v['pytest'].splitlines()[-1] for v in uf['versions']]},
 'input_count':len(backend)+len(frontend),'backend_inputs':len(backend),
 'frontend_reuse':{'base_commit':'c496fbe','byte_identical_input_count':len(frontend),'scope':base_validation['frontend']},
 'source_distribution_inventory_reuse':reused,
 'service_image_reuse':{'base_commit':'c496fbe','image':base_validation['images']['provisioner_image'],'sha256':{p:sha(ROOT/p) for p in service_paths},'scope':'same service implementation and pinned dependencies; previous actual service HTTP admission evidence only'},
 'earlier_failures':{'full_suite':'six cross-user CRUD fixture failures retained; exact changed fixture module rerun and node-level current coverage closure, no single full green run claim','first_reproduction':'4 failed / 1 passed before production fix','stalled_related':'verified owned pytest terminated, -15; no pass claim','related_before_thread_fixture':'7 failed / 719 passed; all missing thread-binding facts; corrected eight affected selections plus final full suite','unfiltered_images':'three Local namespace startup tests fail under default container restrictions; no production isolation bypass','probe_assertion':'first namespace probe expected a different error phrase; actual command failed closed; corrected receipt retains initial failure'},
 'boundaries':['M1 not exited; N08 not started','account suspension/deletion/password renewal covered; no universal browser logout or session lifetime cancellation claim','no real model/SSH/Kubernetes/external tool/ticket acceptance','default Docker nested Local namespace positive execution remains unavailable; no privileged workaround','all original N/O/F scope and gates retained; no push/deploy/release'],
 'raw_log_sha256':{p.relative_to(HERE).as_posix():sha(p) for p in logs}
}
(HERE/'inputs.json').write_text(json.dumps({'base_commit':'c496fbe','sha256':backend|frontend},indent=2)+'\n')
(HERE/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
print(json.dumps({k:validation[k] for k in ['status','backend','postgres','image_tests','upgrade','input_count']},ensure_ascii=False))
