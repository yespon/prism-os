from pathlib import Path
import json,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
code='''import json,logging
logging.disable(logging.CRITICAL)
from deerflow.models.factory import create_chat_model
try:
 model=create_chat_model('gpt-5.6-luna',timeout=45,max_retries=0)
 response=model.invoke('Reply with exactly N04_MODEL_READY. Do not call tools.')
 print(json.dumps({'model_name':'gpt-5.6-luna','actual_request_completed':True,'expected_text_received':'N04_MODEL_READY' in str(response.content),'tool_calls':len(response.tool_calls),'scope':'direct original factory connectivity only; not authenticated graph/Action acceptance'}))
except Exception as exc:
 print(json.dumps({'actual_request_completed':False,'error_type':type(exc).__name__}))
 raise SystemExit(1)
'''
p=subprocess.run(['docker','exec','-w','/app/backend','prismos-n04-wsl-gateway-1','uv','run','--frozen','python','-c',code],capture_output=True,timeout=90)
# Raw SDK errors can contain private URLs; only the bounded JSON diagnostic is exported.
lines=p.stdout.decode().splitlines()
result=next((json.loads(line) for line in reversed(lines) if line.startswith('{')),{'actual_request_completed':False,'error_type':'missing_probe_receipt'})
(HERE/'model-connectivity.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
assert p.returncode==0 and result['actual_request_completed'] and result['expected_text_received']
