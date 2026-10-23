from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
required=['snapshot-static-current','snapshot-final-static','snapshot-tests-current','snapshot-create','snapshot-restore-verify','snapshot-upgrade','snapshot-image','artifact-rollback','jsonl-failure-replay','protected-downgrade-final','final-runtime','brand-staged','public-secrets']
for name in required:
 value=json.loads((HERE/(name+'-result.json')).read_text());assert value['complete'] and value['returncode']==0,name
inputs=json.loads((HERE/'inputs.json').read_text())['sha256']
for p,h in inputs.items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
reuse=json.loads((HERE/'historical-reuse.json').read_text())
for p,h in reuse['unchanged_inputs'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
upgrade=json.loads((HERE/'upgrade.json').read_text());assert upgrade['complete'] and upgrade['host_changed'] is False and all(value['returncode']==0 for value in upgrade['versions'])
for p,h in upgrade['host_contract_sha256s'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
assert json.loads((HERE/'snapshot-image-cleanup.json').read_text())['removed']
restore=json.loads((HERE/'snapshot-restore-verify.json').read_text());assert restore['complete'] and restore['all_file_bytes_and_modes_match'] and restore['owned_clone_databases_removed']
assert all(value['all_row_digests_match'] for value in restore['databases'].values())
assert restore['model_configuration']['opaque_model_credential_restored'] and restore['model_configuration']['restored_database_selected'] and restore['model_configuration']['model_request_sent'] is False
artifact=json.loads((HERE/'artifact-rollback.json').read_text());assert artifact['complete'] and artifact['current_artifact_restored'] and artifact['configuration_bytes_restored'] and artifact['requests_before']==artifact['requests_after']
assert len(artifact['phases'])==3
replay=json.loads((HERE/'jsonl-failure-replay.json').read_text());assert replay['complete'] and replay['original_audit_file_restored'] and replay['canary_restored_off'] and replay['jsonl_event_count_after_concurrent_replay']==1
assert replay['requests_after']==replay['requests_before']+1 and len(replay['actual_process_workers'])==2
protected=json.loads((HERE/'protected-downgrade-final.json').read_text());assert protected['complete'] and protected['owned_clone_removed'] and protected['all_snapshot_rows_unchanged_after_refused_downgrade'] and protected['live_database_downgrade_attempted'] is False
runtime=json.loads((HERE/'final-runtime.json').read_text());assert all(runtime['services'][service]['action']=='off' for service in ['gateway','langgraph'])
assert runtime['receiver']['request_count']==replay['requests_after']
report={'complete_local_snapshot_rollback_block':True,'base_commit':'faa28b6','M1_exited':False,'N08_started':False,'frozen_inputs':len(inputs),'unchanged_inputs_reused':len(reuse['unchanged_inputs']),'application_image':runtime['services']['gateway']['image'],'application_rebuilt':False,'results':{},'source_upgrade':[value['pytest'].splitlines()[-1] for value in upgrade['versions']],'host_contracts':len(upgrade['host_contract_sha256s']),'full_snapshot_clone_rows_match':True,'restored_model_credential_checked_without_request':True,'off_state_artifact_rollback':True,'jsonl_replay_processes':2,'jsonl_replay_calls':8,'actual_jsonl_event_count':1,'actual_ticket_requests':runtime['receiver']['request_count'],'remaining':['Full service deployment and original user flows from restored snapshot','Full other file/tool entry review','Original five-gate final judgment','Remote CI and all original capability targets']}
for name in ['snapshot-tests-current','snapshot-image']:
 text=(HERE/'logs'/(name+'.log')).read_text();report['results'][name]=next(line for line in reversed(text.splitlines()) if re.search(r'\d+ passed',line))
report['raw_sha256']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.rglob('*')) if p.is_file() and p.suffix in {'.log','.jsonl'}}
(HERE/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='raw_sha256'}))
