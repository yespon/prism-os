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
