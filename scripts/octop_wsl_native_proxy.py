"""Loopback-only reverse proxy for the owned native WSL browser test profile."""

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from starlette.routing import Route

HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}


async def forward(request):
    upstream = "http://127.0.0.1:18031" if request.url.path.startswith("/api/") or request.url.path == "/health" else "http://127.0.0.1:18035"
    headers = {key: value for key, value in request.headers.items() if key.lower() not in HOP_HEADERS | {"host"}}
    client = httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(240, connect=5))
    response = None
    try:
        outbound = client.build_request(request.method, upstream + request.url.path, params=request.query_params, headers=headers, content=await request.body())
        response = await client.send(outbound, stream=True)
    except BaseException:
        await client.aclose()
        raise

    async def close():
        await response.aclose()
        await client.aclose()

    async def chunks():
        try:
            async for data in response.aiter_raw():
                yield data
        finally:
            await close()

    return StreamingResponse(chunks(), background=BackgroundTask(close), status_code=response.status_code, headers={key: value for key, value in response.headers.items() if key.lower() not in HOP_HEADERS})


app = Starlette(routes=[Route("/{path:path}", forward, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])])
