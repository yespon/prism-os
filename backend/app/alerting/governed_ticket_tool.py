"""The single canary Agent Action for a server-scoped incident diagnosis."""

import os
from datetime import UTC, datetime
from hashlib import sha256

from langchain_core.tools import tool

from app.alerting.governed_ticket import TicketActionAdapter, TicketActionOutcome
from app.platform.contracts import ExecutionEnvelope, IdentityRef, stable_platform_id
from app.platform.policy.evaluator import PolicyConfiguration, PolicyRule
from app.platform.policy.repository import PolicyDecisionRepository


def ticket_canary_enabled(tenant_id: str) -> bool:
    """Both trusted graph execution and one explicit tenant/Action must be enabled."""
    return (
        os.getenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "off").lower() == "required"
        and bool(tenant_id)
        and os.getenv("PRISMOS_GOVERNED_TICKET_TENANT", "") == tenant_id
        and os.getenv("PRISMOS_GOVERNED_TICKET_ACTION", "off") == "ticket.create"
    )


async def authorize_diagnosis_execution(execution, factory):
    if execution.attributes.get("agent_id") is None:
        return  # Legacy identity remains explicit in the original migration scope.
    from app.runtime_adapters import verify_runtime_selection

    context = {"tenant_id": execution.tenant_id, "user_id": execution.actor.id,
        "thread_id": execution.attributes.get("thread_id"), "agent_id": execution.attributes["agent_id"],
        "agent_name": execution.workload.id.removeprefix("diagnosis-agent:"),
        "diagnosis_incident_id": execution.attributes.get("diagnosis_incident_id") or execution.correlation_id,
        "diagnosis_source_id": execution.attributes.get("diagnosis_source_id"),
        "diagnosis_source_revision": execution.attributes.get("diagnosis_source_revision")}
    async with factory() as session:
        await verify_runtime_selection(session, context)


def ticket_adapter(tenant_id: str) -> TicketActionAdapter:
    verdict = os.getenv("PRISMOS_GOVERNED_TICKET_VERDICT", "deny")
    if verdict not in ("allow", "deny", "require_approval"):
        verdict = "deny"
    configuration = PolicyConfiguration(
        policy_id="aiops-ticket-m1",
        version=os.getenv("PRISMOS_GOVERNED_TICKET_POLICY_VERSION", "v1") or "v1",
        rules={"ticket.create": PolicyRule(risk_class="side_effect", verdict=verdict)},
    )
    return TicketActionAdapter(enabled_tenants=frozenset({tenant_id}) if ticket_canary_enabled(tenant_id) else frozenset(),
                               configuration=configuration, execution_authorizer=authorize_diagnosis_execution)


def ticket_request_id(thread_id: str, incident_id: str) -> str:
    digest = sha256(f"{thread_id}:{incident_id}".encode()).hexdigest()
    return f"ticket-{digest}"


def ticket_execution(scope: dict[str, str]) -> ExecutionEnvelope:
    tenant_id = scope["tenant_id"]
    thread_id = scope["thread_id"]
    return ExecutionEnvelope(
        tenant_id=tenant_id,
        task_id=stable_platform_id("task", "diagnosis", thread_id),
        run_id=stable_platform_id("run", "diagnosis", thread_id),
        correlation_id=scope["incident_id"],
        workload=IdentityRef(kind="workload", id=f"diagnosis-agent:{scope['agent_name']}", tenant_id=tenant_id),
        actor=IdentityRef(kind="user", id=scope["user_id"], tenant_id=tenant_id),
        occurred_at=datetime.now(UTC),
        attributes={"thread_id": thread_id, **{key: scope[key] for key in ("agent_id", "diagnosis_source_id", "diagnosis_source_revision", "diagnosis_incident_id") if scope.get(key) is not None}},
    )


def execution_matches_diagnosis_scope(execution: ExecutionEnvelope, scope: dict[str, str]) -> bool:
    return (
        execution.actor is not None
        and execution.actor.id == scope["user_id"]
        and execution.workload.id == f"diagnosis-agent:{scope['agent_name']}"
        and execution.attributes.get("agent_id") == scope.get("agent_id")
        and all(execution.attributes.get(key) == scope.get(key) for key in ("diagnosis_source_id", "diagnosis_source_revision", "diagnosis_incident_id"))
    )


async def execute_ticket_scope(scope: dict[str, str], *, adapter: TicketActionAdapter | None = None,
                               decisions: PolicyDecisionRepository | None = None) -> TicketActionOutcome:
    tenant_id = scope["tenant_id"]
    if not ticket_canary_enabled(tenant_id):
        raise PermissionError("governed ticket Action is disabled")
    request_id = ticket_request_id(scope["thread_id"], scope["incident_id"])
    existing = await (decisions or PolicyDecisionRepository()).get_by_request(tenant_id, request_id)
    execution = existing.execution if existing else ticket_execution(scope)
    if not execution_matches_diagnosis_scope(execution, scope):
        raise PermissionError("diagnosis Action identity changed")
    return await (adapter or ticket_adapter(tenant_id)).execute(execution, request_id, scope["incident_id"])


def governed_ticket_tools(scope: dict[str, str]) -> list:
    """Called only after the graph has consumed a server-issued diagnosis capability."""
    if not ticket_canary_enabled(scope["tenant_id"]):
        return []

    @tool("create_governed_incident_ticket")
    async def create_governed_incident_ticket() -> dict:
        """Create a ticket for this diagnosis incident through Policy and Approval; report the actual platform status."""
        outcome = await execute_ticket_scope(scope)
        return {
            "status": outcome.status, "decision_id": outcome.decision_id,
            "approval_id": outcome.approval_id, "ticket_id": outcome.ticket_id,
            "needs_reconciliation": outcome.needs_reconciliation,
        }

    from app.alerting.governed_read_tool import governed_read_file_tool

    return [create_governed_incident_ticket, governed_read_file_tool(scope)]
