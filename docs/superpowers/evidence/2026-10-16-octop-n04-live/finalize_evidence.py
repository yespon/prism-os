from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def result(name):
 value=json.loads((HERE/(name+'-result.json')).read_text());assert value['complete'] and value['returncode']==0,name
 return value
required=['model-connectivity','provision-fixture','routing-tests','worker-bootstrap-current','worker-postgres','native-resume-tests','settled-resume-tests','policy-current-tests','policy-static-final','runtime-receiver-image-build','receiver-v2-static','receiver-v2-current-tests','receiver-v2-image','receiver-v2-upgrade','durable-facts','backend-full','image-runtime','upgrade','static-final','policy-change-counter-v2','failure-counter-v2','approval-counter-v2','allow-counter-v2','timeout-counter-v2','receiver-v2-live','final-runtime-closed','final-backup-closed','brand-staged','public-secrets-closed','brand-final','public-secrets-final']
for name in required:result(name)
inputs=json.loads((HERE/'inputs.json').read_text())['sha256']
for p,h in inputs.items():assert sha(ROOT/p)==h,p
subprocess.run([sys.executable,str(HERE/'verify_scope.py')],check=True,cwd=ROOT)
old=json.loads((HERE/'upgrade.json').read_text());new=json.loads((HERE/'receiver-v2-upgrade.json').read_text())
for upgrade in [old,new]:assert upgrade['complete'] and upgrade['host_changed'] is False and all(v['returncode']==0 for v in upgrade['versions'])
changed={p for p,h in old['host_contract_sha256s'].items() if sha(ROOT/p)!=h}
assert changed=={'docker/n04-test/ticket_receiver.py','backend/tests/test_n04_ticket_receiver.py','backend/tests/test_incident_diagnosis.py'},changed
whitespace=json.loads((HERE/'final-whitespace.json').read_text())
assert sha(ROOT/whitespace['file'])==whitespace['current_sha256']
for p,h in new['host_contract_sha256s'].items():
 assert sha(ROOT/p)==h or (p==whitespace['file'] and h==whitespace['old_sha256']),p
for name in ['image-cleanup.json','receiver-v2-image-cleanup.json']:assert json.loads((HERE/name).read_text())['removed']
image=json.loads((HERE/'runtime-image.json').read_text());assert all(v['matches'] for v in image['files'].values())
for p,v in image['files'].items():
 assert sha(ROOT/'backend'/p)==v['sha256'] or ('backend/'+p==whitespace['file'] and v['sha256']==whitespace['old_sha256']),p
runtime=json.loads((HERE/'final-runtime.json').read_text());assert runtime['migration_head']=='n8h9i0j1k2l3'
assert all(runtime['services'][name]['action']=='off' for name in ['gateway','langgraph'])
assert runtime['services']['gateway']['image']==image['image']
assert runtime['receiver']['counter_version']==2
cases=json.loads((HERE/'approval-counter-v2.json').read_text());assert cases['complete'] and all(c['complete'] for c in cases['cases'])
assert {c['scenario'] for c in cases['cases']}=={'approve','reject','revoke_agent','withdraw_secret','rotate_secret','restart'}
for name in ['allow-counter-v2.json','timeout-counter-v2.json','failure-counter-v2.json','policy-change-counter-v2.json','receiver-v2-live.json']:assert json.loads((HERE/name).read_text())['complete'],name
activations=[json.loads(line) for line in (HERE/'policy-activations.jsonl').read_text().splitlines()]
assert activations and all(a['services']['gateway']==a['services']['langgraph'] for a in activations)
report={'complete_local_runtime_governance_block':True,'M1_exited':False,'N08_started':False,'remote_ci_executed':False,'base_commit':'b474c64','frozen_inputs':len(inputs),'image':image['image'],'host_lock_sha256':sha(ROOT/'backend/uv.lock'),'final_test_whitespace_only':whitespace,'whole_backend_on_final_source':False,'whole_backend_snapshot':'inputs-before-settled-read.json','results':{},'source_upgrade':{'original_current_application':[v['pytest'].splitlines()[-1] for v in old['versions']],'final_receiver_only':[v['pytest'].splitlines()[-1] for v in new['versions']],'host_contracts':len(new['host_contract_sha256s'])},'receiver_v2_historical_boundary':runtime['receiver']['historical_v1_receipts'],'remaining':['actual policy/audit write faults','wall-clock approval expiry','legacy delivery failure/recovery','actual read-only file PEP/full entry review','complete target configuration/artifact rollback and original five-gate judgment']}
for name in ['backend-full','policy-current-tests','image-runtime','receiver-v2-current-tests','receiver-v2-image']:
 text=(HERE/'logs'/(name+'.log')).read_text()
 report['results'][name]=next(line for line in reversed(text.splitlines()) if re.search(r'\d+ passed',line))
report['raw_sha256']={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and (p.suffix=='.log' or p.name.endswith('.tar.gz') or p.suffix=='.jsonl')}
(HERE/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='raw_sha256'}))
