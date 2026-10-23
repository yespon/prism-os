"""Prevent HTTP client logs from exposing source-scoped webhook credentials."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

_private_request = ContextVar("ticket_private_http_request", default=False)


class _PrivateTicketFilter(logging.Filter):
    def filter(self, record):
        if _private_request.get():
            record.msg = "Ticket provider HTTP activity"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


_filter = _PrivateTicketFilter()


@contextmanager
def private_ticket_http():
    # Client construction imports the selected transport before this context.
    # Filters remain installed but only alter this request's context, so other
    # concurrent HTTP traffic retains its diagnostics.
    for name, instance in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(instance, logging.Logger) and (name == "httpx" or name.startswith("httpcore")):
            if _filter not in instance.filters:
                instance.addFilter(_filter)
    token = _private_request.set(True)
    try:
        yield
    finally:
        _private_request.reset(token)
