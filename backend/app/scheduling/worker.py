"""Cron worker: schedules definitions, executes occurrences idempotently (R3).

Single-instance constraint (R3 spec): one worker per deployment; no lease
mechanism yet, so running more than one would double-trigger. The worker
rebuilds its schedule from the DB on boot, making restarts safe through the
occurrence claim protocol rather than scheduler-state persistence.
"""

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.scheduling import ScheduleService

logger = logging.getLogger(__name__)


class CronWorker:
    """Owns the scheduler and the trigger-to-occurrence pipeline."""

    def __init__(self, service: ScheduleService | None = None, timezone: str = "Asia/Shanghai",
                 execute=None) -> None:
        """``execute`` is the host-provided run entry:

        async def execute(tenant_id, definition, occurrence) -> str
        returning the run identity (stored on the occurrence). The worker
        itself never talks to LangGraph - the host wires the trusted entry
        (Gateway capability issuance) so scheduled runs share the same
        governance chain as web runs. When ``execute`` is None the claim is
        still durable and the occurrence completes without a run.
        """
        self._service = service or ScheduleService()
        self._timezone = timezone
        self._execute = execute
        self._scheduler = AsyncIOScheduler(timezone=timezone)

    async def boot(self) -> int:
        """Start the scheduler and register every enabled definition."""
        from sqlmodel import select as _select

        from app.models.scheduling import ScheduleDefinitionRecord

        definitions = await self._service.list_definitions(tenant_id="*", enabled_only=True) if False else []
        # List across tenants: the service filters by tenant, so query directly.
        from deerflow.database.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            definitions = list((await session.exec(
                _select(ScheduleDefinitionRecord).where(ScheduleDefinitionRecord.enabled == 1)
            )).all())
        for definition in definitions:
            self._register(definition)
        self._scheduler.start()
        logger.info("CronWorker booted; scheduled %d jobs", len(definitions))
        return len(definitions)

    def _register(self, definition) -> None:
        job_id = definition.id
        if definition.trigger_kind == "cron":
            trigger = CronTrigger.from_crontab(definition.cron_expr, timezone=definition.timezone)
        elif definition.trigger_kind == "date":
            trigger = DateTrigger(run_date=definition.run_at, timezone=definition.timezone)
        else:
            trigger = IntervalTrigger(seconds=definition.interval_seconds, timezone=definition.timezone)
        self._scheduler.add_job(
            self._fire, trigger, id=job_id,
            kwargs={"tenant_id": definition.tenant_id, "schedule_id": definition.id},
            replace_existing=True,
        )

    async def _fire(self, tenant_id: str, schedule_id: str) -> None:
        """One trigger: claim the slot, then execute once if created."""
        scheduled_at = datetime.now(UTC)
        occurrence, created = await self._service.claim_occurrence(tenant_id, schedule_id, scheduled_at)
        if not created:
            logger.info("occurrence %s already claimed; skipping duplicate trigger", occurrence.id)
            return
        logger.info("occurrence %s claimed for schedule %s", occurrence.id, schedule_id)
        definition = await self._service.get_definition(tenant_id, schedule_id)
        if definition is None:
            await self._service.mark_finished(tenant_id, occurrence.id, failed=True)
            return
        if self._execute is None:
            # No host run entry wired: the claim remains the durable evidence
            # that the trigger fired exactly once.
            await self._service.mark_finished(tenant_id, occurrence.id)
            return
        try:
            run_id = await self._execute(tenant_id, definition, occurrence)
            await self._service.mark_running(tenant_id, occurrence.id, run_id)
            await self._service.mark_finished(tenant_id, occurrence.id)
            await self._service.record_delivery_attempt(
                tenant_id, occurrence.id,
                f"{definition.delivery_channel}:{definition.delivery_target or 'default'}",
                delivered=True, provider_message_id=run_id,
            )
        except Exception:
            logger.exception("scheduled run failed for occurrence %s", occurrence.id)
            await self._service.mark_finished(tenant_id, occurrence.id, failed=True)
            await self._service.record_delivery_attempt(
                tenant_id, occurrence.id,
                f"{definition.delivery_channel}:{definition.delivery_target or 'default'}",
                delivered=False, error="execution_failed",
            )

    async def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
