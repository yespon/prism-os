"""Alert ingest pipeline — the entry point for external alerts.

Orchestrates:
1. Receive raw payload → parse via provider → raw_alert
2. Normalise → signal
3. Evaluate user rules (priority: suppression > aggregation > system default)

Rule priority model (user rules override system defaults):
  - No user rules match → system default (auto fingerprint dedup, service+env aggregation, 30min window)
  - Suppression rule matches → alert is silenced, no incident created
  - Aggregation rule matches → user's group_by + window_minutes override system defaults
  - Multiple rules of same type match → first match wins
"""

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerting.ai_analysis import schedule_analysis, should_auto_analyze
from app.alerting.dedup import compute_payload_hash
from app.alerting.incident_manager import create_signal, find_or_create_incident
from app.alerting.providers import get_provider
from app.alerting.rule_engine import evaluate_rules, get_aggregation_config
from app.models.alerting import AlertRule, AlertSource, Incident, IncidentSignalLink, RawAlert, Signal
from app.platform.execution.trust import attach_execution_capability

logger = logging.getLogger(__name__)

# Duplicate payloads arriving within this window are treated as idempotent retries
_IDEMPOTENCY_WINDOW_MINUTES = 5


async def process_alert(
    session: AsyncSession,
    source: AlertSource,
    body: dict,
    headers: dict,
) -> tuple[Incident | None, bool, str]:
    """Run the full ingest pipeline for a single alert payload.

    Args:
        session: DB session.
        source: The configured alert source.
        body: Parsed JSON body of the incoming request.
        headers: Request headers.

    Returns:
        (incident, is_new, disposition) —
        * ``disposition`` is one of ``"created"``, ``"merged"``, ``"suppressed"``, ``"duplicate"``.
        * When suppressed, ``incident`` is None.
    """
    provider = get_provider(source.type)
    if provider is None:
        raise ValueError(f"No provider registered for type '{source.type}'")

    # Validate auth
    if not provider.validate_auth(headers, source.config_json):
        raise PermissionError("Authentication failed for alert source")

    payload_hash = compute_payload_hash(body)

    # Idempotency check — same payload from same source within window = duplicate
    cutoff = datetime.now(UTC) - timedelta(minutes=_IDEMPOTENCY_WINDOW_MINUTES)
    dup_result = await session.exec(
        select(RawAlert).where(
            RawAlert.tenant_id == source.tenant_id,
            RawAlert.source_id == source.id,
            RawAlert.payload_hash == payload_hash,
            RawAlert.received_at >= cutoff,
        ).limit(1)
    )
    existing_raw = dup_result.scalars().first()
    if existing_raw is not None:
        # Resolve the linked incident to return consistent response
        sig_result = await session.exec(
            select(Signal).where(Signal.raw_alert_id == existing_raw.id).limit(1)
        )
        existing_signal = sig_result.scalars().first()
        incident = None
        if existing_signal is not None:
            link_result = await session.exec(
                select(IncidentSignalLink).where(
                    IncidentSignalLink.signal_id == existing_signal.id,
                    IncidentSignalLink.tenant_id == source.tenant_id,
                ).limit(1)
            )
            link = link_result.scalars().first()
            if link is not None:
                incident = await session.get(Incident, link.incident_id)

        logger.info("ingest source=%s duplicate payload hash=%s", source.id, payload_hash[:16])
        return incident, False, "duplicate"

    # Step 1 — raw_alert
    raw_alert = provider.parse_raw_payload(body, headers)
    raw_alert.id = str(uuid.uuid4())
    raw_alert.tenant_id = source.tenant_id
    raw_alert.source_id = source.id
    raw_alert.payload_hash = payload_hash
    raw_alert.ingest_status = "received"
    session.add(raw_alert)

    # Step 2 — normalise to signal(s)
    # For Alertmanager, process all alerts in batch mode
    if hasattr(provider, "batch_alerts") and source.type == "alertmanager":
        batch_signals = provider.batch_alerts(raw_alert, source_config=source.config_json)
        if batch_signals:
            # Process first signal inline, queue rest as background tasks
            signal = batch_signals[0]
            signal.tenant_id = source.tenant_id
            signal.raw_alert_id = raw_alert.id
            await create_signal(session, raw_alert, signal)

            # Process remaining signals in background
            if len(batch_signals) > 1:
                _schedule_batch_signals(raw_alert, source, batch_signals[1:])
        else:
            # Fallback to single normalize
            signal = provider.normalize(raw_alert, source_config=source.config_json)
            signal.tenant_id = source.tenant_id
            signal.raw_alert_id = raw_alert.id
            await create_signal(session, raw_alert, signal)
    else:
        signal = provider.normalize(raw_alert, source_config=source.config_json)
        signal.tenant_id = source.tenant_id
        signal.raw_alert_id = raw_alert.id
        await create_signal(session, raw_alert, signal)

    raw_alert.ingest_status = "normalized"
    session.add(raw_alert)

    # Step 2.5 — load active user-defined rules for this tenant
    rules_result = await session.exec(
        select(AlertRule).where(
            AlertRule.tenant_id == source.tenant_id,
            AlertRule.enabled == True,  # noqa: E712
        )
    )
    active_rules = list(rules_result.scalars().all())

    # Step 2.6 — evaluate rules (user overrides > system defaults)
    # Priority: suppression first, then aggregation for grouping config
    matched = evaluate_rules(active_rules, signal)

    # Check suppression rules (first match wins)
    for r in matched:
        if r.rule_type == "suppression":
            raw_alert.ingest_status = "suppressed"
            raw_alert.error_message = f"Suppressed by rule: {r.name}"
            session.add(raw_alert)
            await session.commit()
            logger.info("ingest source=%s suppressed by rule=%s", source.id, r.name)
            return None, False, "suppressed"

    # Get aggregation override from user rules (None = use system defaults)
    aggregation_config = get_aggregation_config(matched)
    if aggregation_config:
        logger.debug("ingest using user aggregation rule: group_by=%s window=%s",
                      aggregation_config.get("group_by"), aggregation_config.get("window_minutes"))

    incident, is_new = await find_or_create_incident(
        session, signal, raw_alert, aggregation_config=aggregation_config,
    )

    await session.commit()

    disposition = "created" if is_new else "merged"

    # Trigger AI analysis + IM notification for newly created incidents (fire-and-forget)
    if is_new:
        if should_auto_analyze(source.config_json, signal.severity):
            signals_data = [{
                "title": signal.title,
                "severity": signal.severity,
                "source": signal.source,
                "fingerprint": signal.fingerprint,
                "labels_json": signal.labels_json,
            }]
            trigger = (source.config_json or {}).get("analysis_trigger", {})
            model_name = trigger.get("model") or None
            schedule_analysis(incident, signals_data, body, model_name)

            # Auto-trigger agent diagnosis if source has a bound agent
            diagnosis_agent_id = trigger.get("diagnosis_agent_id")
            if diagnosis_agent_id:
                _schedule_agent_diagnosis(incident, source.tenant_id, diagnosis_agent_id, source.id)

        # Schedule IM notification (delayed, waits for AI)
        from app.alerting.notify import schedule_notification, send_incident_created

        schedule_notification(send_incident_created(incident))

        # Evaluate escalation rules for newly created incidents (fire-and-forget)
        _schedule_escalation_evaluation(incident)

    logger.info(
        "ingest source=%s type=%s incident=%s disposition=%s",
        source.id,
        source.type,
        incident.incident_key,
        disposition,
    )
    return incident, is_new, disposition


