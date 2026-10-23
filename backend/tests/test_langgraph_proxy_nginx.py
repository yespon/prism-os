from pathlib import Path

import pytest


@pytest.mark.parametrize("name", ["nginx.conf", "nginx.local.conf"])
def test_browser_langgraph_route_targets_gateway(name) -> None:
    root = Path(__file__).resolve().parents[2]
    config = (root / "docker" / "nginx" / name).read_text()
    route = config.split("location /api/langgraph/ {", 1)[1].split("}", 1)[0]
    assert "proxy_pass http://gateway;" in route
    assert "proxy_pass http://langgraph;" not in route
    assert "rewrite ^/api/langgraph" not in route


@pytest.mark.parametrize("name", ["nginx.conf", "nginx.local.conf"])
def test_gateway_api_fallback_preserves_only_the_two_next_terminal_handlers(name):
    root = Path(__file__).resolve().parents[2]
    config = (root / "docker" / "nginx" / name).read_text()
    fallback = config.split("location /api/ {", 1)[1].split("}", 1)[0]
    assert "proxy_pass http://gateway;" in fallback
    assert "proxy_buffering off;" in fallback
    assert "proxy_read_timeout 600s;" in fallback
    for path in ["/api/terminal/chat", "/api/terminal/chat/approve"]:
        route = config.split(f"location = {path} {{", 1)[1].split("}", 1)[0]
        assert "proxy_pass http://frontend;" in route
