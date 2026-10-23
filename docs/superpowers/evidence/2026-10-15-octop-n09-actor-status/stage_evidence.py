from pathlib import Path
import json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='codex/octop-integration'
assert subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip()=='c496fbe'
paths=['.github/workflows/octop-integration.yml','scripts/octop_upgrade_probe.py','backend/app/integrations/actor_authorization.py','backend/app/integrations/file_access.py','backend/app/runtime_adapters.py','backend/app/alerting/diagnosis_authorization.py','backend/tests/native_auth_test_identity.py','backend/tests/test_runtime_actor_status.py','backend/tests/conftest.py','backend/tests/resource_test_identity.py','backend/tests/test_agent_skill_references.py','backend/tests/test_credential_asset_access.py','backend/tests/test_custom_agent.py','backend/tests/test_file_access_http.py','backend/tests/test_incident_diagnosis.py','backend/tests/test_langgraph_proxy.py','backend/tests/test_octop_integration.py','backend/tests/test_octop_resource_installations.py','backend/tests/test_runtime_source_revocation.py','backend/tests/test_skill_import_recovery.py','backend/tests/test_skills_scope_router.py','backend/tests/test_diagnosis_authorization.py',HERE.relative_to(ROOT).as_posix()]
for p in HERE.glob('*.py'): p.write_text(p.read_text().rstrip()+'\n')
subprocess.run(['git','add',*paths],cwd=ROOT,check=True)
if not (HERE/'brand-staged-result.json').exists():
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),'brand-staged','--',sys.executable,'scripts/check_brand_identity.py'],cwd=ROOT,check=True)
subprocess.run(['git','diff','--cached','--check','--','.',':(exclude)**/*.log'],cwd=ROOT,check=True)
print('Current account functional block staged; no commit until final coverage and upgrade receipts complete')
