#!/usr/bin/env python3
"""Verify the owned WSL deployment without claiming real model/governance acceptance."""

import argparse
import hashlib
import json
import os
import secrets
import ssl
import subprocess
import time
from pathlib import Path

import httpx
from octop_wsl_test_env import PROJECT, ROOT, STATE, owned

PROVIDER = '''import asyncio,json,sys
from datetime import UTC,datetime
from app.alerting.ticket_provider import create_ticket
from app.models.alerting import Incident
async def main():
 value=json.load(sys.stdin)
 now=datetime(2026,10,16,tzinfo=UTC)
 incident=Incident(id='n04-transport',tenant_id='n04-transport',incident_key='N04-TRANSPORT',title='N04 transport verification',first_seen_at=now,last_seen_at=now)
 try:
  result=await create_ticket(incident,{'provider':'webhook','webhook_url':'https://ticket-receiver:8443/tickets','headers':{'Authorization':'Bearer '+value['token']}},idempotency_key=value['idempotency_key'])
  print(json.dumps({'status':'ok','ticket_id':result.ticket_id}))
 except RuntimeError:
  print(json.dumps({'status':'failed_or_unknown'}))
asyncio.run(main())
'''


def execute(service, command, data=None):
    return subprocess.run(['docker', 'compose', '-p', PROJECT, '--env-file', str(STATE / 'runtime.env'), '-f', str(STATE / 'compose.yaml'), 'exec', '-T', service, *command], cwd=ROOT, input=data, capture_output=True, check=True).stdout


def public_health():
    with httpx.Client(base_url='http://127.0.0.1:18026', trust_env=False, timeout=20) as client:
        assert client.get('/health').status_code == 200
        setup = client.get('/api/auth/bootstrap-status')
        assert setup.status_code == 200
        assert client.get('/api/agent-catalog/status').status_code == 401
        assert client.post('/api/langgraph/threads', json={}).status_code == 401
        page = client.get('/', follow_redirects=True)
        assert page.status_code == 200
        return {'health': 200, 'bootstrap_needs_setup': setup.json()['needs_setup'], 'unauthenticated_catalog': 401, 'unauthenticated_thread': 401, 'frontend': 200}


def receiver_probe():
    receiver = STATE / 'receiver'
    token = (receiver / 'receiver-token').read_text().strip()
    context = ssl.create_default_context(cafile=str(receiver / 'server.crt'))
    with httpx.Client(base_url='https://127.0.0.1:18443', verify=context, trust_env=False, timeout=10, headers={'Authorization': 'Bearer ' + token}) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/stats', headers={'Authorization': ''}).status_code == 401
        before = client.get('/stats').json()
        key = 'n04-transport-' + secrets.token_hex(8)
        def provider(identity):
            value = execute('gateway', ['uv', 'run', '--frozen', 'python', '-c', PROVIDER], json.dumps({'token': token, 'idempotency_key': identity}).encode())
            return json.loads(value)
        try:
            (receiver / 'receiver-mode').write_text('ok\n')
            first = provider(key)
            repeated = provider(key)
            assert first['status'] == 'ok' and first == repeated
            after_ok = client.get('/stats').json()
            assert after_ok['request_count'] - before['request_count'] == 2
            assert after_ok['distinct_ticket_count'] - before['distinct_ticket_count'] == 1
            (receiver / 'receiver-mode').write_text('fail\n')
            assert provider(key + '-fail')['status'] == 'failed_or_unknown'
            (receiver / 'receiver-mode').write_text('timeout\n')
            assert provider(key + '-timeout')['status'] == 'failed_or_unknown'
            after = client.get('/stats').json()
            assert after['request_count'] - before['request_count'] == 4
            assert [r['mode'] for r in after['receipts'][-4:]] == ['ok', 'ok', 'fail', 'timeout']
        finally:
            (receiver / 'receiver-mode').write_text('ok\n')
        return {'scope': 'real TLS and original Provider only; no model or governed Action', 'requests_before': before['request_count'],
            'requests_after': after['request_count'], 'delta': 4, 'same_idempotency_ticket': True, 'http_failure_counted': True,
            'actual_provider_timeout_counted': True, 'certificate_verification': True}


def backup_restore():
    backup = STATE / ('backup-' + secrets.token_hex(6))
    backup.mkdir(mode=0o700)
    receipts = {}
    for name in ['prismos', 'prismos_auth_db', 'prismos_checkpoints']:
        data = execute('postgres', ['pg_dump', '-U', 'prismos', '-d', name, '-Fc'])
        path = backup / (name + '.dump')
        path.write_bytes(data)
        os.chmod(path, 0o600)
        restored = name + '_restore_' + secrets.token_hex(3)
        execute('postgres', ['createdb', '-U', 'prismos', restored])
        execute('postgres', ['pg_restore', '-U', 'prismos', '-d', restored], data)
        original_count = execute('postgres', ['psql', '-U', 'prismos', '-d', name, '-Atc', "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"]).decode().strip()
        restored_count = execute('postgres', ['psql', '-U', 'prismos', '-d', restored, '-Atc', "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"]).decode().strip()
        assert original_count == restored_count
        receipts[name] = {'dump_sha256': hashlib.sha256(data).hexdigest(), 'table_count': int(original_count), 'restored_database': restored}
        if name == 'prismos':
            head = execute('postgres', ['psql', '-U', 'prismos', '-d', restored, '-Atc', 'SELECT version_num FROM alembic_version']).decode().strip()
            assert head == 'n8h9i0j1k2l3'
            receipts[name]['migration_head'] = head
    return {'private_backup_directory': str(backup), 'databases': receipts, 'scope': 'independent PostgreSQL dump/restore; no golden model run or deployment rollback claim'}


def restart():
    before = public_health()
    subprocess.run(['docker', 'compose', '-p', PROJECT, '--env-file', str(STATE / 'runtime.env'), '-f', str(STATE / 'compose.yaml'), 'restart', 'gateway', 'langgraph', 'ticket-receiver'], capture_output=True, check=True)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            after = public_health()
            if before['bootstrap_needs_setup'] == after['bootstrap_needs_setup']:
                break
        except (httpx.HTTPError, AssertionError):
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Owned stack did not recover')
    return {'gateway_health_recovered': True, 'bootstrap_state_preserved': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['health', 'receiver', 'backup', 'restart'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    owned()
    if args.output.exists():
        raise ValueError('Existing evidence is never overwritten')
    functions = {'health': public_health, 'receiver': receiver_probe, 'backup': backup_restore, 'restart': restart}
    result = functions[args.action]()
    result.update({'real_model_verified': False, 'M1_exited': False})
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
