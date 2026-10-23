from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[4]
new=['backend/app/integrations/actor_authorization.py','backend/tests/native_auth_test_identity.py','backend/tests/test_runtime_actor_status.py','backend/tests/conftest.py']
changed=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines()
p=ROOT/'.github/workflows/octop-integration.yml'
s=p.read_text()
extra=[x.removeprefix('backend/') for x in new+changed if x.startswith('backend/') and x.endswith('.py') and x.removeprefix('backend/') not in s.split('uv run --locked ruff check',1)[1].split('      - name:',1)[0].split()]
anchor='uv run --locked ruff check'
assert s.count(anchor)==1
s=s.replace(anchor,anchor+' '+' '.join(dict.fromkeys(extra)),1)
p.write_text(s)
p=ROOT/'scripts/octop_upgrade_probe.py'
s=p.read_text().replace('        "tests/test_credential_asset_access.py",','        "tests/test_runtime_actor_status.py",\n        "tests/test_credential_asset_access.py",',1)
anchor='    contract_paths = [\n'
assert s.count(anchor)==1
contracts=list(dict.fromkeys(new+[p for p in changed if p.startswith('backend/')]))
s=s.replace(anchor,anchor+''.join('        '+repr(p)+',\n' for p in contracts if ('"'+p+'"') not in s.split(anchor,1)[1]),1)
p.write_text(s)
subprocess.run([str(ROOT/'backend/.venv/bin/ruff'),'check','--fix',*[p.removeprefix('backend/') for p in new]],cwd=ROOT/'backend',check=True)
