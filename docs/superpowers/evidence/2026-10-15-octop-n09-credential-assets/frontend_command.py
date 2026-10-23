from pathlib import Path
import os,subprocess,sys
ROOT=Path(__file__).resolve().parents[4]
env=dict(os.environ)
env['PATH']='/root/.nvm/versions/node/v24.11.1/bin:'+env.get('PATH','')
env['COREPACK_HOME']='/root/.cache/node/corepack'
env['COREPACK_ENABLE_NETWORK']='0'
raise SystemExit(subprocess.run(['pnpm',*sys.argv[1:]],cwd=ROOT/'frontend',env=env).returncode)
