from pathlib import Path
import hashlib,json,subprocess,sys
import yaml
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(HERE.parent/'2026-10-16-octop-office-report-pack'))
import octop_wsl_test_snapshot as snapshot
from live_common import login
snapshot.assert_owned_services();info=json.loads((HERE/'runtime-image.json').read_text());case=json.loads((HERE/'real-chinese-fixed.json').read_text());preview=json.loads((HERE/'native-preview-fixed.json').read_text());p=snapshot.STATE/'compose.yaml';current=p.read_bytes();cfg=yaml.safe_load(current);receipt={'complete':False,'phases':[]}
def compose(args):return subprocess.run(['docker','compose','-p',snapshot.PROJECT,'--env-file',str(snapshot.STATE/'runtime.env'),'-f',str(p),*args],capture_output=True,check=True)
def verify(label):
 owner,other,outsider=[login(role) for role in ['requester','approver','outsider']]
 try:
  for url,digest in [(case['artifact_url'],case['artifact_sha256']),(preview['artifact_url'],preview['png_sha256'])]:
   r=owner.get(url);assert r.status_code==200 and hashlib.sha256(r.content).hexdigest()==digest;assert other.get(url).status_code==404 and outsider.get(url).status_code==404
  graph='/api/langgraph/threads/'+case['thread_id'];history=owner.post(graph+'/history',json={'limit':5});assert history.status_code==200 and case['artifact_url'].split('/artifacts')[1].split('?')[0] in json.dumps(history.json())
  for run in [case['run_id'],preview['run_id']]:assert owner.get(graph+'/runs/'+run).json()['status']=='success'
  receipt['phases'].append({'phase':label,'pdf_and_preview_sha_unchanged':True,'task_status_history_and_acl':True,'new_model_task_submissions':0})
 finally:owner.close();other.close();outsider.close()
try:
 compose(['restart','gateway','langgraph']);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('restart')
 for name in ['gateway','langgraph']:cfg['services'][name]['image']=info['previous'][name]
 p.write_text(yaml.safe_dump(cfg,sort_keys=False));compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('rollback')
 p.write_bytes(current);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('reapply');assert p.read_bytes()==current;receipt['complete']=True
finally:
 if p.read_bytes()!=current:p.write_bytes(current);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph'])
 (HERE/'runtime-cycle.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
