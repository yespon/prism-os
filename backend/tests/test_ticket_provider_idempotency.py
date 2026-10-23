from datetime import UTC, datetime

import pytest

from app.alerting import ticket_provider
from app.models.alerting import Incident


@pytest.mark.anyio
async def test_webhook_receives_stable_idempotency_key(monkeypatch) -> None:
    captured = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "T-1"}

    class Client:
        def __init__(self, timeout):
            assert timeout == 30

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, url, *, json, headers):
            captured.append((url, json, headers))
            return Response()

    monkeypatch.setattr(ticket_provider.httpx, "AsyncClient", Client)
    incident = Incident(
        id="incident-1", tenant_id="tenant-a", incident_key="INC-1", title="Alarm",
        severity="high", status="open", first_seen_at=datetime(2026, 9, 24, tzinfo=UTC),
        last_seen_at=datetime(2026, 9, 24, tzinfo=UTC),
    )
    config = {
        "provider": "webhook", "webhook_url": "https://tickets.example/create",
        "headers": {"Authorization": "Bearer secret", "idempotency-key": "wrong"},
    }
    result = await ticket_provider.create_ticket(incident, config, idempotency_key="stable-key")
    assert result.ticket_id == "T-1"
    assert captured[0][2]["Idempotency-Key"] == "stable-key"
    assert captured[0][1] == ticket_provider.render_ticket_payload(incident, config)
    await ticket_provider.create_ticket(incident, config)
    assert captured[1][2]["idempotency-key"] == "wrong"


@pytest.mark.anyio
async def test_webhook_failure_does_not_expose_configured_secret(monkeypatch, caplog) -> None:
    import httpx

    class Client:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, url, *, json, headers):
            raise httpx.ConnectError("https://tickets.example/create?token=private-secret")

    monkeypatch.setattr(ticket_provider.httpx, "AsyncClient", Client)
    incident = Incident(id="incident-1", tenant_id="tenant-a", incident_key="INC-1")
    with pytest.raises(RuntimeError) as error:
        await ticket_provider.create_ticket(
            incident, {"webhook_url": "https://tickets.example/create?token=private-secret"},
            idempotency_key="stable-key",
        )
    assert "private-secret" not in str(error.value)
    assert "private-secret" not in caplog.text
