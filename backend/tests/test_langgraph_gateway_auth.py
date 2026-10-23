from fastapi.testclient import TestClient

from app.gateway.app import create_app


def test_browser_langgraph_route_requires_gateway_session() -> None:
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/langgraph/threads/thread-1")
    assert response.status_code == 401
