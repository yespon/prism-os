"""Original session expiry and transient response-delivery leases; no persisted token."""

import asyncio
from datetime import UTC, datetime


class SessionAuthorityUnavailable(RuntimeError):
    pass


def session_expiry(raw) -> datetime | None:
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, str) and raw:
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    # Original database timestamps are UTC, including legacy naive SQL values.
    try:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


async def current_session_body(iterator, verify, *, interval=0.25):
    """Stop local delivery on logout/expiry; remote effects remain unconfirmed."""
    pending = None
    try:
        while True:
            verify()
            pending = asyncio.ensure_future(anext(iterator))
            while not pending.done():
                await asyncio.wait({pending}, timeout=interval)
                verify()
            try:
                value = pending.result()
            except StopAsyncIteration:
                return
            verify()
            yield value
    finally:
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()

def session_token(request) -> str | None:
    """Use the original HTTP token priority for HTTP and WebSocket consumers."""
    header = request.headers.get("Authorization")
    if header and header.startswith("Bearer "):
        value = header.split(" ", 1)[1].strip()
        if value:
            return value
    return request.query_params.get("token") or request.cookies.get("better-auth.session_token") or request.cookies.get("__Secure-better-auth.session_token")
