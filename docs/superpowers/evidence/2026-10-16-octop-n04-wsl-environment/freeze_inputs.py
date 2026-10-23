from pathlib import Path
import hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
previous=json.loads((HERE.parent/'2026-10-16-octop-office-docx-images/inputs.json').read_text())['sha256']
new=['scripts/octop_wsl_test_env.py','scripts/octop_wsl_test_probe.py','docker/n04-test/ticket_receiver.py','backend/tests/test_n04_ticket_receiver.py']
def sha(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
current={p:sha(p) for p in sorted(set(previous)|set(new))}
changed={p:{'previous':h,'current':current[p]} for p,h in previous.items() if current[p]!=h}
assert set(changed)=={'.github/workflows/octop-integration.yml','scripts/octop_upgrade_probe.py'}
unchanged={p:h for p,h in previous.items() if p not in changed}
reuse={'base_commit':'645fb42','source':'../2026-10-16-octop-office-docx-images/validation.json','changed_inputs':changed,'added_inputs':new,'unchanged_inputs':unchanged,'scope':['2403 backend passed /18 skipped as unchanged host application evidence only; ten new receiver/ownership tests run separately','151 Office PostgreSQL/image and three-phase source upgrade tests unchanged; new test-environment upgrade probe is additional','frontend source/lock and prior strict production build unchanged; actual .next build mounted read-only into isolated runtime','retained Octop source, external SDK worker, provisioner, wheels and sdist unchanged'],'not_reused_as_new':['real model or governed Action/network golden acceptance','remote CI','target deployment rollback']}
(HERE/'inputs.json').write_text(json.dumps({'base_commit':'645fb42','sha256':current},indent=2)+'\n')
(HERE/'historical-reuse.json').write_text(json.dumps(reuse,indent=2)+'\n')
print(json.dumps({'frozen_inputs':len(current),'unchanged':len(unchanged),'changed':list(changed),'new':new}))
