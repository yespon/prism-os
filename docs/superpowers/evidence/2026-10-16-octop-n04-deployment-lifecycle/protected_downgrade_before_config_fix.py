"""Exercise the original nonempty SecretRef downgrade guard on an actual snapshot clone."""
from pathlib import Path
import json,secrets,subprocess,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import octop_wsl_test_snapshot as snapshot
snapshot.assert_owned_services()
source=ROOT/'backend/tmp/n04-deployment-snapshot-20261016';snapshot.safe_directory(source,existing=True)
manifest=json.loads((source/'manifest.json').read_text());clone='prismos_snapshot_guard_'+secrets.token_hex(6)
receipt={'complete':False,'M1_exited':False,'live_database_downgrade_attempted':False};created=False
try:
 snapshot.execute('postgres',['createdb','-U','prismos',clone]);created=True
 snapshot.execute('postgres',['pg_restore','-U','prismos','-d',clone],(source/'prismos.dump').read_bytes())
 before=snapshot.database_manifest(clone);assert before==manifest['databases']['prismos']['tables']
 count=int(snapshot.execute('postgres',['psql','-X','-qAt','-U','prismos','-d',clone,'-c','SELECT count(*) FROM platform_ticket_secrets']).decode());assert count>0
 config=snapshot.yaml.safe_load((source/'config.yaml').read_text());snapshot.validate_database_scope(config)
 from sqlalchemy.engine import make_url
 config['database']['url']=make_url(config['database']['url']).set(database=clone).render_as_string(hide_password=False)
 config['database']['auth']['url']=make_url(config['database']['auth']['url']).set(database=clone).render_as_string(hide_password=False)
 config['checkpointer']['connection_string']=make_url(config['checkpointer']['connection_string']).set(database=clone).render_as_string(hide_password=False)
 code='''import json,logging,os,subprocess,sys,tempfile
logging.disable(logging.CRITICAL)
value=json.load(sys.stdin);fd,path=tempfile.mkstemp(prefix='prismos-owned-downgrade-',suffix='.yaml')
try:
 with os.fdopen(fd,'w') as stream:stream.write(value['config'])
 os.environ['PRISMOS_CONFIG_PATH']=path
 from deerflow.database.session import get_engine
 from sqlalchemy.engine import make_url
 assert get_engine().url.database==value['database']
 result=subprocess.run(['uv','run','--frozen','alembic','downgrade','m7g8h9i0j1k2'],capture_output=True)
 output=result.stdout+result.stderr
 matched=b'ticket secret records exist; restore or migrate references before downgrade' in output
 print(json.dumps({'returncode':result.returncode,'expected_nonempty_guard':matched,'clone_database_selected':True}))
 if result.returncode==0 or not matched:raise SystemExit(1)
finally:os.unlink(path)
'''
 result=snapshot.execute('gateway',['uv','run','--frozen','python','-c',code],json.dumps({'config':snapshot.yaml.safe_dump(config),'database':clone}).encode())
 receipt['original_alembic']=json.loads(result.decode().splitlines()[-1]);assert receipt['original_alembic']['expected_nonempty_guard']
 after=snapshot.database_manifest(clone);assert after==before
 receipt.update({'complete':True,'nonempty_secret_rows':count,'all_snapshot_rows_unchanged_after_refused_downgrade':True})
finally:
 if created:snapshot.execute('postgres',['dropdb','-U','prismos',clone]);receipt['owned_clone_removed']=True
 (HERE/'protected-downgrade-current.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
