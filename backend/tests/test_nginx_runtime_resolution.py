from pathlib import Path


NGINX_CONFIG = (
    Path(__file__).resolve().parents[2] / "docker" / "nginx" / "nginx.conf"
)


def test_docker_service_upstreams_refresh_after_container_recreation():
    config = NGINX_CONFIG.read_text()

    for service, port in (("gateway", 8001), ("langgraph", 2024), ("frontend", 3000)):
        assert f"upstream {service} {{" in config
        assert f"zone {service} 64k;" in config
        assert f"server {service}:{port} resolve;" in config
