"""Ticket provider — creates external tickets for incidents.

Supports:
  - Generic webhook: POST incident data to a configurable URL
  - Future: Jira, Feishu Bitable, DingTalk, etc.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.alerting.ticket_http_privacy import private_ticket_http
from app.alerting.ticket_secrets import resolve_ticket_material
from app.models.alerting import Incident

logger = logging.getLogger(__name__)


@dataclass
class TicketResult:
    ticket_id: str
    ticket_url: str | None
    provider: str


async def create_ticket(
    incident: Incident,
    ticket_config: dict[str, Any],
    signals_data: list[dict] | None = None,
    *,
    idempotency_key: str | None = None,
    source_id: str | None = None,
    before_send: Callable[[], Awaitable[None]] | None = None,
) -> TicketResult:
    """Create an external ticket for an incident.

    Args:
        incident: The incident to create a ticket for.
        ticket_config: Ticket configuration from AlertSource.config_json.ticket.
            Expected format:
            {
                "provider": "webhook",
                "webhook_url": "https://...",
                "headers": {"Authorization": "Bearer xxx"},
                "template": { ... }  # optional custom JSON body template
            }
        signals_data: Optional list of signal dicts for additional context.

    Returns:
        TicketResult with ticket_id, ticket_url, and provider name.
    """
    provider = ticket_config.get("provider", "webhook")

    if provider == "webhook":
        return await _create_webhook_ticket(incident, ticket_config, signals_data, idempotency_key=idempotency_key, source_id=source_id, before_send=before_send)
    else:
        raise ValueError(f"Unsupported ticket provider: {provider}")


def render_ticket_payload(
    incident: Incident,
    ticket_config: dict[str, Any],
    signals_data: list[dict] | None = None,
) -> dict[str, Any]:
    template = ticket_config.get("template")
    return (
        _render_template(template, incident, signals_data)
        if template else _default_ticket_payload(incident, signals_data)
    )


async def _create_webhook_ticket(
    incident: Incident,
    ticket_config: dict[str, Any],
    signals_data: list[dict] | None = None,
    *,
    idempotency_key: str | None = None,
    source_id: str | None = None,
    before_send: Callable[[], Awaitable[None]] | None = None,
) -> TicketResult:
    """Create a ticket via generic webhook (POST JSON)."""
    payload = render_ticket_payload(incident, ticket_config, signals_data)
    material = None
    async with httpx.AsyncClient(timeout=30) as client:
        if before_send is not None:
            await before_send()
        # Resolve after client setup and the last policy/identity recheck.
        material = await resolve_ticket_material(incident.tenant_id, source_id, ticket_config)
        webhook_url = material.webhook_url if material else ticket_config.get("webhook_url", "")
        if not webhook_url:
            raise ValueError("ticket.webhook_url is required for webhook provider")
        headers = {"Content-Type": "application/json", **(material.headers if material else ticket_config.get("headers", {}))}
        if idempotency_key is not None:
            headers = {name: value for name, value in headers.items() if name.lower() != "idempotency-key"}
            headers["Idempotency-Key"] = idempotency_key
        try:
            with private_ticket_http():
                response = await client.post(webhook_url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("ticket: webhook request failed (%s)", type(exc).__name__)
            # HTTP errors contain the credential-bearing request URL.
            raise RuntimeError("Ticket creation failed") from None

    # Try to extract ticket_id and URL from response
    ticket_id = ""
    ticket_url = ""
    try:
        resp_data = response.json()
        ticket_id = str(resp_data.get("id") or resp_data.get("key") or resp_data.get("ticket_id") or "")
        ticket_url = str(resp_data.get("url") or resp_data.get("ticket_url") or resp_data.get("self") or "")
    except Exception:
        # If response is not JSON or doesn't have expected fields, use empty strings
        pass

    if material is not None:
        # A provider may echo request credentials in returned IDs or URLs.
        # Discard such values before they reach incident/audit persistence.
        from urllib.parse import parse_qsl, unquote, urlsplit

        url = urlsplit(material.webhook_url)
        protected = [material.webhook_url, unquote(url.path)]
        protected.extend(part for part in unquote(url.path).split("/") if part)
        protected.extend(value for _, value in parse_qsl(url.query))
        for name, value in material.headers.items():
            protected.append(value)
            if name.lower() in {"authorization", "proxy-authorization"}:
                protected.append(value.split(" ", 1)[-1])
        protected = [value for value in protected if value and value != "/"]
        if any(value in unquote(ticket_id) for value in protected):
            ticket_id = ""
        if any(value in unquote(ticket_url) for value in protected):
            ticket_url = ""

    if not ticket_id:
        ticket_id = f"inc-{incident.incident_key}"

    logger.info(
        "ticket: created for incident=%s via webhook: ticket_id=%s",
        incident.incident_key, ticket_id,
    )
    return TicketResult(ticket_id=ticket_id, ticket_url=ticket_url or None, provider="webhook")


def _default_ticket_payload(
    incident: Incident,
    signals_data: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a default ticket payload from incident data."""
    return {
        "title": incident.title or "Untitled Incident",
        "description": incident.summary or "",
        "severity": incident.severity,
        "status": incident.status,
        "service": incident.service,
        "environment": incident.environment,
        "incident_key": incident.incident_key,
        "signal_count": incident.signal_count,
        "first_seen_at": incident.first_seen_at.isoformat() if incident.first_seen_at else None,
        "last_seen_at": incident.last_seen_at.isoformat() if incident.last_seen_at else None,
        "ai_summary": incident.ai_summary,
        "ai_impact": incident.ai_impact,
        "ai_suggestion": incident.ai_suggestion,
        "diagnosis_result": incident.diagnosis_result,
        "signals": signals_data or [],
    }


