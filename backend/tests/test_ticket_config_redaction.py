from copy import deepcopy

import pytest

from app.alerting.ticket_config import REDACTED, redact_ticket_config, restore_ticket_config
from app.gateway.routers.alerts import AlertSourceResponse


def source_config():
    return {"ticket": {"webhook_url": "https://tickets.example/create", "headers": {
        "Authorization": "Bearer private-secret", "X-Custom": "another-secret",
    }}, "analysis_trigger": {"enabled": True}}


def test_response_model_redacts_headers_without_mutating_stored_configuration():
    config = source_config()
    before = deepcopy(config)
    response = AlertSourceResponse(id="source-1", name="monitor", type="webhook", status="active",
                                   auth_mode="none", config_json=config, created_at="2026-10-08")
    assert "private-secret" not in response.model_dump_json()
    assert "another-secret" not in response.model_dump_json()
    assert response.config_json["ticket"]["headers"] == {"Authorization": REDACTED, "X-Custom": REDACTED}
    assert config == before
    assert response.config_json["analysis_trigger"]["enabled"] is True


@pytest.mark.parametrize("url", ["https://user:password@tickets.example/create",
                                 "https://tickets.example/create?token=private-secret",
                                 "https://tickets.example/create#private-secret"])
def test_response_hides_url_credentials_and_roundtrip_preserves_them(url):
    config = source_config()
    config["ticket"]["webhook_url"] = url
    redacted = redact_ticket_config(config)
    assert redacted["ticket"]["webhook_url"] == REDACTED
    assert restore_ticket_config(redacted, config) == config


def test_same_source_roundtrip_preserves_credentials_and_allows_explicit_replacement():
    stored = source_config()
    incoming = redact_ticket_config(stored)
    incoming["ticket"]["headers"]["X-Custom"] = "replacement"
    restored = restore_ticket_config(incoming, stored)
    assert restored["ticket"]["headers"]["Authorization"] == "Bearer private-secret"
    assert restored["ticket"]["headers"]["X-Custom"] == "replacement"
    assert incoming["ticket"]["headers"]["Authorization"] == REDACTED
    incoming["ticket"]["headers"] = {}
    assert restore_ticket_config(incoming, stored)["ticket"]["headers"] == {}


def test_unknown_placeholders_are_rejected_instead_of_stored():
    with pytest.raises(ValueError, match="no stored value"):
        restore_ticket_config({"ticket": {"headers": {"Authorization": REDACTED}}})
    with pytest.raises(ValueError, match="no stored value"):
        restore_ticket_config({"ticket": {"webhook_url": REDACTED}})


def test_destination_change_cannot_forward_existing_credentials():
    stored = source_config()
    incoming = redact_ticket_config(stored)
    incoming["ticket"]["webhook_url"] = "https://another.example/create"
    with pytest.raises(ValueError, match="destination changed"):
        restore_ticket_config(incoming, stored)


@pytest.mark.anyio
async def test_source_routes_redact_and_preserve_same_tenant_credentials(tmp_path):
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession
    from starlette.requests import Request

    from app.gateway.routers.alerts import (
        AlertSourceCreate,
        AlertSourceUpdate,
        create_alert_source,
        list_alert_sources,
        update_alert_source,
    )
    from app.models.alerting import AlertSource

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'source-config.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: AlertSource.__table__.create(conn))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    request = Request({"type": "http"})
    request.state.tenant_id = "tenant-a"
    request.state.tenant_role = "admin"
    request.state.user_id = "admin-a"
    try:
        async with factory() as session:
            created = await create_alert_source(AlertSourceCreate(name="monitor", config_json=source_config()), request, session)
            assert "private-secret" not in created.model_dump_json()
            listed = await list_alert_sources(request, session)
            assert len(listed) == 1 and "private-secret" not in listed[0].model_dump_json()
            updated = await update_alert_source(created.id, AlertSourceUpdate(config_json=created.config_json), request, session)
            assert "private-secret" not in updated.model_dump_json()
            source = await session.get(AlertSource, created.id)
            assert source.config_json["ticket"]["headers"]["Authorization"] == "Bearer private-secret"
            request.state.tenant_id = "tenant-b"
            with pytest.raises(HTTPException) as exc:
                await update_alert_source(created.id, AlertSourceUpdate(config_json=created.config_json), request, session)
            assert exc.value.status_code == 404
            assert await list_alert_sources(request, session) == []
    finally:
        await engine.dispose()
