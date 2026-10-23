from pathlib import Path
import json,subprocess,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
lines=(ROOT/'backend/tmp/n04-wsl/office-pack-f44da91eda/stream.txt').read_text().splitlines();messages=[]
for line in lines:
 if line.startswith('data: '):
  try:
   value=json.loads(line[6:])
   if isinstance(value,dict) and value.get('messages'):messages=value['messages']
  except ValueError:pass
calls=[call for message in messages for call in message.get('tool_calls',[]) if call['name']=='office_pdf'];assert calls
arguments=calls[-1]['args'];(HERE/'actual-pdf-input.json').write_text(json.dumps(arguments,indent=2)+'\n')
if '--without-empty' in sys.argv:
 arguments['document']['pages']=[[line for line in page if line] for page in arguments['document']['pages']]
image=json.loads((HERE.parent/'2026-10-16-octop-office-expert-task/runtime-image.json').read_text())['image']
if '--current' in sys.argv:image=json.loads((HERE/'runtime-image.json').read_text())['image']
code='import sys,json,hashlib;from deerflow.tools.builtins.office_pdf import create_pdf;data=create_pdf(json.load(sys.stdin));print(json.dumps({"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}))'
result=subprocess.run(['docker','run','--rm','--network','none','--memory','512m','--pids-limit','64','-i','--name','prismos-pdf-actual-repro',image,'sh','-c','cd /app/backend && .venv/bin/python -c "$1"','sh',code],input=json.dumps(arguments['document']).encode(),capture_output=True)
print(json.dumps({'image':image,'returncode':result.returncode,'stdout':result.stdout.decode(errors='replace'),'stderr':result.stderr.decode(errors='replace')}));raise SystemExit(result.returncode)
