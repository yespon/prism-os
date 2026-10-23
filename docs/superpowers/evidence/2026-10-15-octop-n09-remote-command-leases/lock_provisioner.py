from pathlib import Path
import subprocess
r=Path('/root/.codex/worktrees/octop-integration/prism-os')
image='sha256:5ed1507c9168ed6d25b69ef2a7a3178cc1c122902a6fb47c88c5b4bbdea879cd'
result=subprocess.run(['docker','run','--rm','--network','none',image,'python','-m','pip','freeze'],check=True,capture_output=True,text=True)
(r/'docker/provisioner/requirements.lock').write_text('# Resolved from the recorded provisioner image; explicit dependency upgrades require rebuild and protocol regression.\n'+result.stdout)
p=r/'docker/provisioner/Dockerfile'
s=p.read_text()
a=s.index('# Install Python dependencies')
b=s.index('WORKDIR /app',a)
s=s[:a]+'# Install the recorded complete Python dependency set.\nCOPY requirements.lock /tmp/requirements.lock\nRUN pip install --no-cache-dir -r /tmp/requirements.lock\n\n'+s[b:]
p.write_text(s)
p=r/'docs/superpowers/evidence/2026-10-15-octop-n09-remote-command-leases/freeze_inputs.py'
s=p.read_text().replace("paths.update([","paths.update(['docker/provisioner/requirements.lock',",1)
p.write_text(s)
p=r/'scripts/octop_upgrade_probe.py'
s=p.read_text().replace('    contract_paths = [','    contract_paths = [\n        "docker/provisioner/requirements.lock",',1)
p.write_text(s)
print('Pinned full provisioner dependency set:',len(result.stdout.splitlines()))
