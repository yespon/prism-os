import json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
STATE=HERE.parents[3]/'backend/tmp/n04-wsl'
fixture=json.loads((STATE/'live-fixture.json').read_text())
protected=[(STATE/'receiver/receiver-token').read_bytes().strip(),(STATE/'receiver/server.key').read_bytes()]
protected += [line.split(b'=',1)[1] for line in (STATE/'runtime.env').read_bytes().splitlines() if b'=' in line]
protected += [user['password'].encode() for user in fixture['users'].values()]
protected += [(STATE/'native-profile/analytics-service/token').read_bytes().strip()]
files=[p for p in HERE.rglob('*') if p.is_file()]
# Check real audit/receiver storage boundaries too; snapshots intentionally contain private secrets.
runtime_exports=[STATE/'home/audit/events.jsonl',STATE/'receiver/receipts.db']
assert all(p.is_file() and not p.is_symlink() for p in runtime_exports)
files+=runtime_exports
blob=b'\n'.join(p.read_bytes() for p in files)
assert all(value not in blob for value in protected if value),'Known runtime credential found in public evidence'
code='''import json,logging,sys
logging.disable(logging.CRITICAL)
blob=sys.stdin.buffer.read()
try:
 from deerflow.models.factory import create_chat_model
 model=create_chat_model('gpt-5.6-luna')
 key=getattr(model,'openai_api_key',None) or getattr(model,'api_key',None)
 value=key.get_secret_value() if hasattr(key,'get_secret_value') else str(key or '')
 opaque=bool(value) and value not in {'test','sk-test','not-needed','dummy'}
 found=opaque and value.encode() in blob
 print(json.dumps({'opaque_model_credential_checked':opaque,'model_credential_found_in_export':bool(found)}))
 raise SystemExit(1 if found else 0)
except Exception as error:
 print(json.dumps({'credential_check_error_type':type(error).__name__}))
 raise SystemExit(1)
'''
result=subprocess.run(['docker','exec','-i','-w','/app/backend','prismos-n04-wsl-gateway-1','uv','run','--frozen','python','-c',code],input=blob,capture_output=True,timeout=60)
receipt=json.loads(result.stdout.decode().splitlines()[-1]);assert result.returncode==0,receipt
receipt.update({'known_runtime_credentials_checked':True,'public_file_count':len(files)-len(runtime_exports),'runtime_export_boundary_files_checked':len(runtime_exports),'model_request_sent':False,'plaintext_model_credential_exported':False})
(HERE/'public-secret-check.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
