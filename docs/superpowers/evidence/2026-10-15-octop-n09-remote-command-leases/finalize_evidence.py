"""Reconcile final receipts, frozen inputs and strictly scoped historical reuse."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def read(p): return json.loads((HERE/p).read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(name):
    text=(HERE/'logs'/name).read_text()
    m=re.findall(r'(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) warnings)? in ',text)
    assert m,name
    return {'passed':int(m[-1][0]),'skipped':int(m[-1][1] or 0)}
required=['static-final','backend-image-build-final','provisioner-image-build-final','image-protocol-final','service-image-http-final','backend-full-final','upgrade-final','source','external','inventory']
for name in required:
    value=read(name+'-result.json')
    assert value['complete'] and value['returncode']==0,name
inputs=read('inputs.json')
assert all(sha(ROOT/p)==h for p,h in inputs['sha256'].items())
assert all(sha(ROOT/p)==h for p,h in inputs['frontend_reuse']['sha256'].items())
driver=read('acceptance-driver-final.json')
assert driver['complete'] and driver['returncodes']==[0,0] and driver['source_inputs_unchanged']
proof=read('image-proof-final.json')
assert proof['backend_image']==driver['backend_image'] and proof['provisioner_image']==driver['provisioner_image']
assert all(v['matches'] and sha(ROOT/p)==v['sha256'] for p,v in proof['files'].items())
assert proof['owned_test_container_removed']
u=read('upgrade-final.json')
assert u['complete'] and u['host_changed'] is False and all(v['returncode']==0 for v in u['versions']) and len(u['versions'])==3
base=json.loads((HERE.parent/'2026-10-15-octop-n09-auxiliary-resources/inputs.json').read_text())
# Reuse database evidence only for unchanged native resource/import code and tests,
# not for this new remote protocol, node execution, or the complete current backend.
pg_scope=['backend/app/integrations/skill_imports.py','backend/app/gateway/resource_authorization.py','backend/app/gateway/routers/skills.py','backend/app/gateway/routers/agent_catalog.py','backend/app/integrations/agent_skill_references.py','backend/app/integrations/skill_reference_transactions.py','backend/tests/test_resource_catalog_access.py','backend/tests/test_skill_import_recovery.py','backend/tests/test_skill_manual_creation.py','backend/tests/test_skill_mutation_boundaries.py','backend/tests/test_skill_resource_identity.py','backend/tests/resource_test_identity.py','backend/packages/harness/deerflow/database/models.py','backend/uv.lock']
assert all(sha(ROOT/p)==base['sha256'][p] for p in pg_scope)
validation={'base_commit':'c20fdd9','branch':'codex/octop-integration','status':'remote_command_protocol_integrated_cluster_pending_milestone_one_pending','backend':stats('backend-full-final.log')|{'returncode':0},'related':stats('protocol-termination.log'),'image_protocol':stats('image-protocol-final.log'),'images':proof,'input_count':len(inputs['sha256']),'frontend_reuse':inputs['frontend_reuse'],'postgres_reuse':{'source':'../2026-10-15-octop-n09-auxiliary-resources/validation.json','original_passed':120,'unchanged_inputs':{p:sha(ROOT/p) for p in pg_scope},'scope':'original native resource import/authority database behavior only; no claim of new remote PostgreSQL or cluster execution'},'upgrade':{'complete':True,'host_changed':False,'host_inputs':len(u['host_contract_sha256s']),'stages':[v['pytest'].splitlines()[-1] for v in u['versions']]},'real_cluster':{'executed':False,'acceptance_pending':True,'ready_probe':'scripts/octop_remote_smoke.py'},'boundaries':['M1 not exited; N08 not started','real Kubernetes/node mapping/cancellation must be exercised in configured environment','remote Browser/interactive sandbox and Apple runtime pending','N04 actual model/tool/ticket environment and N07 remote CI pending','generic Secret purposes, complete expert behavior/delegation, independent Office and external runtime remain','all N/O/F and original PrismOS exits retained; no push/deploy/release'],'raw_log_sha256':{p.relative_to(HERE).as_posix():sha(p) for p in sorted((HERE/'logs').iterdir()) if p.is_file()}}
(HERE/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
print(json.dumps({k:validation[k] for k in ['status','backend','related','image_protocol','upgrade','input_count']}))