def _schedule_escalation_evaluation(incident: Incident):
    """Fire-and-forget: evaluate escalation rules for a newly created incident."""
    import asyncio

    from deerflow.database.session import get_session_factory

    async def _run():
        try:
            from app.alerting.escalation import apply_escalation_actions, evaluate_escalation_rules

            async with get_session_factory()() as session:
                fresh_inc = await session.get(Incident, incident.id)
                if not fresh_inc or fresh_inc.status != "firing":
                    return

                matching = await evaluate_escalation_rules(fresh_inc, session)
                if matching:
                    await apply_escalation_actions(fresh_inc, matching, session)
                    logger.info(
                        "Escalation: incident %s matched %d rules",
                        fresh_inc.incident_key,
                        len(matching),
                    )
        except Exception:
            logger.exception("Failed to evaluate escalation rules for incident=%s", incident.id)

    asyncio.create_task(_run())


def _schedule_batch_signals(raw_alert: RawAlert, source, remaining_signals: list):
    """Fire-and-forget: process remaining batch signals in background."""
    import asyncio

    from deerflow.database.session import get_session_factory

    async def _run():
        try:
            async with get_session_factory()() as session:
                for sig in remaining_signals:
                    sig.id = str(uuid.uuid4())
                    sig.tenant_id = raw_alert.tenant_id
                    sig.raw_alert_id = raw_alert.id
                    session.add(sig)
                await session.commit()
                logger.info(
                    "Batch ingest: processed %d additional signals for raw_alert=%s",
                    len(remaining_signals),
                    raw_alert.id,
                )
        except Exception:
            logger.exception("Failed to process batch signals for raw_alert=%s", raw_alert.id)

    asyncio.create_task(_run())


