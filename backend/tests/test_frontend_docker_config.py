from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_docker_build_excludes_local_frontend_env_file() -> None:
    dockerignore = (REPO_ROOT / ".dockerignore").read_text()

    assert "frontend/.env" in dockerignore or "**/.env" in dockerignore


def test_frontend_production_build_accepts_explicit_public_api_urls() -> None:
    dockerfile = (REPO_ROOT / "frontend" / "Dockerfile").read_text()
    compose = (REPO_ROOT / "docker" / "docker-compose.yaml").read_text()

    assert "ARG NEXT_PUBLIC_BACKEND_BASE_URL" in dockerfile
    assert "ARG NEXT_PUBLIC_LANGGRAPH_BASE_URL" in dockerfile
    assert "NEXT_PUBLIC_BACKEND_BASE_URL:" in compose
    assert "NEXT_PUBLIC_LANGGRAPH_BASE_URL:" in compose
