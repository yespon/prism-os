#!/usr/bin/env python3
"""Manage the persistent, loopback-only N04 WSL test stack.

Runtime secrets stay under ignored backend/tmp/n04-wsl with owner-only access.
No existing project database, Docker socket, or CLI account is mounted.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'backend/tmp/n04-wsl'
PROJECT = 'prismos-n04-wsl'
MARKER = 'prismos-owned-n04-wsl-v1'


def owned():
    if STATE.is_symlink() or STATE.resolve() != ROOT / 'backend/tmp/n04-wsl':
        raise ValueError('Unexpected runtime directory')
    if (STATE / 'owner').read_text().strip() != MARKER:
        raise ValueError('Test stack ownership marker required')


def initialize(image):
    image = subprocess.check_output(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], text=True).strip()
    if not image.startswith('sha256:'):
        raise ValueError('Immutable local backend image required')
    if not (ROOT / 'frontend/.next/BUILD_ID').is_file():
        raise ValueError('Previously verified frontend production output required')
    if STATE.exists():
        raise ValueError('Runtime already exists; initialization never overwrites it')
    STATE.mkdir(parents=True, mode=0o700)
    os.chmod(STATE, 0o700)
    (STATE / 'owner').write_text(MARKER + '\n')
    for name in ['home', 'langgraph', 'receiver', 'skills-custom']:
        (STATE / name).mkdir(mode=0o700)
    password = secrets.token_hex(24)
    encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    config = yaml.safe_load((ROOT / 'config.example.yaml').read_text())
    db = f'postgresql+asyncpg://prismos:{password}@postgres:5432/'
    config['database'] = {'type': 'postgres', 'url': db + 'prismos', 'echo': False, 'auth': {'type': 'postgres', 'url': db + 'prismos_auth_db'}}
    config['checkpointer'] = {'type': 'postgres', 'connection_string': db.replace('+asyncpg', '') + 'prismos_checkpoints'}
    config['title']['enabled'] = False
    config['memory']['enabled'] = False
    (STATE / 'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
    (STATE / 'runtime.env').write_text(f'POSTGRES_PASSWORD={password}\nDEERFLOW_SECRETS_ENCRYPTION_KEY={encryption_key}\n')
    receiver = STATE / 'receiver'
    (receiver / 'receiver-token').write_text(secrets.token_urlsafe(32))
    (receiver / 'receiver-mode').write_text('ok\n')
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(receiver / 'server.key'),
        '-out', str(receiver / 'server.crt'), '-days', '30', '-subj', '/CN=ticket-receiver', '-addext', 'subjectAltName=DNS:ticket-receiver,DNS:localhost,IP:127.0.0.1'],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (STATE / 'ca-bundle.crt').write_bytes(Path('/etc/ssl/certs/ca-certificates.crt').read_bytes() + (receiver / 'server.crt').read_bytes())
    environment = {'CI': 'true', 'PRISMOS_HOME': '/app/backend/.prismos', 'PRISMOS_CONFIG_PATH': '/app/config.yaml',
        'DEERFLOW_SECRETS_ENCRYPTION_KEY': '${DEERFLOW_SECRETS_ENCRYPTION_KEY:?required}', 'PRISMOS_TRUSTED_GRAPH_CONTEXT': 'off',
        'PRISMOS_GOVERNED_TICKET_ACTION': 'off', 'PRISMOS_GOVERNED_TICKET_VERDICT': 'deny', 'LANGCHAIN_TRACING_V2': 'false',
        'SSL_CERT_FILE': '/run/n04-ca-bundle.crt', 'CORS_ORIGINS': 'http://localhost:18026,http://127.0.0.1:18026',
        'LANGGRAPH_API_URL': 'http://langgraph:2024', 'PRISMOS_RUNTIME_ADAPTER_MODULE': 'app.runtime_adapters'}
    volumes = [f'{STATE}/config.yaml:/app/config.yaml:ro', f'{STATE}/home:/app/backend/.prismos', f'{STATE}/ca-bundle.crt:/run/n04-ca-bundle.crt:ro', f'{ROOT}/skills:/app/skills:ro', f'{STATE}/skills-custom:/app/skills/custom']
    services = {}
    for name, command in [('db-init', 'uv run --frozen alembic upgrade head'), ('gateway', 'uv run --frozen uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001'),
        ('langgraph', 'uv run --frozen langgraph dev --no-browser --allow-blocking --no-reload --host 0.0.0.0 --port 2024')]:
        service = {'image': image, 'working_dir': '/app/backend', 'command': ['sh', '-c', command], 'volumes': list(volumes),
            'environment': dict(environment), 'restart': 'no', 'mem_limit': '1g', 'cpus': 1.0, 'security_opt': ['no-new-privileges:true'],
            'depends_on': {'postgres': {'condition': 'service_healthy'}}}
        if name != 'db-init':
            service['depends_on']['db-init'] = {'condition': 'service_completed_successfully'}
            port, path = (8001, '/health') if name == 'gateway' else (2024, '/ok')
            service['healthcheck'] = {'test': ['CMD', 'curl', '-fsS', f'http://localhost:{port}{path}'], 'interval': '10s', 'timeout': '5s', 'retries': 12, 'start_period': '30s'}
        if name == 'langgraph':
            service['volumes'].append(f'{STATE}/langgraph:/app/backend/.langgraph_api')
        services[name] = service
    services['postgres'] = {'image': 'postgres:16-alpine', 'environment': {'POSTGRES_USER': 'prismos',
        'POSTGRES_PASSWORD': '${POSTGRES_PASSWORD:?required}', 'POSTGRES_DB': 'prismos'}, 'volumes': ['postgres-data:/var/lib/postgresql/data',
        f'{ROOT}/docker/postgres/init-databases.sql:/docker-entrypoint-initdb.d/01-init-databases.sql:ro'], 'healthcheck': {'test': ['CMD-SHELL',
        'pg_isready -U prismos -d prismos'], 'interval': '5s', 'timeout': '5s', 'retries': 12}, 'mem_limit': '512m',
        'restart': 'no'}
    services['frontend'] = {'image': image, 'working_dir': '/app/frontend', 'command': ['node', 'node_modules/next/dist/bin/next',
        'start', '-H', '0.0.0.0', '-p', '3000'], 'volumes': [f'{ROOT}/frontend:/app/frontend:ro'], 'environment': {'SERVER_BACKEND_URL': 'http://gateway:8001',
        'GATEWAY_URL': 'http://gateway:8001', 'NODE_ENV': 'production', 'NEXT_TELEMETRY_DISABLED': '1'}, 'mem_limit': '512m',
        'restart': 'no', 'security_opt': ['no-new-privileges:true']}
    services['nginx'] = {'image': 'nginx:1.27-alpine', 'ports': ['127.0.0.1:18026:2026'], 'volumes': [f'{ROOT}/docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro'],
        'depends_on': ['gateway', 'langgraph', 'frontend'], 'mem_limit': '128m', 'restart': 'no'}
    services['ticket-receiver'] = {'image': image, 'command': ['python', '/receiver.py'], 'volumes': [f'{ROOT}/docker/n04-test/ticket_receiver.py:/receiver.py:ro',
        f'{receiver}:/state'], 'ports': ['127.0.0.1:18443:8443'], 'mem_limit': '128m', 'cpus': 0.5, 'read_only': True,
        'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'], 'restart': 'no'}
    compose = {'name': PROJECT, 'services': services, 'volumes': {'postgres-data': {}}, 'networks': {'default': {'name': PROJECT + '-network'}}}
    (STATE / 'compose.yaml').write_text(yaml.safe_dump(compose, sort_keys=False))
    for path in STATE.rglob('*'):
        if path.is_file():
            os.chmod(path, 0o600)
    receipt = {'backend_image': image, 'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'],
        cwd=ROOT, text=True).strip(), 'frontend_build_id_sha256': hashlib.sha256((ROOT / 'frontend/.next/BUILD_ID').read_bytes()).hexdigest(),
        'project': PROJECT, 'url': 'http://localhost:18026', 'receiver_url': 'https://ticket-receiver:8443/tickets',
        'm1_exited': False, 'real_model_verified': False}
    (STATE / 'deployment.json').write_text(json.dumps(receipt, indent=2) + '\n')
    os.chmod(STATE / 'deployment.json', 0o600)
    print(json.dumps(receipt))



def enable_skill_storage():
    """Add only the owned writable custom mount; preserve readonly source/public files."""
    owned()
    compose_path = STATE / 'compose.yaml'
    original = compose_path.read_bytes()
    config = yaml.safe_load(original)
    if config.get('name') != PROJECT:
        raise ValueError('Unexpected compose project')
    target = STATE / 'skills-custom'
    if target.is_symlink() or target.resolve() != target or (target.exists() and not target.is_dir()):
        raise ValueError('Unexpected custom Skill storage')
    source_mount = f'{ROOT}/skills:/app/skills:ro'
    custom_mount = f'{target}:/app/skills/custom'
    changed = False
    for name in ['db-init', 'gateway', 'langgraph']:
        volumes = config['services'][name]['volumes']
        if not all(isinstance(value, str) for value in volumes) or source_mount not in volumes:
            raise ValueError('Readonly source Skill mount required')
        existing = [value for value in volumes if value.split(':')[1] == '/app/skills/custom']
        if existing and existing != [custom_mount]:
            raise ValueError('Foreign custom Skill mount refused')
        if not existing:
            volumes.append(custom_mount)
            changed = True
    target.mkdir(mode=0o700, exist_ok=True)
    os.chmod(target, 0o700)
    if changed:
        suffix = secrets.token_hex(8)
        backup = STATE / f'compose-before-skill-storage-{suffix}.yaml'
        temporary = STATE / f'compose-skill-storage-{suffix}.yaml'
        for path, data in [(backup, original), (temporary, yaml.safe_dump(config, sort_keys=False).encode())]:
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temporary, compose_path)
    print(json.dumps({'project': PROJECT, 'custom_skill_storage': str(target), 'source_skills_readonly': True, 'configuration_changed': changed}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'up', 'status', 'stop', 'restart', 'skills-storage'])
    parser.add_argument('--backend-image', default='prismos-office-docx-images:test')
    args = parser.parse_args()
    if args.action == 'init':
        initialize(args.backend_image)
        return
    owned()
    if args.action == 'skills-storage':
        enable_skill_storage()
    compose = ['docker', 'compose', '-p', PROJECT, '--env-file', str(STATE / 'runtime.env'), '-f', str(STATE / 'compose.yaml')]
    actions = {'up': ['up', '-d', '--no-build', '--wait', '--wait-timeout', '240'], 'status': ['ps'],
        'stop': ['stop'], 'restart': ['restart'], 'skills-storage': ['up', '-d', '--no-build', '--no-deps', '--wait',
        '--wait-timeout', '240', 'gateway', 'langgraph']}
    # Never print resolved compose config or runtime environment: both contain credentials.
    subprocess.run(compose + actions[args.action], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
