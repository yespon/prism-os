from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.alerting import governed_ticket
from app.alerting.ticket_provider import TicketResult
from app.models.alerting import AlertSource, Incident, IncidentSignalLink, RawAlert, Signal


@pytest.mark.anyio
async def test_real_ticket_target_resolves_only_active_source_in_tenant(tmp_path, monkeypatch) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ticket-target.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(governed_ticket, "get_session_factory", lambda: factory)
    now = datetime(2026, 9, 24, tzinfo=UTC)
    async with factory() as session:
        session.add_all([
            Incident(id="incident-1", tenant_id="tenant-a", incident_key="INC-1", title="Alarm", first_seen_at=now, last_seen_at=now),
            AlertSource(id="source-1", tenant_id="tenant-a", name="monitor", status="active", config_json={
                "ticket": {"provider": "webhook", "webhook_url": "https://tickets.example/create"},
            }),
            RawAlert(id="raw-1", tenant_id="tenant-a", source_id="source-1", payload_hash="hash-1", received_at=now),
            Signal(id="signal-1", tenant_id="tenant-a", raw_alert_id="raw-1", fingerprint="fingerprint-1", title="CPU high"),
            IncidentSignalLink(id="link-1", tenant_id="tenant-a", incident_id="incident-1", signal_id="signal-1"),
        ])
        await session.commit()
    target = await governed_ticket.resolve_ticket_target("tenant-a", "incident-1")
    assert target.config["webhook_url"] == "https://tickets.example/create"
    assert target.signals[0]["title"] == "CPU high"
    with pytest.raises(ValueError, match="unavailable"):
        await governed_ticket.resolve_ticket_target("tenant-b", "incident-1")
    await governed_ticket.link_incident_ticket(
        "tenant-a", "incident-1", TicketResult(ticket_id="T-1", ticket_url=None, provider="webhook"),
    )
    assert (await governed_ticket.resolve_ticket_target("tenant-a", "incident-1")).incident.ticket_id == "T-1"
    async with factory() as session:
        source = await session.get(AlertSource, "source-1")
        source.status = "disabled"
        await session.commit()
    with pytest.raises(ValueError, match="configured webhook"):
        await governed_ticket.resolve_ticket_target("tenant-a", "incident-1")
    await engine.dispose()
