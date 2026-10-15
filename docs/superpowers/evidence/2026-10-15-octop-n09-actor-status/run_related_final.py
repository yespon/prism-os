from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
patterns=['test_skill*.py','test_agent*.py','test_octop*.py','test_file_access*.py','test_terminal*.py','test_diagnosis*.py','test_langgraph*.py']
names={p.name for pattern in patterns for p in (ROOT/'backend/tests').glob(pattern)}
names.update(['test_runtime_actor_status.py','test_runtime_source_revocation.py','test_runtime_adapters.py','test_incident_diagnosis.py','test_credential_asset_access.py','test_legacy_default_scope.py'])
subprocess.run([sys.executable,str(HERE/'run_validation.py'),'--cwd','backend','actor-related-final','--','.venv/bin/python','-m','pytest',*['tests/'+p for p in sorted(names)],'-q','-o','faulthandler_timeout=90'],cwd=ROOT,check=True)
