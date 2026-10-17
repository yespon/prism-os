"""Keep actual chart revisions, speaker notes and prior child result through image changes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(HERE.parent / '2026-10-16-octop-governed-readers'))
from live_common import STATE, login, stats
import octop_wsl_test_snapshot as snapshot

snapshot.assert_owned_services()
accepted_path = HERE.parent / '2026-10-17-octop-office-chart-task/real-chart-task-recovered.json'
case = json.loads(accepted_path.read_text())
assert case['complete']
image = json.loads((HERE / 'runtime-image.json').read_text())
child = json.loads((HERE.parent / '2026-10-17-octop-child-user-task/real-child-main-image.json').read_text())
p = STATE / 'compose.yaml'
current = p.read_bytes()
cfg = yaml.safe_load(current)
assert all(cfg['services'][name]['image'] == image['image'] and cfg['services'][name]['environment']['PRISMOS_GOVERNED_TICKET_ACTION'] == 'off' for name in ['gateway', 'langgraph'])
receipt = {'complete': False, 'phases': [], 'receiver_before': stats()['request_count']}


def compose(args):
    subprocess.run(['docker', 'compose', '-p', snapshot.PROJECT, '--env-file', str(STATE / 'runtime.env'), '-f', str(p), *args], check=True, capture_output=True)


def verify(label):
    output = HERE / ('recheck-' + label + '.json')
    assert not output.exists()
    subprocess.run([str(ROOT / 'backend/.venv/bin/python'), str(ROOT / 'scripts/octop_office_chart_task_probe.py'), '--resume', str(accepted_path), '--output', str(output)], cwd=ROOT, check=True, capture_output=True)
    recheck = json.loads(output.read_text())
    assert recheck['complete'] and recheck['new_model_task_submissions'] == 0
    owner, nonowner, outsider = [login(role) for role in ['requester', 'approver', 'outsider']]
    try:
        # Include the pre-note original PPTX, whose missing notes were retained
        # as evidence rather than silently replaced during recovery.
        for artifact in [*case['original_initial_artifacts'].values(), {'artifact_url': child['artifact_url'], 'sha256': child['artifact_sha256']}]:
            response = owner.get(artifact['artifact_url'])
            assert response.status_code == 200 and hashlib.sha256(response.content).hexdigest() == artifact['sha256']
            assert nonowner.get(artifact['artifact_url']).status_code == 404 and outsider.get(artifact['artifact_url']).status_code == 404
        graph = '/api/langgraph/threads/' + child['thread_id']
        assert not owner.get(graph + '/state').json().get('next')
        assert owner.post(graph + '/history', json={'limit': 10}).status_code == 200
    finally:
        for client in [owner, nonowner, outsider]:
            client.close()
    receipt['phases'].append({'phase': label, 'chart_files_and_notes_unchanged': True, 'original_pre_note_files_and_previous_child_docx_unchanged': True, 'history_checkpoint_and_current_acl': True, 'new_model_task_submissions': 0, 'receipt': output.name})


try:
    compose(['restart', 'gateway', 'langgraph'])
    compose(['up', '-d', '--no-build', '--pull', 'never', '--no-deps', '--wait', '--wait-timeout', '240', 'gateway', 'langgraph'])
    verify('restart')
    for name in ['gateway', 'langgraph']:
        cfg['services'][name]['image'] = image['previous'][name]
    p.write_text(yaml.safe_dump(cfg, sort_keys=False))
    compose(['up', '-d', '--no-build', '--pull', 'never', '--no-deps', '--wait', '--wait-timeout', '240', 'gateway', 'langgraph'])
    verify('previous-accepted-image')
    p.write_bytes(current)
    compose(['up', '-d', '--no-build', '--pull', 'never', '--no-deps', '--wait', '--wait-timeout', '240', 'gateway', 'langgraph'])
    verify('reapply')
    assert stats()['request_count'] == receipt['receiver_before']
    receipt.update(complete=True, receiver_after=stats()['request_count'])
finally:
    if p.read_bytes() != current:
        p.write_bytes(current)
        compose(['up', '-d', '--no-build', '--pull', 'never', '--no-deps', '--wait', '--wait-timeout', '240', 'gateway', 'langgraph'])
    (HERE / 'runtime-cycle.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('Original/revised chart and note user results survive restart/rollback/reapply')
