"""Owned PostgreSQL audit of the previous uncoordinated Agent writer seam."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path('/root/.codex/worktrees/octop-integration/prism-os')
OUTPUT = Path('/tmp/prismos-n09k-reference-baseline')
spec = importlib.util.spec_from_file_location('owned_reference_probe', ROOT / 'scripts/octop_skill_postgres.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
original = subprocess.run

def selected_tests(command, *args, **kwargs):
    if isinstance(command, list) and command[1:3] == ['-m', 'pytest']:
        command = [command[0], '-m', 'pytest', 'tests/test_skill_reference_transactions.py', '-k', 'new_reference_writer and create', '-q']
        kwargs['env'] = dict(kwargs['env'], PRISMOS_REFERENCE_BASELINE_PROBE='1')
    return original(command, *args, **kwargs)

probe.subprocess.run = selected_tests
sys.argv = [str(ROOT / 'scripts/octop_skill_postgres.py'), '--output-dir', str(OUTPUT)]
try:
    probe.main()
except RuntimeError:
    result = json.loads((OUTPUT / 'postgres.json').read_text())
    log = (OUTPUT / 'pytest.log').read_text()
    assert result['returncode'] == 1 and result['owned_container_removed']
    assert '2 failed' in log and 'Agent write committed after reference check but before withdrawal commit' in log
    print(json.dumps({'uncoordinated_writer_fault_observed': True, 'failed_cases': 2, 'owned_container_removed': True, 'evidence': str(OUTPUT)}))
else:
    raise AssertionError('Uncoordinated writer unexpectedly passed; audit is not proven')
