"""Reconcile exactly one nonsemantic trailing-space cleanup without hiding input changes."""
from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
p=ROOT/'frontend/src/components/workspace/terminal/persistent-terminal.tsx'
source=p.read_text()
marker='            key={identity.key} \n'
assert source.count(marker)==1
before=json.loads((HERE/'frontend-inputs.json').read_text())
name=p.relative_to(ROOT).as_posix()
assert hashlib.sha256(p.read_bytes()).hexdigest()==before['sha256'][name]
assert json.loads((HERE/'upgrade-result.json').read_text())['returncode']==0
clean=source.replace(marker,'            key={identity.key}\n')
code="const ts=require('typescript'),crypto=require('crypto');let data='';process.stdin.on('data',c=>data+=c);process.stdin.on('end',()=>{const p=JSON.parse(data);const emit=s=>ts.transpileModule(s,{fileName:'persistent-terminal.tsx',compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX,sourceMap:false,inlineSourceMap:false}}).outputText;const a=emit(p.before),b=emit(p.after);if(a!==b)throw Error('Emitted JavaScript changed');process.stdout.write(JSON.stringify({typescript:ts.version,identical_javascript:true,javascript_sha256:crypto.createHash('sha256').update(a).digest('hex')}));});"
result=subprocess.run(['/root/.nvm/versions/node/v24.11.1/bin/node','-e',code],cwd=ROOT/'frontend',input=json.dumps({'before':source,'after':clean}),text=True,capture_output=True,check=True)
proof=json.loads(result.stdout)
(HERE/'frontend-inputs-before-format.json').write_text(json.dumps(before,indent=2)+'\n')
p.write_text(clean)
proof.update(path=name,before_sha256=before['sha256'][name],after_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),change='one trailing ASCII space before newline; no other bytes changed',original_full_tests=277,original_strict_build_preserved=True,upgrade_completed_before_cleanup=True)
(HERE/'format-only-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
after=json.loads(json.dumps(before));after['sha256'][name]=proof['after_sha256']
(HERE/'frontend-inputs.json').write_text(json.dumps(after,indent=2)+'\n')
commands=[]
for label,args in [('frontend-format-typecheck',['typecheck']),('frontend-format-related',['test:unit','src/components/workspace/terminal/asset-dialogs.test.tsx','--maxWorkers=1'])]:
    commands.append([sys.executable,str(HERE/'run_validation.py'),label,'--',sys.executable,str(HERE/'frontend_command.py'),*args])
jobs=[subprocess.Popen(args,cwd=ROOT) for args in commands]
codes=[job.wait() for job in jobs]
assert codes==[0,0],codes
assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in after['sha256'].items())
print('One-space cleanup, identical emitted JavaScript, current typecheck and all six dependent component tests verified')