def _schedule_agent_diagnosis(incident, tenant_id: str, diagnosis_agent_id: str, source_id: str | None = None):
    """Fire-and-forget: trigger agent diagnosis for a newly created incident."""
    import asyncio

    from deerflow.database.session import get_session_factory

    async def _run():
        from app.alerting.diagnosis_run_control import DiagnosisAuthorityWithdrawn, DiagnosisStopRequested

        try:
            from langgraph_sdk import get_client

            from app.alerting.diagnosis_helper import build_incident_diagnosis_prompt

            async with get_session_factory()() as session:
                from sqlalchemy import select
                fresh_inc = (await session.exec(select(Incident).where(Incident.id == incident.id, Incident.tenant_id == tenant_id))).scalars().first()
                if fresh_inc is None:
                    raise RuntimeError("Current diagnosis incident is unavailable")
                fresh_inc.diagnosis_status = "running"
                session.add(fresh_inc)
                await session.commit()

                from app.alerting.diagnosis_authorization import current_authorization, revision
                from app.models.alerting import AlertSource
                from app.runtime_adapters import verify_native_selection
                if not source_id:
                    raise RuntimeError("Automatic diagnosis requires a source authorization")
                actor_id, agent = await current_authorization(session, source_id, tenant_id, diagnosis_agent_id, severity=fresh_inc.severity)
                source_revision = revision((await session.get(AlertSource, source_id)).config_json)

                langgraph_url = os.getenv("LANGGRAPH_API_URL", "http://localhost:2024")
                client = get_client(url=langgraph_url)
                thread = await client.threads.create(metadata={
                    "incident_id": incident.id,
                    "tenant_id": tenant_id,
                    "owner_tenant_id": tenant_id,
                    "owner_user_id": actor_id,
                })
                thread_id = thread["thread_id"]

                # Refresh incident data after the network wait; Agent/Skill
                # configuration belongs to the current authorized graph prompt.
                fresh_inc = (await session.exec(select(Incident).where(Incident.id == incident.id, Incident.tenant_id == tenant_id).execution_options(populate_existing=True))).scalars().first()
                if fresh_inc is None:
                    raise RuntimeError("Current diagnosis incident is unavailable")
                actor_id, agent = await current_authorization(session, source_id, tenant_id, diagnosis_agent_id, expected_actor=actor_id, expected_revision=source_revision, severity=fresh_inc.severity)
                from app.platform.execution.trust import ThreadBindingRepository

                bindings = ThreadBindingRepository(get_session_factory())
                await bindings.create(thread_id, tenant_id, actor_id)
                await bindings.bind_agent(thread_id, tenant_id, actor_id, agent.name)
                fresh_inc.agent_id = diagnosis_agent_id
                fresh_inc.thread_id = thread_id
                session.add(fresh_inc)
                await session.commit()
                prompt = await build_incident_diagnosis_prompt(session, fresh_inc, tenant_id, include_agent_configuration=False)
                from app.alerting.diagnosis_run_control import interrupt_owned_runs, wait_authorized_result

                async def validate_running():
                    async with get_session_factory()() as current:
                        from app.runtime_adapters import verify_runtime_selection

                        await verify_runtime_selection(current, {"tenant_id": tenant_id, "user_id": actor_id, "thread_id": thread_id,
                            "agent_name": agent.name, "agent_id": agent.id, "diagnosis_source_id": source_id,
                            "diagnosis_source_revision": source_revision, "diagnosis_incident_id": incident.id})

                async def interrupt_running():
                    return await interrupt_owned_runs(client, thread_id, tenant_id, actor_id, get_session_factory())

                result = await wait_authorized_result(client.runs.wait(
                    thread_id,
                    "lead_agent",
                    input={"messages": [{"role": "human", "content": prompt}]},
                    config={
                        "recursion_limit": 500,
                    },
                    context=await attach_execution_capability({
                        "agent_name": agent.name,
                        "tenant_id": tenant_id,
                        "user_id": actor_id,
                        "agent_id": agent.id,
                        "diagnosis_source_id": source_id,
                        "diagnosis_source_revision": source_revision,
                        "diagnosis_incident_id": fresh_inc.id,
                        "thread_id": thread_id,
                    }, native_selection_validator=verify_native_selection),
                ), validate_running, interrupt_running)

                # Extract the last AI response text from the result
                diagnosis_text = ""
                if isinstance(result, dict):
                    messages = result.get("messages", [])
                    for msg in reversed(messages):
                        if isinstance(msg, dict) and msg.get("type") == "ai":
                            content = msg.get("content", "")
                            if isinstance(content, str):
                                diagnosis_text = content
                            elif isinstance(content, list):
                                diagnosis_text = "".join(
                                    c.get("text", "") if isinstance(c, dict) else str(c)
                                    for c in content
                                )
                            if diagnosis_text:
                                break

                # Store linkage, result, and completed status
                await validate_running()
                fresh = await session.get(Incident, incident.id, populate_existing=True)
                if fresh and fresh.tenant_id == tenant_id:
                    fresh.agent_id = diagnosis_agent_id
                    fresh.thread_id = thread_id
                    fresh.diagnosis_status = "completed"
                    fresh.diagnosis_result = diagnosis_text or None
                    fresh.diagnosis_error = None
                    session.add(fresh)
                    await session.commit()

                logger.info("diagnose: auto-completed for incident=%s agent=%s", incident.incident_key, agent.name)

        except DiagnosisStopRequested:
            # The original cancellation endpoint owns confirmation/unknown;
            # never publish a late result or overwrite that intent.
            logger.info("diagnose: auto wait stopped by recorded cancellation for incident=%s", incident.id)

        except DiagnosisAuthorityWithdrawn as withdrawn:
            from app.models.alerting import IncidentAction

            async with get_session_factory()() as err_session:
                fresh = await err_session.get(Incident, incident.id)
                if fresh and fresh.tenant_id == tenant_id:
                    fresh.agent_id = diagnosis_agent_id
                    fresh.thread_id = thread_id
                    fresh.diagnosis_status = "cancelled" if withdrawn.interruption.status == "confirmed" else "failed"
                    fresh.diagnosis_error = str(withdrawn)
                    err_session.add(fresh)
                    err_session.add(IncidentAction(id=str(uuid.uuid4()), tenant_id=tenant_id, incident_id=incident.id,
                        actor_id=actor_id, action_type="diagnosis_authority_withdrawn",
                        action_payload={"interruption": withdrawn.interruption.status, "thread_id": thread_id,
                            "source_id": source_id, "source_revision": source_revision,
                            "run_ids": list(withdrawn.interruption.run_ids), "external_effects": "unknown"}))
                    await err_session.commit()

        except Exception:
            logger.exception("diagnose: auto-failed for incident=%s", incident.incident_key)
            try:
                async with get_session_factory()() as err_session:
                    fresh = await err_session.get(Incident, incident.id)
                    if fresh and fresh.tenant_id == tenant_id:
                        fresh.diagnosis_status = "failed"
                        fresh.diagnosis_error = "自动诊断执行失败，请手动发起深度诊断"
                        err_session.add(fresh)
                        await err_session.commit()
            except Exception:
                logger.exception("diagnose: failed to save failure status for incident=%s", incident.incident_key)

    task = asyncio.create_task(_run())
    logger.info("diagnose: auto-scheduled for incident=%s agent=%s", incident.incident_key, diagnosis_agent_id)
    return task