def _render_template(
    template: dict[str, Any],
    incident: Incident,
    signals_data: list[dict] | None = None,
) -> dict[str, Any]:
    """Render a user-provided template with incident data.

    Supports simple variable substitution:
      {{ incident.title }} → incident.title
      {{ incident.severity }} → incident.severity
      {{ incident.ai_summary }} → incident.ai_summary
    """
    import re

    context = {
        "incident.title": incident.title or "",
        "incident.summary": incident.summary or "",
        "incident.severity": incident.severity,
        "incident.status": incident.status,
        "incident.service": incident.service or "",
        "incident.environment": incident.environment or "",
        "incident.incident_key": incident.incident_key,
        "incident.signal_count": str(incident.signal_count),
        "incident.ai_summary": incident.ai_summary or "",
        "incident.ai_impact": incident.ai_impact or "",
        "incident.ai_suggestion": incident.ai_suggestion or "",
        "incident.diagnosis_result": incident.diagnosis_result or "",
    }

    def _substitute(value: Any) -> Any:
        if isinstance(value, str):
            def _replace(m: re.Match) -> str:
                key = m.group(1).strip()
                return context.get(key, m.group(0))
            return re.sub(r"\{\{\s*([^}]+)\s*\}\}", _replace, value)
        elif isinstance(value, dict):
            return {k: _substitute(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [_substitute(v) for v in value]
        return value

    return _substitute(template)


async def create_ticket_webhook(*, incident: Incident, session) -> dict | None:
    """Compatibility entry for rule auto_ticket; caller owns the transaction."""
    from uuid import uuid4

    from app.alerting.governed_ticket import resolve_ticket_target
    from app.models.alerting import IncidentAction

    if incident.ticket_id:
        return None
    target = await resolve_ticket_target(incident.tenant_id, incident.id, session=session)
    result = await create_ticket(incident, target.config, target.signals, source_id=target.source_id)
    incident.ticket_id, incident.ticket_url, incident.ticket_provider = result.ticket_id, result.ticket_url, result.provider
    session.add(incident)
    session.add(IncidentAction(id=str(uuid4()), tenant_id=incident.tenant_id, incident_id=incident.id,
                              actor_id="system", action_type="ticket_created", action_payload={
                                  "ticket_id": result.ticket_id, "ticket_url": result.ticket_url,
                                  "provider": result.provider, "origin": "auto_ticket"}))
    return {"ticket_id": result.ticket_id, "ticket_url": result.ticket_url, "provider": result.provider}
