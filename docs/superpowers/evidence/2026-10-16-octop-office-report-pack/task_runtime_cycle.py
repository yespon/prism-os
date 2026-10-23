from pathlib import Path
import json,subprocess,sys
import yaml
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import octop_wsl_test_snapshot as snapshot
snapshot.assert_owned_services();info=json.loads((HERE/'runtime-image.json').read_text());p=snapshot.STATE/'compose.yaml';current=p.read_bytes();cfg=yaml.safe_load(current);receipt={'complete':False,'phases':[]}
def compose(args):return subprocess.run(['docker','compose','-p',snapshot.PROJECT,'--env-file',str(snapshot.STATE/'runtime.env'),'-f',str(p),*args],capture_output=True,check=True)
def verify(label):
 r=subprocess.run([str(ROOT/'backend/.venv/bin/python'),str(ROOT/'scripts/octop_office_report_probe.py'),'--source',str(HERE.parent/'2026-10-16-octop-office-expert-task/real-expert-task.json'),'--resume',str(HERE/'report-task-acceptance.json'),'--output',str(HERE/(label+'.json'))],capture_output=True);assert r.returncode==0,(label,r.returncode)
 proof=json.loads((HERE/(label+'.json')).read_text());assert proof['complete'] and proof['new_agent_task_submissions']==0;receipt['phases'].append({'phase':label,'artifacts':{k:v['sha256'] for k,v in proof['artifacts'].items()},'task_status':proof['run_status'],'model_task_resubmitted':False})
try:
 compose(['restart','gateway','langgraph']);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('pack-after-restart')
 for name in ['gateway','langgraph']:cfg['services'][name]['image']=info['previous'][name]
 p.write_text(yaml.safe_dump(cfg,sort_keys=False));compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('pack-after-rollback')
 p.write_bytes(current);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('pack-after-reapply');assert p.read_bytes()==current;receipt['complete']=True
finally:
 if p.read_bytes()!=current:p.write_bytes(current);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph'])
 (HERE/'runtime-cycle.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
