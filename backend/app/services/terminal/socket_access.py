"""Per-connection current session, independent from the original shared PTY lease."""

import asyncio

from app.gateway.session_authorization import SessionAuthorityUnavailable


class CurrentTerminalSocket:
    def __init__(self, socket, verify_session, verify_terminal):
        self._socket = socket
        self._verify_session = verify_session
        self._verify_terminal = verify_terminal
        self._lock = asyncio.Lock()
        self._closed = False

    async def _authorize(self):
        if self._closed:
            raise SessionAuthorityUnavailable("Terminal connection unavailable")
        self._verify_session()
        await self._verify_terminal()
        self._verify_session()

    async def authorize(self):
        async with self._lock:
            await self._authorize()

    async def send_text(self, data):
        async with self._lock:
            pending = None
            try:
                await self._authorize()
                pending = asyncio.create_task(self._socket.send_text(data))
                while not pending.done():
                    await asyncio.wait({pending}, timeout=.25)
                    await self._authorize()
                pending.result()
            except Exception:
                if pending is not None:
                    if not pending.done():
                        pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                await self._close()
                raise
            finally:
                if pending is not None:
                    if not pending.done():
                        pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)

    async def _close(self):
        if not self._closed:
            self._closed = True
            try:
                await asyncio.wait_for(self._socket.close(code=1008), timeout=1)
            except Exception:
                pass  # Peer may already have disconnected; never expose bearer material.

    async def close(self):
        async with self._lock:
            await self._close()
