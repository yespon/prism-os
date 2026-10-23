"""Natural follow-up uses the existing PDF; does not regenerate it."""
from pathlib import Path
import argparse,hashlib,json,sys
import httpx
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'scripts'))
from octop_office_report_probe import STATE,BASE
parser=argparse.ArgumentParser();parser.add_argument('--case',default='real-chinese-task.json');parser.add_argument('--result',default='native-preview.json');parser.add_argument('--png',default='chinese-report-preview.png');args=parser.parse_args();assert not (HERE/args.result).exists() and not (HERE/args.png).exists();case=json.loads((HERE/args.case).read_text());assert case['complete'];fixture=json.loads((STATE/'live-fixture.json').read_text());clients=[]
def login(role):
 user=fixture['users'][role];c=httpx.Client(base_url=BASE,headers={'X-Tenant-Id':fixture['other_tenant_id'] if role=='outsider' else fixture['tenant_id']},trust_env=False,timeout=240);r=c.post('/api/auth/login',json={'email':user['email'],'password':user['password']});assert r.status_code==200;c.headers['Authorization']='Bearer '+r.json()['session']['token'];clients.append(c);return c
result={'complete':False}
try:
 owner,outsider,nonowner=[login(role) for role in ['requester','outsider','approver']];graph='/api/langgraph/threads/'+case['thread_id'];source=case['artifact_url'].split('/artifacts')[1].split('?')[0];output=source.removesuffix('.pdf')+'-preview.png';task='请将已完成的中文 PDF '+source+' 首页渲染为清晰的 PNG 预览，保存为 '+output+' 并提供预览结果。直接使用现有 PDF，不要重新生成简报。';payload={'assistant_id':'lead_agent','input':{'messages':[{'type':'human','content':task}]},'context':{'agent_name':case['agent_name'],'subagent_enabled':False,'thinking_enabled':False,'is_plan_mode':False},'config':{'recursion_limit':1000},'stream_mode':['values','updates']}
 with owner.stream('POST',graph+'/runs/stream',json=payload) as r:assert r.status_code==200;transcript='\n'.join(r.iter_lines())
 private=Path(case['private_diagnostics'])/'preview-stream.txt';private.write_text(transcript);private.chmod(0o600)
 state=owner.get(graph+'/state').json();runs=owner.get(graph+'/runs').json();assert runs[0]['status']=='success' and not state.get('next');messages=state['values']['messages'];index=next(i for i,m in enumerate(messages) if m.get('type')=='human' and m.get('content')==task);calls=[v for m in messages[index:] for v in m.get('tool_calls',[])];assert any(v['name']=='office_pdf' and v['args'].get('action')=='render' and v['args'].get('source_path')==source for v in calls);assert not any(v['name']=='office_pdf' and v['args'].get('action')=='create' for v in calls);assert any(v['name']=='present_files' for v in calls)
 url='/api/threads/'+case['thread_id']+'/artifacts'+output+'?download=true';r=owner.get(url);assert r.status_code==200;png=HERE/args.png;png.write_bytes(r.content)
 with Image.open(png) as im:assert im.format=='PNG' and im.width*im.height<=5_000_000 and im.convert('RGB').getextrema()!=((255,255),(255,255),(255,255));size=im.size
 assert outsider.get(url).status_code==404 and nonowner.get(url).status_code==404;original=owner.get(case['artifact_url']);assert original.status_code==200 and hashlib.sha256(original.content).hexdigest()==case['artifact_sha256'];assert output in json.dumps(owner.post(graph+'/history',json={'limit':5}).json());fresh=login('requester');assert hashlib.sha256(fresh.get(url).content).digest()==hashlib.sha256(r.content).digest()
 result.update({'complete':True,'run_id':runs[0]['run_id'],'task':task,'actual_tool_names':[v['name'] for v in calls],'artifact_url':url,'png_sha256':hashlib.sha256(r.content).hexdigest(),'png_size':size,'source_pdf_unchanged':True,'history_and_fresh_login':True,'nonowners_denied':True,'pdf_regenerated':False})
finally:
 for c in clients:c.close()
 (HERE/args.result).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
