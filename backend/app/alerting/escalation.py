"""
Escalation Engine — evaluates escalation rules against incidents and triggers actions.

Supported conditions:
- severity: critical, major, warning, info
- min_duration_minutes: incident has been firing for >= N minutes without acknowledgment
- service: specific service name
- source: specific alert source

Supported actions:
- notify_channel: send notification to a specific IM channel
- auto_assign: assign to a specific user
- auto_ticket: create an external ticket
- escalate_severity: bump severity to next level
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.alerting import AlertRule, Incident

logger = logging.getLogger(__name__)

SEVERITY_LEVELS = {"info": 0, "warning": 1, "minor": 2, "major": 3, "critical": 4}
SEVERITY_BUMP = {"info": "warning", "warning": "minor", "minor": "major", "major": "critical"}


def _matches_conditions(incident: Incident, rule: AlertRule) -> bool:
    """Check if an incident matches all conditions defined in an escalation rule."""
    conditions = rule.condition_json or {}

    # Severity match
    severities: list[str] = conditions.get("severity", [])
    if severities and incident.severity not in severities:
        return False

    # Service match
    service: str | None = conditions.get("service")
    if service and incident.service != service:
        return False

    # Source match
    source: str | None = conditions.get("source")
    if source and incident.source != source:
        return False

    # Min duration (unacknowledged) match
    min_duration: int | None = conditions.get("min_duration_minutes")
    if min_duration:
        if not incident.first_seen_at:
            return False
        elapsed = (datetime.now(UTC) - incident.first_seen_at).total_seconds() / 60
        if elapsed < min_duration:
            return False

    return True


async def evaluate_escalation_rules(
    incident: Incident,
    session: AsyncSession,
) -> list[AlertRule]:
    """Evaluate all active escalation rules against an incident.

    Returns the list of matching rules that should be applied.
    Only returns rules that haven't already been applied to this incident.
    """
    rules_result = await session.exec(
        select(AlertRule).where(
            AlertRule.tenant_id == incident.tenant_id,
            AlertRule.rule_type == "escalation",
            AlertRule.enabled == True,  # noqa: E712
        )
    )
    rules = rules_result.all()

    matching: list[AlertRule] = []
    for rule in rules:
        if _matches_conditions(incident, rule):
            matching.append(rule)

    return matching


async def apply_escalation_actions(
    incident: Incident,
    matching_rules: list[AlertRule],
    session: AsyncSession,
) -> list[dict]:
    """Apply escalation actions from matching rules.

    Returns a list of actions that were taken.
    """
    results: list[dict] = []
    import uuid

    from app.models.alerting import IncidentAction

    for rule in matching_rules:
        actions = rule.action_json or {}
        action_type = actions.get("action", "notify_channel")

        if action_type == "escalate_severity":
            current_level = SEVERITY_LEVELS.get(incident.severity, 0)
            new_severity = SEVERITY_BUMP.get(incident.severity)
            if new_severity and SEVERITY_LEVELS[new_severity] > current_level:
                old_severity = incident.severity
                incident.severity = new_severity
                session.add(incident)

                # Record escalation action
                action_record = IncidentAction(
                    id=str(uuid.uuid4()),
                    tenant_id=incident.tenant_id,
                    incident_id=incident.id,
                    action_type="escalation",
                    actor_id="system",
                    action_payload={
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "from_severity": old_severity,
                        "to_severity": new_severity,
                    },
                )
                session.add(action_record)
                results.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "action": "escalate_severity",
                    "from": old_severity,
                    "to": new_severity,
                })
                logger.info(
                    "Escalation: incident %s severity bumped from %s to %s (rule: %s)",
                    incident.id, old_severity, new_severity, rule.name,
                )

        elif action_type == "notify_channel":
            # Channel notification is handled by the caller (notify module)
            results.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "action": "notify_channel",
                "channel": actions.get("channel", "default"),
            })

        elif action_type == "auto_assign":
            assign_user = actions.get("user_id")
            if assign_user:
                incident.owner_user_id = assign_user
                session.add(incident)

                action_record = IncidentAction(
                    id=str(uuid.uuid4()),
                    tenant_id=incident.tenant_id,
                    incident_id=incident.id,
                    action_type="assigned",
                    actor_id="system",
                    action_payload={
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "owner_user_id": assign_user,
                        "reason": "auto-escalation",
                    },
                )
                session.add(action_record)
                results.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "action": "auto_assign",
                    "user_id": assign_user,
                })
                logger.info(
                    "Escalation: incident %s auto-assigned to %s (rule: %s)",
                    incident.id, assign_user, rule.name,
                )

        elif action_type == "auto_ticket":
            from app.alerting.ticket_provider import create_ticket_webhook

            ticket_result = await create_ticket_webhook(
                incident=incident,
                session=session,
            )
            if ticket_result:
                results.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "action": "auto_ticket",
                    "ticket_id": ticket_result.get("ticket_id"),
                })
                logger.info(
                    "Escalation: incident %s auto-ticket created (rule: %s)",
                    incident.id, rule.name,
                )

    await session.commit()
    return results
