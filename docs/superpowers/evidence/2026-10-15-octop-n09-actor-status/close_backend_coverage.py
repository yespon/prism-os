"""Close full-suite coverage only for an exact isolated test-data correction."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def read(p): return json.loads((HERE/p).read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
full=read('backend-full-result.json')
assert full['complete'] and full['returncode']==1,full
rerun=read('actor-custom-identities-result.json')
assert rerun['complete'] and rerun['returncode']==0
old=read('backend-inputs-final.json')['sha256']
current=read('backend-inputs-current.json')['sha256']
assert all(sha(ROOT/p)==h for p,h in current.items())
assert [p for p in old if old[p]!=current[p]]==['backend/tests/test_custom_agent.py']
proof=read('fixture-only-proof.json')
assert not proof['test_module_import_consumers']
names=read('full-collection.json')
log=(HERE/'logs/backend-full.log').read_text()
failed=re.findall(r'^FAILED (\S+)',log,re.M)
assert len(failed)==6 and all(n.startswith('tests/test_custom_agent.py::') for n in failed),failed
letters=''.join(line.split('[')[0].replace(' ','') for line in log.splitlines() if re.fullmatch(r'[.FsExX\s]+(?:\[\s*\d+%\])?\s*',line))
assert len(letters)==len(names),(len(letters),len(names))
assert {n for n,c in zip(names,letters,strict=True) if c=='F'}==set(failed)
assert set(letters)<={'.','F','s'},set(letters)
custom=[n for n in names if n.startswith('tests/test_custom_agent.py::')]
line=[s for s in (HERE/'logs/actor-custom-identities.log').read_text().splitlines() if re.search(r'\d+ passed',s)][-1]
assert int(re.search(r'(\d+) passed',line)[1])==len(custom)
status={n:('passed' if n in custom else {'s':'skipped','.':'passed'}[c]) for n,c in zip(names,letters,strict=True)}
receipt={'complete':True,'method':'full original run plus current exact changed-fixture module; not a new single full green run','full_returncode':1,'initial_failures':failed,'fixture_rerun_summary':line,'fixture_rerun_returncode':0,'unchanged_input_count':len(old)-1,'changed_scope':proof,'passed':list(status.values()).count('passed'),'skipped':list(status.values()).count('skipped'),'unresolved_failures':0,'test_node_status':status,'raw_full_log_sha256':sha(HERE/'logs/backend-full.log'),'raw_current_fixture_log_sha256':sha(HERE/'logs/actor-custom-identities.log')}
(HERE/'backend-coverage.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ['method','passed','skipped','unresolved_failures','fixture_rerun_summary']}))
