"""Owned off-state image rollback/reapply, checking the actual accepted task."""
from pathlib import Path
import json,subprocess,sys
import yaml
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import octop_wsl_test_snapshot as snapshot
snapshot.assert_owned_services()
info=json.loads((HERE/'runtime-image.json').read_text());p=snapshot.STATE/'compose.yaml';current=p.read_bytes();cfg=yaml.safe_load(current);receipt={'complete':False,'phases':[]}

def compose(args):
 return subprocess.run(['docker','compose','-p',snapshot.PROJECT,'--env-file',str(snapshot.STATE/'runtime.env'),'-f',str(p),*args],capture_output=True,check=True)

def verify(label):
 result=subprocess.run([str(ROOT/'backend/.venv/bin/python'),str(ROOT/'scripts/octop_office_task_probe.py'),'--resume',str(HERE/'real-docx-current.json'),'--output',str(HERE/(label+'.json'))],capture_output=True)
 assert result.returncode==0,('Task continuity check failed',label,result.returncode)
 proof=json.loads((HERE/(label+'.json')).read_text());assert proof['complete'];receipt['phases'].append({'phase':label,'artifact_sha256':proof['artifact_sha256'],'history_and_acl':True,'model_reinvoked':False})
try:
 compose(['restart','gateway','langgraph']);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('task-after-restart')
 for name in ['gateway','langgraph']:cfg['services'][name]['image']=info['previous'][name]
 p.write_text(yaml.safe_dump(cfg,sort_keys=False));compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('task-after-image-rollback')
 p.write_bytes(current);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('task-after-image-reapply')
 assert p.read_bytes()==current;receipt['complete']=True
finally:
 if p.read_bytes()!=current:p.write_bytes(current);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph'])
 (HERE/'runtime-cycle.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
