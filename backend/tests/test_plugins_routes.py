"""Test /api/plugins endpoint."""
from fastapi.testclient import TestClient


def test_plugins_list_returns_all_definitions():
    """GET /api/plugins should return all plugin definitions with enabled state."""
    from fastapi import FastAPI

    from app.gateway.routers.plugins import router
    from app.plugins.registry import PLUGIN_DEFINITIONS

    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)
    resp = client.get("/api/plugins")
    assert resp.status_code == 200

    data = resp.json()
    assert "plugins" in data
    keys = {p["key"] for p in data["plugins"]}
    assert keys == set(PLUGIN_DEFINITIONS.keys())
    for p in data["plugins"]:
        assert "enabled" in p
        assert "frontendNavIds" in p
        assert p["enabled"] is True  # default


def test_plugins_respect_config():
    """When plugin is disabled, enabled should be false."""
    from app.gateway.config import GatewayConfig, set_gateway_config

    cfg = GatewayConfig(plugins={"ops-alerting": {"enabled": False}})
    set_gateway_config(cfg)

    from fastapi import FastAPI

    from app.gateway.routers.plugins import router

    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)
    resp = client.get("/api/plugins")
    assert resp.status_code == 200

    alerting = next(p for p in resp.json()["plugins"] if p["key"] == "ops-alerting")
    assert alerting["enabled"] is False