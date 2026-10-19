"""R3 schedule tool contracts."""

from unittest.mock import patch

import pytest

from app.scheduling.tools import governed_schedule_tools


def test_tool_hidden_without_canary():
    tools = governed_schedule_tools({"tenant_id": "t1", "user_id": "u1", "agent_name": "default"})
    assert tools == []


@pytest.mark.anyio
async def test_tool_creates_schedule_when_canary_on(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models import scheduling as _scheduling_models  # noqa: F401
    from app.scheduling import ScheduleService

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sched-tools.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service = ScheduleService(factory)
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "t1")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")

    with patch("app.scheduling.tools.ScheduleService", lambda: service):
        tools = governed_schedule_tools({"tenant_id": "t1", "user_id": "u1", "agent_name": "default"})
        assert [t.name for t in tools] == ["schedule.create"]
        result = await tools[0].ainvoke({
            "name": "nightly check", "trigger_kind": "cron",
            "cron_expr": "0 3 * * *", "prompt": "Run the nightly health check.",
        })
    assert result["status"] == "created"
    listed = await service.list_definitions("t1")
    assert len(listed) == 1 and listed[0].name == "nightly check"
    await engine.dispose()


@pytest.mark.anyio
async def test_tool_rejects_invalid_definition(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models import scheduling as _scheduling_models  # noqa: F401
    from app.scheduling import ScheduleService

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sched-tools-2.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service = ScheduleService(factory)
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "t1")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")

    with patch("app.scheduling.tools.ScheduleService", lambda: service):
        tools = governed_schedule_tools({"tenant_id": "t1", "user_id": "u1", "agent_name": "default"})
        result = await tools[0].ainvoke({
            "name": "broken", "trigger_kind": "cron", "prompt": "no cron expression",
        })
    assert result["status"] == "rejected" and "cron_expr" in result["reason"]
    await engine.dispose()
