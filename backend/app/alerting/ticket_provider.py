"""Ticket provider — creates external tickets for incidents.

Supports:
  - Generic webhook: POST incident data to a configurable URL
  - Future: Jira, Feishu Bitable, DingTalk, etc.
"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

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
        return await _create_webhook_ticket(incident, ticket_config, signals_data, idempotency_key=idempotency_key)
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
) -> TicketResult:
    """Create a ticket via generic webhook (POST JSON)."""
    webhook_url = ticket_config.get("webhook_url", "")
    if not webhook_url:
        raise ValueError("ticket.webhook_url is required for webhook provider")

    headers = {"Content-Type": "application/json", **ticket_config.get("headers", {})}
    if idempotency_key is not None:
        headers = {name: value for name, value in headers.items() if name.lower() != "idempotency-key"}
        headers["Idempotency-Key"] = idempotency_key
    payload = render_ticket_payload(incident, ticket_config, signals_data)

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(
                webhook_url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("ticket: webhook request failed (%s)", type(e).__name__)
            raise RuntimeError("Ticket creation failed") from e

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
