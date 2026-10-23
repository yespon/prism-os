"""Owned native browser routes preserve the production terminal BFF split."""

import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[2] / "scripts/octop_wsl_native_proxy.py"
spec = importlib.util.spec_from_file_location("native_browser_proxy_actual", path)
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


@pytest.mark.parametrize("path", ["/api/terminal/chat", "/api/terminal/chat/approve", "/workspace/terminal"])
def test_terminal_ui_and_pages_use_owned_frontend(path, monkeypatch):
    monkeypatch.setenv("PRISMOS_NATIVE_FRONTEND_URL", "http://127.0.0.1:18037")
    assert proxy.upstream_for_path(path) == "http://127.0.0.1:18037"


@pytest.mark.parametrize("path", ["/api/v1/terminal/invoke", "/api/v1/terminal/chats", "/api/auth/login", "/health"])
def test_native_backend_routes_stay_on_original_gateway(path):
    assert proxy.upstream_for_path(path) == "http://127.0.0.1:18031"


def test_native_proxy_refuses_external_frontend_origin(monkeypatch):
    monkeypatch.setenv("PRISMOS_NATIVE_FRONTEND_URL", "https://unowned.invalid")
    with pytest.raises(ValueError):
        proxy.upstream_for_path("/api/terminal/chat")
