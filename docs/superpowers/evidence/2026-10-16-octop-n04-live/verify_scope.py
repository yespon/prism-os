from pathlib import Path
import ast,copy,hashlib,json,tarfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
proof={}
def stripped(data, names, method=None):
 tree=ast.parse(data)
 tree.body=[n for n in tree.body if getattr(n,'name','') not in names]
 if method:
  for node in tree.body:
   if isinstance(node,ast.ClassDef) and node.name==method[0]:node.body=[n for n in node.body if getattr(n,'name','')!=method[1]]
 return ast.dump(tree)
def compare(archive,path,names,method=None):
 with tarfile.open(HERE/archive) as f:old=f.extractfile(path).read()
 current=(ROOT/path).read_bytes()
 assert stripped(old,names,method)==stripped(current,names,method),path
 proof[path]={'old_sha256':hashlib.sha256(old).hexdigest(),'current_sha256':hashlib.sha256(current).hexdigest(),'changed_functions':names,'changed_method':method,'all_other_AST_unchanged':True}
compare('source-before-settled-read.tar.gz','backend/app/gateway/routers/alerts.py',['resume_governed_incident_ticket','_governed_ticket_status'])
compare('source-before-settled-read.tar.gz','backend/tests/test_incident_diagnosis.py',['test_authenticated_diagnosis_stream_invokes_scoped_governed_tool'])
compare('source-before-policy-guard.tar.gz','backend/app/alerting/governed_ticket.py',['ticket_decision_matches_current_policy'],('TicketActionAdapter','execute'))
compare('source-before-policy-guard.tar.gz','backend/app/alerting/governed_ticket_tool.py',['ticket_adapter','ticket_policy_configuration'])
with tarfile.open(HERE/'source-before-policy-guard.tar.gz') as f:old=ast.parse(f.extractfile('backend/app/alerting/governed_ticket_tool.py').read())
new=ast.parse((ROOT/'backend/app/alerting/governed_ticket_tool.py').read_bytes())
old_adapter=next(n for n in old.body if getattr(n,'name','')=='ticket_adapter')
new_config=next(n for n in new.body if getattr(n,'name','')=='ticket_policy_configuration')
new_adapter=next(n for n in new.body if getattr(n,'name','')=='ticket_adapter')
body=copy.deepcopy(old_adapter.body[:-1]);assert isinstance(body[-1],ast.Assign);body[-1]=ast.Return(value=body[-1].value)
assert ast.dump(ast.Module(body=body,type_ignores=[]))==ast.dump(ast.Module(body=new_config.body,type_ignores=[]))
assert ast.dump(old_adapter.body[-1])==ast.dump(new_adapter.body[-1])
proof['configuration_extraction_preserves_original_constructor_AST']=True
inputs=json.loads((HERE/'inputs.json').read_text())['sha256']
for path,value in inputs.items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==value,path
(HERE/'final-scope.json').write_text(json.dumps(proof,indent=2)+'\n')
print('Final changed runtime functions and current input hashes verified')
