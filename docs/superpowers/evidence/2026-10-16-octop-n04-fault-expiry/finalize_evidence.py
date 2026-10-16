"""Close only completed owned deployment gates; never infer M1 exit."""
from pathlib import Path
import hashlib,json,subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
required=['wall-clock-expiry','database-write-faults','final-runtime','final-backup','brand-staged','public-secrets']
for name in required:
 value=json.loads((HERE/(name+'-result.json')).read_text());assert value['complete'] and value['returncode']==0,name
reuse=json.loads((HERE/'historical-reuse.json').read_text())
for p,h in reuse['unchanged_inputs'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
expiry=json.loads((HERE/'wall-clock-expiry.json').read_text());faults=json.loads((HERE/'database-write-faults.json').read_text())
assert expiry['complete'] and expiry['canary_restored_off'] and expiry['final_approval_status']=='expired'
assert expiry['requests_before']==expiry['requests_after']
assert faults['complete'] and faults['canary_restored_off'] and faults['triggers_and_schema_removed']
assert {case['scenario'] for case in faults['cases']}=={'policy','audit_policy','audit_result','legacy_action'}
for case in faults['cases']:assert case['complete'] and case['actual_trigger_hits']>0
runtime=json.loads((HERE/'final-runtime.json').read_text())
assert all(runtime['services'][name]['action']=='off' for name in ['gateway','langgraph'])
report={'complete_local_fault_expiry_block':True,'base_commit':'1c11dbb','M1_exited':False,'N08_started':False,'production_inputs_unchanged':len(reuse['unchanged_inputs']),'actual_wall_clock_expiry':True,'actual_database_fault_cases':[case['scenario'] for case in faults['cases']],'fault_triggers_removed':True,'application_image':runtime['services']['gateway']['image'],'receiver_counter_version':runtime['receiver']['counter_version'],'requests_after':runtime['receiver']['request_count'],'acceptance_scope':'Owned WSL deployment, real configured model/native HTTP/PG and real HTTPS test receiver; enterprise integration not implied. Existing application/image/upgrade gates reused by exact input SHA.','remaining':['actual read-only file PEP and other entry review','complete target configuration/artifact rollback','original five-gate final judgment','remote CI and full retained capability scope'],'raw_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.rglob('*')) if p.is_file() and p.suffix in {'.log','.jsonl'}}}
(HERE/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='raw_sha256'}))
