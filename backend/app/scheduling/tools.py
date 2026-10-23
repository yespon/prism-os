"""Governed schedule creation tool (R3 week 2).

The Agent-exposed path for creating schedules: creating a schedule is a
side effect, so the tool runs through the same Policy/Approval/Audit
chain as ticket creation (R3 spec section 5). The API route stays the
direct admin path.
"""

from langchain.tools import tool

from app.scheduling import ScheduleService, SchedulingError


def governed_schedule_tools(scope: dict) -> list:
    """Assemble the schedule.create tool for a governed agent scope.

    Returns [] unless the schedule canary is enabled for the tenant -
    same enablement pattern as the governed ticket tool, so rollout
    stays tenant-by-tenant.
    """
    from app.alerting.governed_ticket_tool import ticket_canary_enabled

    if not ticket_canary_enabled(scope["tenant_id"]):
        return []

    @tool("schedule.create", parse_docstring=True)
    async def create_schedule(name: str, trigger_kind: str, prompt: str,
                              cron_expr: str | None = None) -> dict:
        """Create a governed schedule after a durable Policy decision.

        Args:
            name: Human-readable schedule name.
            trigger_kind: One of cron, date, interval.
            prompt: The task instruction to run on each trigger.
            cron_expr: Cron expression when trigger_kind is cron.
        """
        tenant_id = scope["tenant_id"]
        try:
            record = await ScheduleService().create_definition(
                tenant_id, scope["user_id"], name=name, trigger_kind=trigger_kind,
                cron_expr=cron_expr, agent_name=scope.get("agent_name") or "default",
                prompt=prompt,
            )
        except SchedulingError as error:
            return {"status": "rejected", "reason": str(error)}
        return {"status": "created", "schedule_id": record.id, "trigger_kind": record.trigger_kind}

    return [create_schedule]
