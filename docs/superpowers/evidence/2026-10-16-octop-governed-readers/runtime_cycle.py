"""Keep accepted user results through restart, previous image and reapplication."""
from pathlib import Path
import hashlib,json,subprocess,sys
import yaml
from live_common import HERE,ROOT,STATE,login,stats
sys.path.insert(0,str(ROOT/'scripts'))
import octop_wsl_test_snapshot as snapshot
snapshot.assert_owned_services();p=STATE/'compose.yaml';current=p.read_bytes();cfg=yaml.safe_load(current)
assert all(cfg['services'][name]['environment']['PRISMOS_GOVERNED_TICKET_ACTION']=='off' for name in ['gateway','langgraph'])
previous=json.loads((HERE/'runtime-image.json').read_text())['previous'];case=json.loads((HERE/'real-binary-task-current.json').read_text());assert case['complete']
other=json.loads((HERE.parent/'2026-10-16-octop-office-chinese-task/real-chinese-fixed.json').read_text());preview=json.loads((HERE.parent/'2026-10-16-octop-office-chinese-task/native-preview-fixed.json').read_text())
receipt={'complete':False,'phases':[],'receiver_before':stats()['request_count']}
def compose(args):return subprocess.run(['docker','compose','-p',snapshot.PROJECT,'--env-file',str(STATE/'runtime.env'),'-f',str(p),*args],capture_output=True,check=True)
def verify(label):
 owner,other_user,outsider=[login(role) for role in ['requester','approver','outsider']]
 try:
  for accepted,digestkey in [(case,'artifact_sha256'),(other,'artifact_sha256'),(preview,'png_sha256')]:
   url=accepted['artifact_url'];r=owner.get(url);assert r.status_code==200 and hashlib.sha256(r.content).hexdigest()==accepted[digestkey];assert other_user.get(url).status_code==404 and outsider.get(url).status_code==404
   graph='/api/langgraph/threads/'+accepted.get('thread_id',other['thread_id']);r=owner.post(graph+'/history',json={'limit':20});assert r.status_code==200 and url.split('/artifacts')[1].split('?')[0] in json.dumps(r.json())
   assert owner.get(graph+'/runs/'+accepted['run_id']).json()['status']=='success'
  receipt['phases'].append({'phase':label,'owned_binary_report_and_previous_chinese_pdf_preview_sha_unchanged':True,'run_status_history_acl':True,'new_model_task_submissions':0})
 finally:owner.close();other_user.close();outsider.close()
try:
 compose(['restart','gateway','langgraph']);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('restart')
 for name in ['gateway','langgraph']:cfg['services'][name]['image']=previous[name]
 p.write_text(yaml.safe_dump(cfg,sort_keys=False));compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('previous_accepted_image')
 p.write_bytes(current);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph']);verify('reapply');assert p.read_bytes()==current
 assert stats()['request_count']==receipt['receiver_before'];receipt.update(complete=True,receiver_after=stats()['request_count'])
finally:
 if p.read_bytes()!=current:p.write_bytes(current);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph'])
 (HERE/'runtime-cycle-current.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Accepted result restart/rollback/reapply:',receipt['complete'])
