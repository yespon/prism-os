"""Fresh worker imports and actual DB access across short-lived runtime loops."""

import asyncio
import concurrent.futures
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from deerflow.database import session as database


def test_fresh_terminal_first_worker_import_keeps_both_plugin_routers(tmp_path):
    root = Path(__file__).resolve().parents[2]
    config = tmp_path / 'config.yaml'
    config.write_text(f'database:\n  type: sqlite\n  url: sqlite+aiosqlite:///{tmp_path}/tenant.db\nsandbox:\n  use: LocalSandboxProvider\nplugins:\n  ops-terminal:\n    enabled: true\n  ops-assets:\n    enabled: true\n')
    code = '''import app.services.terminal.session as terminal
assert callable(terminal.build_ssh_command)
from app.gateway.app import app
paths=list(app.openapi()['paths'])
assert any(path.startswith('/api/v1/assets') for path in paths)
assert any(path.startswith('/api/v1/terminal') for path in paths)
print('Fresh Terminal-first worker imports both original plugin routers')
'''
    env = dict(os.environ, PRISMOS_CONFIG_PATH=str(config))
    result = subprocess.run([sys.executable, '-c', code], cwd=root / 'backend', env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    assert 'Failed to import router' not in result.stderr


def test_original_global_factory_survives_separate_and_parallel_worker_loops(tmp_path, monkeypatch):
    url = os.environ.get('PRISMOS_SKILL_TEST_DB_URL', '')
    postgres = url.startswith('postgresql+')
    if postgres:
        parsed = make_url(url)
        if parsed.drivername != 'postgresql+asyncpg' or parsed.host not in {'127.0.0.1', 'localhost'} or parsed.database != 'prismos_skill_probe':
            pytest.fail('Only the owned PostgreSQL probe database is supported')
    else:
        url = 'sqlite+aiosqlite:///' + str(tmp_path / 'runtime.db')
    monkeypatch.setattr(database, '_engine', None)
    monkeypatch.setattr(database, '_session_factory', None)
    monkeypatch.setattr(database, 'get_database_url', lambda: url)
    monkeypatch.setattr(database, 'get_database_echo', lambda: False)
    factory = database.get_session_factory()
    async def query():
        async with factory() as session:
            assert (await session.exec(text('SELECT 1'))).scalar_one() == 1
            if postgres:
                return (await session.exec(text('SELECT pg_backend_pid()'))).scalar_one()
    sequential = [asyncio.run(query()) for _ in range(3)]
    def worker(_):
        return asyncio.run(query())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        parallel = list(pool.map(worker, range(6)))
    if postgres:
        assert len(set(sequential + parallel)) == 9
    asyncio.run(database.get_engine().dispose())
