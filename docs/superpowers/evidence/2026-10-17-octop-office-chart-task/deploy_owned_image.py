import hashlib,json,subprocess,sys
from pathlib import Path
import yaml
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import octop_wsl_test_snapshot as snapshot
snapshot.assert_owned_services()
def compose(args):
 return subprocess.run(["docker","compose","-p",snapshot.PROJECT,"--env-file",str(snapshot.STATE/"runtime.env"),"-f",str(snapshot.STATE/"compose.yaml"),*args],check=True,capture_output=True).stdout
image=subprocess.check_output(['docker','image','inspect','prismos-chart-notes:test','--format','{{.Id}}'],text=True).strip()
p=snapshot.STATE/'compose.yaml';original=p.read_bytes();backup=snapshot.STATE/'compose-before-chart-notes.yaml';assert not backup.exists();snapshot.private_write(backup,original)
config=yaml.safe_load(original);previous={}
for name in ['gateway','langgraph']:
 service=config['services'][name];previous[name]=service['image'];assert service['environment']['PRISMOS_GOVERNED_TICKET_ACTION']=='off';service['image']=image
p.write_bytes(yaml.safe_dump(config,sort_keys=False).encode())
try:
 compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph'])
except BaseException:
 p.write_bytes(original);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);raise
files={}
for name in ['app/alerting/governed_native_reads.py','app/alerting/governed_read_tool.py','app/integrations/file_access.py','app/runtime_adapters.py','packages/harness/deerflow/runtime.py','packages/harness/deerflow/agents/lead_agent/agent.py','tests/test_office_pptx_notes.py','packages/harness/deerflow/tools/builtins/office_pptx.py','tests/test_governed_native_reads.py','packages/harness/deerflow/subagents/executor.py','packages/harness/deerflow/tools/builtins/task_tool.py']:
 expected=hashlib.sha256((ROOT/'backend'/name).read_bytes()).hexdigest();actual=subprocess.check_output(['docker','exec','prismos-n04-wsl-gateway-1','sha256sum','/app/backend/'+name],text=True).split()[0];assert actual==expected;files[name]=expected
(HERE/'runtime-image.json').write_text(json.dumps({'image':image,'previous':previous,'files':files,'action':'off','private_original_compose':str(backup)},indent=2)+'\n')
print('Owned Gateway and LangGraph healthy on current chart notes image; deployment bytes match')
