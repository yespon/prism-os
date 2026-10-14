"""Original terminal tools must refuse foreign asset and credential lookup."""
import asyncio
from types import SimpleNamespace

import pytest
from test_agent_skill_references import configured, scoped_client  # noqa: F401
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from app.agent import terminal_tools
from app.models.assets import LocalAsset


def test_foreign_terminal_asset_never_starts_ssh(configured, monkeypatch):
    _, factory, _, _ = configured
    async def create():
        async with factory() as session:
            session.add(LocalAsset(id='foreign-host', tenant_id='tenant-b', user_id='foreign-user', name='Foreign', ip='127.0.0.1'))
            await session.commit()
    asyncio.run(create())
    starts = []
    session = SimpleNamespace(pty=SimpleNamespace(fd=None), start=lambda **kwargs: starts.append(kwargs))
    monkeypatch.setattr(terminal_tools, 'get_session_factory', lambda: factory)
    monkeypatch.setattr(terminal_tools.session_manager, 'get_or_create_session', lambda *args: session)
    monkeypatch.setattr('app.gateway.routers.terminal.build_ssh_command', lambda *args: (['authorized-test-sentinel'], {}, []))
    terminal_tools.set_terminal_context({'tenant_id':'tenant-a','user_id':'user-a','terminal_session_id':'same-session','selected_assets':[{'id':'foreign-host'}]})
    try:
        asyncio.run(terminal_tools._ensure_session('foreign-host'))
    except PermissionError:
        pass
    assert starts == [], 'Foreign tenant SSH connection started using only untrusted selected asset id'
