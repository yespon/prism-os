"""Feature-gated Agent ticket Action behind the trusted diagnosis Tool."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal
from urllib.parse import urlsplit

from sqlmodel import select

from app.alerting.legacy_audit_delivery import LegacyAuditDeliveryService
from app.alerting.ticket_provider import TicketResult, create_ticket, render_ticket_payload
from app.alerting.ticket_secrets import check_ticket_material, ticket_secret_ref
from app.models.alerting import AlertSource, Incident, IncidentSignalLink, RawAlert, Signal
from app.platform.approval.repository import ApprovalRepository
from app.platform.approval.service import ApprovalService
from app.platform.contracts import ActionContextInput, AuditEvent, ExecutionEnvelope, PolicyRequest, hash_action_context, stable_platform_id
from app.platform.policy.evaluator import PolicyConfiguration
from app.platform.policy.service import PolicyService
from app.platform.submission.repository import ActionSubmissionRepository, SubmissionFact
from deerflow.database.session import get_session_factory
from deerflow.database.tenant_service import get_membership, get_tenant


@dataclass(frozen=True)
class TicketTarget:
    incident: Incident
    config: dict[str, Any]
    signals: list[dict[str, Any]]
    source_id: str | None = None


@dataclass(frozen=True)
class TicketActionOutcome:
    status: Literal["denied", "awaiting_approval", "rejected", "expired", "submitted", "unknown"]
    decision_id: str
    approval_id: str | None = None
    idempotency_key: str | None = None
    ticket_id: str | None = None
    needs_reconciliation: bool = False


TargetResolver = Callable[[str, str], Awaitable[TicketTarget]]
PermissionCheck = Callable[[str, str], Awaitable[bool]]
TicketSender = Callable[..., Awaitable[TicketResult]]
TicketLinker = Callable[[str, str, TicketResult], Awaitable[None]]


async def resolve_ticket_target(tenant_id: str, incident_id: str, *, session=None) -> TicketTarget:
    """Resolve only tenant-scoped signals and active Source; never decrypt here."""
    if session is not None:
        return await _resolve_in_session(session, tenant_id, incident_id)
    async with get_session_factory()() as value:
        return await _resolve_in_session(value, tenant_id, incident_id)


async def _resolve_in_session(session, tenant_id: str, incident_id: str) -> TicketTarget:
    incident = (await session.exec(select(Incident).where(Incident.tenant_id == tenant_id, Incident.id == incident_id))).first()
    if incident is None:
        raise ValueError("incident unavailable")
    links = (await session.exec(select(IncidentSignalLink).where(
        IncidentSignalLink.tenant_id == tenant_id, IncidentSignalLink.incident_id == incident_id,
    ))).all()
    signal_ids = [link.signal_id for link in links]
    signals = (await session.exec(select(Signal).where(
        Signal.tenant_id == tenant_id, Signal.id.in_(signal_ids),
    ).order_by(Signal.id))).all() if signal_ids else []
    raw_ids = {signal.raw_alert_id for signal in signals if signal.raw_alert_id}
    raw_alerts = (await session.exec(select(RawAlert).where(
        RawAlert.tenant_id == tenant_id, RawAlert.id.in_(raw_ids),
    ))).all() if raw_ids else []
    source_ids = {alert.source_id for alert in raw_alerts if alert.source_id}
    sources = (await session.exec(select(AlertSource).where(
        AlertSource.tenant_id == tenant_id, AlertSource.status == "active", AlertSource.id.in_(source_ids),
    ).order_by(AlertSource.id))).all() if source_ids else []
    selected_source = next((source for source in sources if (source.config_json or {}).get("ticket")), None)
    ticket_config = (selected_source.config_json or {}).get("ticket") if selected_source else None
    if not isinstance(ticket_config, dict) or ticket_config.get("provider", "webhook") != "webhook" or not (ticket_config.get("webhook_url") or "secret_ref" in ticket_config):
        raise ValueError("incident has no configured webhook ticket provider")
    summaries = [{"title": signal.title, "severity": signal.severity,
                  "source": signal.source, "status": signal.status} for signal in signals]
    return TicketTarget(incident=incident, config=ticket_config, signals=summaries, source_id=selected_source.id)

async def active_requester(tenant_id: str, user_id: str) -> bool:
    return await get_tenant(tenant_id) is not None and await get_membership(user_id, tenant_id) is not None


async def link_incident_ticket(tenant_id: str, incident_id: str, result: TicketResult) -> None:
    async with get_session_factory()() as session:
        incident = (await session.exec(select(Incident).where(Incident.tenant_id == tenant_id, Incident.id == incident_id))).first()
        if incident is None or (incident.ticket_id and incident.ticket_id != result.ticket_id):
            raise ValueError("incident ticket linkage changed")
        incident.ticket_id = result.ticket_id
        incident.ticket_url = result.ticket_url
        incident.ticket_provider = result.provider
        session.add(incident)
        await session.commit()


class TicketActionAdapter:
    def __init__(
        self,
        *,
        enabled_tenants: frozenset[str] = frozenset(),
        configuration: PolicyConfiguration | None = None,
        policy: PolicyService | None = None,
        approvals: ApprovalRepository | None = None,
        approval_service: ApprovalService | None = None,
        submissions: ActionSubmissionRepository | None = None,
        deliveries: LegacyAuditDeliveryService | None = None,
        resolve_target: TargetResolver = resolve_ticket_target,
        check_permission: PermissionCheck = active_requester,
        send_ticket: TicketSender = create_ticket,
        link_ticket: TicketLinker = link_incident_ticket,
        execution_authorizer: Callable[..., Awaitable[None]] | None = None,
    ) -> None:
        self._enabled_tenants = enabled_tenants
        self._configuration = configuration
        self._policy = policy or PolicyService()
        self._approvals = approvals or ApprovalRepository()
        self._approval_service = approval_service or ApprovalService()
        self._submissions = submissions or ActionSubmissionRepository()
        self._deliveries = deliveries or LegacyAuditDeliveryService(self._submissions._session_factory)
        self._resolve_target = resolve_target
        self._check_permission = check_permission
        self._send_ticket = send_ticket
        self._link_ticket = link_ticket
        self._execution_authorizer = execution_authorizer

    @staticmethod
    def _validate_destination(config: dict[str, Any], *, tenant_id: str | None = None, source_id: str | None = None) -> None:
        """The M1 canary may use only credential-free HTTPS webhooks."""
        if config.get("provider", "webhook") != "webhook":
            raise ValueError("governed ticket requires a webhook provider")
        if "secret_ref" in config:
            ticket_secret_ref(config, tenant_id, source_id)
            return
        url = config.get("webhook_url")
        if not isinstance(url, str):
            raise ValueError("governed ticket requires an HTTPS webhook URL")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or "@" in parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("governed ticket requires a credential-free HTTPS webhook URL")
        headers = config.get("headers", {})
        if not isinstance(headers, dict) or headers:
            raise ValueError("governed ticket does not accept inline webhook headers")

    @staticmethod
    def _request(execution: ExecutionEnvelope, request_id: str, target: TicketTarget, at: datetime) -> PolicyRequest:
        payload = render_ticket_payload(target.incident, target.config, target.signals)
        payload_hash = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        destination = {"provider": target.config.get("provider", "webhook"),
                       "webhook_url": target.config.get("webhook_url"),
                       "headers": target.config.get("headers", {})}
        if "secret_ref" in target.config:
            ref = ticket_secret_ref(target.config, execution.tenant_id, target.source_id)
            destination = {"provider": "webhook", "reference": ref.model_dump(mode="json"), "source_id": target.source_id}
        destination_hash = sha256(json.dumps(destination, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        context = ActionContextInput(
            tenant_id=execution.tenant_id, execution=execution, action="ticket.create",
            risk_class="side_effect", resource_id=target.incident.id,
            parameters={"incident_key": target.incident.incident_key,
                        "payload_sha256": payload_hash, "destination_sha256": destination_hash},
        )
        return PolicyRequest(
            tenant_id=execution.tenant_id, request_id=request_id, execution=execution,
            action="ticket.create", risk_class="side_effect", resource_id=target.incident.id,
            context_hash=hash_action_context(context), requested_at=at,
        )

    @staticmethod
    def _from_submission(fact: SubmissionFact) -> TicketActionOutcome:
        return TicketActionOutcome(
            status="submitted" if fact.status == "submitted" else "unknown",
            decision_id=fact.decision_id, approval_id=fact.approval_id,
            idempotency_key=fact.idempotency_key, ticket_id=fact.ticket_id,
        )

    async def execute(
        self, execution: ExecutionEnvelope, request_id: str, incident_id: str,
        *, at: datetime | None = None,
    ) -> TicketActionOutcome:
        """Execute only from trusted server scopes after rechecking live permissions."""
        if execution.tenant_id not in self._enabled_tenants:
            raise PermissionError("governed ticket Action is disabled for this tenant")
        actor = execution.actor
        if actor is None or actor.kind != "user" or execution.workload is None:
            raise PermissionError("trusted user and Agent workload required")
        if not await self._check_permission(execution.tenant_id, actor.id):
            raise PermissionError("requester is no longer authorized")
        if self._execution_authorizer is not None:
            await self._execution_authorizer(execution, self._submissions._session_factory)
        instant = at or datetime.now(UTC)
        target = await self._resolve_target(execution.tenant_id, incident_id)
        if target.incident.tenant_id != execution.tenant_id or target.incident.id != incident_id:
            raise PermissionError("incident tenant or identity changed")
        self._validate_destination(target.config, tenant_id=execution.tenant_id, source_id=target.source_id)
        request = self._request(execution, request_id, target, instant)
        decision = await self._policy.evaluate_and_record(request, self._configuration, at=instant)
        if decision.verdict == "deny":
            return TicketActionOutcome(status="denied", decision_id=decision.decision_id)
        existing = await self._submissions.get(decision.tenant_id, decision.decision_id)
        if existing is not None and existing.status in ("submitted", "unknown"):
            return replace(
                self._from_submission(existing),
                needs_reconciliation=existing.status == "submitted" and target.incident.ticket_id != existing.ticket_id,
            )
        approval_id = None
        if decision.verdict == "require_approval":
            found = await self._approvals.get_by_decision(decision.tenant_id, decision.decision_id)
            if found is None:
                raise ValueError("persisted Approval missing")
            approval_id = found[0].approval_id
            approval = await self._approval_service.get_for_user(
                decision.tenant_id, approval_id, actor.id, at=instant,
            )
            if approval.status in ("rejected", "expired"):
                return TicketActionOutcome(status=approval.status, decision_id=decision.decision_id, approval_id=approval_id)
            if instant >= decision.expires_at or instant >= approval.expires_at:
                return TicketActionOutcome(status="expired", decision_id=decision.decision_id, approval_id=approval_id)
            if approval.status == "pending":
                return TicketActionOutcome(status="awaiting_approval", decision_id=decision.decision_id, approval_id=approval_id)
            if approval.status != "approved":
                raise ValueError("consumed Approval has no submission fact")
        if target.incident.ticket_id:
            raise ValueError("incident already has a ticket")
        if not await self._check_permission(execution.tenant_id, actor.id):
            raise PermissionError("requester authorization changed")
        if self._execution_authorizer is not None:
            await self._execution_authorizer(execution, self._submissions._session_factory)
        current = await self._resolve_target(execution.tenant_id, incident_id)
        self._validate_destination(current.config, tenant_id=execution.tenant_id, source_id=current.source_id)
        if current.incident.ticket_id or self._request(execution, request_id, current, instant).context_hash != request.context_hash:
            raise ValueError("ticket Action context changed before submission")
        await check_ticket_material(execution.tenant_id, current.source_id, current.config)
        if approval_id is not None:
            await self._approval_service.consume_for_request(decision.tenant_id, approval_id, request, at=instant)
        fact = await self._submissions.prepare(decision, approval_id, at=instant)
        if fact.status in ("submitted", "unknown"):
            return replace(
                self._from_submission(fact),
                needs_reconciliation=fact.status == "submitted" and current.incident.ticket_id != fact.ticket_id,
            )
        if not await self._submissions.claim(decision.tenant_id, decision.decision_id, at=instant):
            latest = await self._submissions.get(decision.tenant_id, decision.decision_id)
            if latest is None:
                raise ValueError("submission fact disappeared")
            if latest.status not in ("submitted", "unknown"):
                raise ValueError("submission claim did not settle")
            return replace(
                self._from_submission(latest),
                needs_reconciliation=latest.status == "submitted" and current.incident.ticket_id != latest.ticket_id,
            )
        try:
            if self._execution_authorizer is not None:
                await self._execution_authorizer(execution, self._submissions._session_factory)
            arguments = {"idempotency_key": fact.idempotency_key}
            if "secret_ref" in current.config:
                async def before_send():
                    if self._execution_authorizer is not None:
                        await self._execution_authorizer(execution, self._submissions._session_factory)
                    if not await self._check_permission(execution.tenant_id, actor.id):
                        raise PermissionError("requester authorization changed")
                    final = await self._resolve_target(execution.tenant_id, incident_id)
                    self._validate_destination(final.config, tenant_id=execution.tenant_id, source_id=final.source_id)
                    if final.incident.ticket_id or self._request(execution, request_id, final, instant).context_hash != request.context_hash:
                        raise ValueError("ticket Action context changed before submission")

                arguments.update(source_id=current.source_id, before_send=before_send)
            ticket = await self._send_ticket(current.incident, current.config, current.signals, **arguments)
        except Exception:
            unknown_audit = AuditEvent(
                tenant_id=decision.tenant_id,
                event_id=stable_platform_id("event", "ticket-result-unknown", decision.decision_id),
                event_type="action.submission_unknown", action=decision.action,
                outcome="pending", severity="warning", execution=decision.execution,
                policy_decision_id=decision.decision_id, approval_id=approval_id,
                resource_id=decision.resource_id,
                payload={"reason_code": "provider_result_unknown"}, recorded_at=instant,
            )
            try:
                await self._submissions.record_unknown_result(
                    decision.tenant_id, decision.decision_id, unknown_audit,
                )
            except Exception:
                # Reservation remains unknown even if result Audit is unavailable.
                pass
            return TicketActionOutcome(
                status="unknown", decision_id=decision.decision_id,
                approval_id=approval_id, idempotency_key=fact.idempotency_key,
            )
        result_audit = AuditEvent(
            tenant_id=decision.tenant_id,
            event_id=stable_platform_id("event", "ticket-submitted", decision.decision_id),
            event_type="action.submitted", action=decision.action, outcome="succeeded",
            execution=decision.execution, policy_decision_id=decision.decision_id,
            approval_id=approval_id, resource_id=decision.resource_id,
            payload={"ticket_id": ticket.ticket_id, "provider": ticket.provider},
            recorded_at=instant,
        )
        try:
            submitted = await self._submissions.mark_submitted(
                decision.tenant_id, decision.decision_id, ticket_id=ticket.ticket_id,
                ticket_url=ticket.ticket_url, provider=ticket.provider, at=instant,
                result_audit=result_audit,
            )
        except Exception:
            return TicketActionOutcome(
                status="unknown", decision_id=decision.decision_id,
                approval_id=approval_id, idempotency_key=fact.idempotency_key,
            )
        try:
            await self._deliveries.deliver_event(decision.tenant_id, result_audit.event_id)
        except Exception:
            # Pending rows remain durable; replay does not call the ticket provider.
            pass
        try:
            await self._link_ticket(decision.tenant_id, incident_id, ticket)
        except Exception:
            return replace(self._from_submission(submitted), needs_reconciliation=True)
        return self._from_submission(submitted)
