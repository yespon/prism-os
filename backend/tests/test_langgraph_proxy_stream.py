import httpx
import pytest
from fastapi import FastAPI, Request
from test_langgraph_proxy import proxy_setup as proxy_fixture
from test_langgraph_proxy import real_forward

from app.gateway.routers import langgraph_proxy
from app.platform.execution.trust import ThreadBindingRepository

proxy_setup = proxy_fixture


@pytest.mark.anyio
async def test_proxy_preserves_sse_and_run_location(monkeypatch, proxy_setup) -> None:
    _, _, factory = proxy_setup
    await ThreadBindingRepository(factory).create("thread-1", "tenant-a", "user-1")
    closed = []

    class FakeClient:
        async def aclose(self):
            closed.append(True)

    class FakeStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"event: metadata\ndata: {}\n\n"

    async def upstream(method, path, body, query, **_kwargs):
        assert (method, path, query) == ("POST", "threads/thread-1/runs/stream", "")
        assert body == b'{"input":"hello"}'
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream", "content-location": "/threads/thread-1/runs/run-1"},
            stream=FakeStream(),
        ), FakeClient()

    monkeypatch.setattr(langgraph_proxy, "_upstream", upstream)
    app = FastAPI()

    @app.post("/relay")
    async def relay(request: Request):
        request.state.tenant_id = "tenant-a"
        request.state.user_id = "user-1"
        return await real_forward("POST", "threads/thread-1/runs/stream", {"input": "hello"}, request)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/relay")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["content-location"] == "/threads/thread-1/runs/run-1"
    assert response.content == b"event: metadata\ndata: {}\n\n"
    assert closed == [True]
