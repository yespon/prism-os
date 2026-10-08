"""Keep legacy ticket credentials out of alert source API responses."""

from copy import deepcopy
from urllib.parse import urlsplit

REDACTED = "[REDACTED]"


def redact_ticket_config(config: dict) -> dict:
    result = deepcopy(config)
    ticket = result.get("ticket")
    if not isinstance(ticket, dict):
        return result
    headers = ticket.get("headers")
    if isinstance(headers, dict):
        ticket["headers"] = {name: REDACTED for name in headers}
    url = ticket.get("webhook_url")
    if isinstance(url, str):
        try:
            parsed = urlsplit(url)
            if "@" in parsed.netloc or parsed.query or parsed.fragment:
                ticket["webhook_url"] = REDACTED
        except ValueError:
            ticket["webhook_url"] = REDACTED
    return result


def restore_ticket_config(config: dict, previous: dict | None = None) -> dict:
    """Resolve response placeholders against the same source's stored config."""
    result = deepcopy(config)
    ticket = result.get("ticket")
    if not isinstance(ticket, dict):
        return result
    old_ticket = (previous or {}).get("ticket", {})
    if not isinstance(old_ticket, dict):
        old_ticket = {}
    headers = ticket.get("headers")
    old_headers = old_ticket.get("headers", {})
    if not isinstance(old_headers, dict):
        old_headers = {}
    if isinstance(headers, dict):
        if REDACTED in headers.values() and ticket.get("webhook_url") not in (REDACTED, old_ticket.get("webhook_url")):
            raise ValueError("ticket destination changed; replace or remove stored headers")
        for name, value in headers.items():
            if value == REDACTED:
                if name not in old_headers:
                    raise ValueError("redacted ticket header has no stored value")
                headers[name] = old_headers[name]
    if ticket.get("webhook_url") == REDACTED:
        if not old_ticket.get("webhook_url"):
            raise ValueError("redacted ticket URL has no stored value")
        ticket["webhook_url"] = old_ticket["webhook_url"]
    return result
