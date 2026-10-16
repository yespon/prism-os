from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
required=['storage-tests','storage-deployment','storage-static-current','storage-image-current','skill-lock-reproduction','diagnosis-static','diagnosis-targeted','diagnosis-postgres','runtime-image-build','live-skill-read-current','read-audit-faults','upgrade-current','image-current','final-runtime','final-backup','storage-mounts','brand-staged','public-secrets']
for name in required:
 r=json.loads((HERE/(name+'-result.json')).read_text());assert r['complete'] and r['returncode']==0,name
inputs=json.loads((HERE/'inputs.json').read_text())['sha256']
for f,h in inputs.items():assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h,f
reuse=json.loads((HERE/'historical-reuse.json').read_text())
for f,h in reuse['unchanged_inputs'].items():assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h,f
upgrade=json.loads((HERE/'upgrade-current.json').read_text());assert upgrade['complete'] and upgrade['host_changed'] is False and all(v['returncode']==0 for v in upgrade['versions'])
for f,h in upgrade['host_contract_sha256s'].items():assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h,f
read=json.loads((HERE/'live-skill-read-current.json').read_text());assert read['complete'] and read['canary_restored_off'] and read['actual_model_tool_read_success'] and read['disabled_resource_blocks_new_diagnosis_http']==403 and read['requests_before']==read['requests_after']
fault=json.loads((HERE/'read-audit-faults.json').read_text());assert fault['complete'] and fault['triggers_and_schema_removed'] and fault['canary_restored_off'] and all(case['complete'] and case['actual_trigger_hits']>0 for case in fault['cases'])
assert json.loads((HERE/'runtime-image-cleanup.json').read_text())['removed']
assert json.loads((HERE/'image-current-cleanup.json').read_text())['removed']
pg=json.loads((HERE/'diagnosis-postgres.json').read_text());assert pg['passed'] and pg['owned_container_removed']
runtime=json.loads((HERE/'final-runtime.json').read_text());assert all(runtime['services'][name]['action']=='off' for name in ['gateway','langgraph'])
report={'complete_local_skill_runtime_block':True,'M1_exited':False,'N08_started':False,'base_commit':'36941c7','frozen_inputs':len(inputs),'reused_unchanged_inputs':len(reuse['unchanged_inputs']),'image':runtime['services']['gateway']['image'],'whole_backend_rerun':False,'results':{},'current_source_upgrade':[v['pytest'].splitlines()[-1] for v in upgrade['versions']],'host_contracts':len(upgrade['host_contract_sha256s']),'real_model_read':True,'readonly_audit_fault_events':[case['fault_event'] for case in fault['cases']],'receiver_counter':runtime['receiver']['request_count'],'remaining':['full other file/tool entry review','complete target configuration/artifact rollback','original five-gate final judgment','remote CI and all original capability targets']}
for name in ['storage-tests','storage-image-current','diagnosis-targeted','diagnosis-postgres-pytest','image-current']:
 text=(HERE/'logs'/(name+'.log')).read_text();report['results'][name]=next(line for line in reversed(text.splitlines()) if re.search(r'\d+ passed',line))
report['raw_sha256']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.rglob('*')) if p.is_file() and (p.suffix in {'.log','.jsonl'} or p.name.endswith('.tar.gz'))}
(HERE/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='raw_sha256'}))
