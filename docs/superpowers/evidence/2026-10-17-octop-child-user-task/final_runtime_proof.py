"""Close only the owned child task runtime and input boundaries."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import httpx
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(HERE.parent / '2026-10-16-octop-governed-readers'))
from octop_wsl_native_env import STATE, NATIVE, process_identity
from live_common import stats

image = json.loads((HERE / 'runtime-image.json').read_text())
cycle = json.loads((HERE / 'runtime-cycle.json').read_text())
assert cycle['complete'] and len(cycle['phases']) == 3
for name in ['gateway', 'langgraph']:
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'prismos-n04-wsl-' + name + '-1'], text=True))[0]
    assert info['Image'] == image['image'] and info['State']['Health']['Status'] == 'healthy'
    assert info['Config']['Labels']['com.docker.compose.project'] == 'prismos-n04-wsl'
    assert not info['HostConfig']['Privileged'] and info['HostConfig']['SecurityOpt'] == ['no-new-privileges:true']
    assert all(m['Destination'] != '/var/run/docker.sock' for m in info['Mounts'])
    assert 'PRISMOS_GOVERNED_TICKET_ACTION=off' in info['Config']['Env']
    assert 'PRISMOS_TRUSTED_GRAPH_CONTEXT=off' in info['Config']['Env']
for name, expected in image['files'].items():
    assert hashlib.sha256((ROOT / 'backend' / name).read_bytes()).hexdigest() == expected
for name, item in json.loads((NATIVE / 'processes.json').read_text()).items():
    assert process_identity(item['pid']) == {k: item[k] for k in ['starttime', 'cmdline_sha256']}, name
with httpx.Client(trust_env=False, timeout=15) as client:
    for port, path in [(18026, '/'), (18036, '/'), (18036, '/health'), (18034, '/ok')]:
        assert client.get(f'http://127.0.0.1:{port}{path}', follow_redirects=True).status_code == 200
assert stats()['request_count'] == 26
# Rebase the native controller's ownership reference only for this exact,
# recorded main-image replacement. No adoption of unknown config/processes.
owned_path = NATIVE / 'ownership.json'
owned = json.loads(owned_path.read_text())
before = Path(image['private_original_compose']).read_bytes()
current = (STATE / 'compose.yaml').read_bytes()
before_sha = hashlib.sha256(before).hexdigest()
current_sha = hashlib.sha256(current).hexdigest()
if owned['main_compose_sha256'] != before_sha:
    earlier = json.loads((HERE / 'final-proof.json').read_text())
    assert earlier['native_ownership_reference_updated_for_recorded_main_image_only'] == {'before': before_sha, 'after': current_sha}
    assert owned['main_compose_sha256'] == current_sha
a, b = yaml.safe_load(before), yaml.safe_load(current)
for name in ['gateway', 'langgraph']:
    assert b['services'][name]['image'] == image['image']
    b['services'][name]['image'] = a['services'][name]['image']
assert a == b
old_sha = before_sha
owned['main_compose_sha256'] = hashlib.sha256(current).hexdigest()
owned_path.write_text(json.dumps(owned, indent=2) + '\n')
assert owned_path.stat().st_mode & 0o777 == 0o600
unchanged = ['frontend', 'backend/uv.lock', 'backend/Dockerfile', 'backend/packages/octop-capabilities', 'vendor/octop']
assert not subprocess.check_output(['git', 'diff', '83ea012', '--name-only', '--', *unchanged], text=True).strip()
receipt = {'complete': True, 'image': image['image'], 'main_and_native_healthy': True, 'main_security_unchanged': True, 'canary_off': True, 'receiver_count': 26, 'native_ownership_reference_updated_for_recorded_main_image_only': {'before': old_sha, 'after': owned['main_compose_sha256']}, 'production_image_sources_match': image['files'], 'unchanged_input_scope_from_83ea012': unchanged, 'M1_exited': False, 'N08_started': False}
(HERE / 'final-proof-current.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('Owned runtimes healthy; exact image source and controlled ownership reference verified')
