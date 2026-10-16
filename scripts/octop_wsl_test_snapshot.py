#!/usr/bin/env python3
"""Private full-state snapshot/clone restore for the owned loopback WSL test stack."""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import tarfile
from pathlib import Path

import yaml

from octop_wsl_test_env import PROJECT, ROOT, STATE, owned
from octop_wsl_test_probe import execute

MARKER = 'prismos-owned-n04-snapshot-v1'
DATABASES = ('prismos', 'prismos_auth_db', 'prismos_checkpoints')
RUNTIME_PATHS = ('owner', 'deployment.json', 'config.yaml', 'runtime.env', 'compose.yaml', 'ca-bundle.crt', 'home', 'skills-custom', 'langgraph', 'receiver')


def private_write(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def safe_directory(path, *, existing=False):
    path = Path(path)
    base = (ROOT / 'backend/tmp').resolve()
    if not path.is_absolute() or path.is_symlink() or path.resolve() != path or not path.is_relative_to(base) or path == base:
        raise ValueError('Snapshot must be an owned non-aliased directory under backend/tmp')
    if existing:
        if not path.is_dir() or (path / 'owner').is_symlink() or (path / 'owner').read_text().strip() != MARKER:
            raise ValueError('Snapshot ownership marker required')
    elif path.exists():
        raise ValueError('Existing snapshot is never overwritten')
    return path


def compose(args):
    return subprocess.run(['docker', 'compose', '-p', PROJECT, '--env-file', str(STATE / 'runtime.env'), '-f', str(STATE / 'compose.yaml'), *args], cwd=ROOT, check=True, capture_output=True).stdout


def assert_owned_services():
    owned()
    for name in ['gateway', 'langgraph', 'postgres', 'ticket-receiver']:
        info = json.loads(subprocess.check_output(['docker', 'inspect', PROJECT + '-' + name + '-1'], text=True))[0]
        if info['Config']['Labels']['com.docker.compose.project'] != PROJECT:
            raise ValueError('Foreign service refused')
        if name in ['gateway', 'langgraph']:
            env = dict(value.split('=', 1) for value in info['Config']['Env'])
            if env.get('PRISMOS_GOVERNED_TICKET_ACTION') != 'off' or env.get('PRISMOS_TRUSTED_GRAPH_CONTEXT') != 'off':
                raise ValueError('Close the owned canary before taking a deployment snapshot')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def tree_manifest(root):
    result = {}
    for name in RUNTIME_PATHS:
        path = root / name
        if not path.exists() or path.is_symlink():
            raise ValueError('Required runtime component unavailable or aliased')
        entries = [path, *path.rglob('*')] if path.is_dir() else [path]
        for entry in entries:
            if entry.is_symlink() or entry.resolve() != entry or not (entry.is_file() or entry.is_dir()):
                raise ValueError('Snapshot runtime contains an alias or special file')
            relative = entry.relative_to(root).as_posix()
            result[relative] = {'type': 'directory' if entry.is_dir() else 'file', 'mode': entry.stat().st_mode & 0o777}
            if entry.is_file():
                result[relative].update(size=entry.stat().st_size, sha256=digest(entry))
    return result


def database_manifest(database):
    tables = execute('postgres', ['psql', '-X', '-qAt', '-U', 'prismos', '-d', database, '-c', "SELECT quote_ident(schemaname)||'.'||quote_ident(tablename) FROM pg_tables WHERE schemaname NOT LIKE 'pg_%' AND schemaname <> 'information_schema' ORDER BY schemaname,tablename"]).decode().splitlines()
    queries = []
    for table in tables:
        label = table.replace("'", "''")
        queries.append("SELECT json_build_object('table','" + label + "','rows',count(*),'sha256',encode(sha256(convert_to(COALESCE(string_agg(encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex'),'' ORDER BY encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex')),''),'UTF8')),'hex')) FROM " + table + ' t')
    if not queries:
        return []
    data = execute('postgres', ['psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'prismos', '-d', database], (';\n'.join(queries) + ';\n').encode()).decode()
    return [json.loads(line) for line in data.splitlines()]



def validate_database_scope(config):
    from sqlalchemy.engine import make_url

    references = [config['database']['url'], config['database']['auth']['url'], config['checkpointer']['connection_string']]
    for reference, expected in zip(references, DATABASES, strict=True):
        url = make_url(reference)
        if not url.drivername.startswith('postgresql') or url.host != 'postgres' or url.username != 'prismos' or url.database != expected or url.port not in (None, 5432):
            raise ValueError('Snapshot configuration references a foreign database')


def create_snapshot(path):
    assert_owned_services()
    path = safe_directory(path)
    path.mkdir(mode=0o700)
    private_write(path / 'owner', (MARKER + '\n').encode())
    manifest = {'schema': MARKER, 'complete': False, 'runtime_files': {}, 'databases': {}, 'writers_stopped': ['gateway', 'langgraph', 'ticket-receiver']}
    stopped = False
    try:
        # Restore the current stack even when a component is missing or a dump fails.
        stopped = True
        compose(['stop', 'gateway', 'langgraph', 'ticket-receiver'])
        manifest['runtime_files'] = tree_manifest(STATE)
        validate_database_scope(yaml.safe_load((STATE / 'config.yaml').read_text()))
        archive_path = path / 'runtime.tar'
        with os.fdopen(os.open(archive_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            with tarfile.open(fileobj=stream, mode='w') as archive:
                for name in RUNTIME_PATHS:
                    archive.add(STATE / name, arcname=name, recursive=True)
            stream.flush()
            os.fsync(stream.fileno())
        manifest['archive_sha256'] = digest(archive_path)
        for database in DATABASES:
            rows = database_manifest(database)
            data = execute('postgres', ['pg_dump', '-U', 'prismos', '-d', database, '-Fc'])
            private_write(path / (database + '.dump'), data)
            manifest['databases'][database] = {'dump_sha256': hashlib.sha256(data).hexdigest(), 'tables': rows}
        assert tree_manifest(STATE) == manifest['runtime_files'], 'Runtime changed despite writer stop'
        manifest['complete'] = True
    finally:
        try:
            private_write(path / 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
        finally:
            if stopped:
                compose(['up', '-d', '--no-build', '--no-deps', '--wait', '--wait-timeout', '240', 'gateway', 'langgraph', 'ticket-receiver'])
    return {'complete': True, 'private_snapshot_directory': str(path), 'runtime_entries': len(manifest['runtime_files']), 'databases': len(manifest['databases']), 'writers_restarted': True, 'private_material_exported': False, 'M1_exited': False}


MODEL_RESTORE = '''import asyncio,json,logging,os,sys,tempfile
logging.disable(logging.CRITICAL)
value=json.load(sys.stdin)
fd,path=tempfile.mkstemp(prefix='prismos-owned-snapshot-',suffix='.yaml')
try:
 with os.fdopen(fd,'w') as stream:stream.write(value['config'])
 os.environ['PRISMOS_CONFIG_PATH']=path
 os.environ['DEERFLOW_SECRETS_ENCRYPTION_KEY']=value['master_key']
 from deerflow.database.session import get_session_factory
 from sqlalchemy import text
 async def check_database():
  async with get_session_factory()() as session:
   actual=(await session.execute(text('SELECT current_database()'))).scalar_one()
   if actual!=value['expected_app_database']:raise ValueError('Restored database was not selected')
 asyncio.run(check_database())
 from deerflow.models.factory import create_chat_model
 model=create_chat_model(value['model_name'])
 key=getattr(model,'openai_api_key',None) or getattr(model,'api_key',None)
 secret=key.get_secret_value() if hasattr(key,'get_secret_value') else str(key or '')
 opaque=bool(secret) and secret not in {'test','sk-test','not-needed','dummy'}
 if not opaque:raise ValueError('Restored model has no opaque credential')
 print(json.dumps({'configured_model_restored':True,'restored_database_selected':True,'opaque_model_credential_restored':True,'model_request_sent':False,'plaintext_credential_exported':False}))
except Exception as error:
 print(json.dumps({'restore_error_type':type(error).__name__}))
 raise SystemExit(1)
finally:os.unlink(path)
'''


def restore_model_configuration(restored, clones, model_name):
    from sqlalchemy.engine import make_url

    config = yaml.safe_load((restored / 'config.yaml').read_text())
    validate_database_scope(config)
    config['database']['url'] = make_url(config['database']['url']).set(database=clones['prismos']).render_as_string(hide_password=False)
    config['database']['auth']['url'] = make_url(config['database']['auth']['url']).set(database=clones['prismos_auth_db']).render_as_string(hide_password=False)
    config['checkpointer']['connection_string'] = make_url(config['checkpointer']['connection_string']).set(database=clones['prismos_checkpoints']).render_as_string(hide_password=False)
    settings = dict(line.split('=', 1) for line in (restored / 'runtime.env').read_text().splitlines() if '=' in line)
    payload = {'config': yaml.safe_dump(config), 'master_key': settings['DEERFLOW_SECRETS_ENCRYPTION_KEY'], 'model_name': model_name, 'expected_app_database': clones['prismos']}
    result = execute('gateway', ['uv', 'run', '--frozen', 'python', '-c', MODEL_RESTORE], json.dumps(payload).encode())
    proof = json.loads(result.decode().splitlines()[-1])
    if not proof.get('configured_model_restored') or not proof.get('opaque_model_credential_restored'):
        raise ValueError('Restored model configuration unavailable')
    return proof


def verify_snapshot(path, model_name=None):
    assert_owned_services()
    path = safe_directory(path, existing=True)
    for name in ['manifest.json', 'runtime.tar', *[database + '.dump' for database in DATABASES]]:
        if (path / name).is_symlink() or (path / name).resolve() != path / name:
            raise ValueError('Snapshot input contains a filesystem alias')
    manifest = json.loads((path / 'manifest.json').read_text())
    if manifest.get('schema') != MARKER or manifest.get('complete') is not True:
        raise ValueError('Complete owned snapshot required')
    if digest(path / 'runtime.tar') != manifest['archive_sha256']:
        raise ValueError('Snapshot archive changed')
    for database in DATABASES:
        if digest(path / (database + '.dump')) != manifest['databases'][database]['dump_sha256']:
            raise ValueError('Snapshot database dump changed')
    restored = path / ('restored-files-' + secrets.token_hex(6))
    restored.mkdir(mode=0o700)
    with tarfile.open(path / 'runtime.tar') as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)) or set(names) != set(manifest['runtime_files']):
            raise ValueError('Archive member manifest differs')
        for member in members:
            relative = Path(member.name)
            if relative.is_absolute() or '..' in relative.parts or relative.parts[0] not in RUNTIME_PATHS or not (member.isfile() or member.isdir()):
                raise ValueError('Snapshot member escapes the owned runtime or is a special file')
        archive.extractall(restored, filter='data')
    # data_filter intentionally discards directory modes; restore only attested modes.
    for name, expected in manifest['runtime_files'].items():
        if not isinstance(expected.get('mode'), int) or not 0 <= expected['mode'] <= 0o777:
            raise ValueError('Invalid attested file mode')
        os.chmod(restored / name, expected['mode'])
    if tree_manifest(restored) != manifest['runtime_files']:
        raise ValueError('Restored file bytes or modes changed')
    clones = {}
    checked = {}
    model = None
    try:
        for database in DATABASES:
            clone = 'prismos_snapshot_' + secrets.token_hex(8)
            execute('postgres', ['createdb', '-U', 'prismos', clone])
            clones[database] = clone
            execute('postgres', ['pg_restore', '-U', 'prismos', '-d', clone], (path / (database + '.dump')).read_bytes())
            restored_rows = database_manifest(clone)
            if restored_rows != manifest['databases'][database]['tables']:
                raise ValueError('Restored database row content differs')
            checked[database] = {'tables': len(restored_rows), 'rows': sum(table['rows'] for table in restored_rows), 'all_row_digests_match': True}
        if model_name:
            model = restore_model_configuration(restored, clones, model_name)
    finally:
        for clone in clones.values():
            execute('postgres', ['dropdb', '-U', 'prismos', clone])
    return {'complete': True, 'private_snapshot_directory': str(path), 'private_restored_files': str(restored), 'all_file_bytes_and_modes_match': True, 'databases': checked, 'owned_clone_databases_removed': True, 'model_configuration': model, 'scope': 'Full runtime bytes/modes and all database row contents restored into owned clones; optional original model factory validates restored encrypted settings without a model request. Not an application artifact rollback or full restored user-flow claim.', 'M1_exited': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'verify'])
    parser.add_argument('--snapshot-dir', type=Path, required=True)
    parser.add_argument('--model-name')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Existing evidence is never overwritten')
    result = create_snapshot(args.snapshot_dir) if args.action == 'create' else verify_snapshot(args.snapshot_dir, args.model_name)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
