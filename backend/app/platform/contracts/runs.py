"""Minimal persistent run facts with frozen execution snapshots (R1-A).

A run fact is the platform's durable record that an execution happened or is
happening: who ran what workload, under which agent/model configuration, and
the frozen snapshot of that configuration. M1's ``run_id`` was a correlation
ID only; from R1 the fact row is the source of truth that UI refresh, restart
recovery, and audit projection read from.
"""

from typing import Any

from pydantic import Field, model_validator

from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.resources import IdentityRef
from app.platform.contracts.types import FrozenContractModel, TenantId, UtcDatetime
from app.platform.contracts.versioning import PLATFORM_SCHEMA_V1, PlatformSchemaVersion

RunState = str
# Minimal lifecycle for R1: facts are recorded, not state-machined. The full
# Task/Run/Attempt/Action state machine remains M2/R5 scope; these states only
# describe what is known about the durable fact.
RUN_CREATED = "created"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"


class ExecutionSnapshot(FrozenContractModel):
    """Frozen configuration references captured when a run starts.

    The snapshot stores *references and summaries* (agent name/id, model name,
    tool group selection), never credentials or model secrets. It answers
    "which configuration did this run use" after the live configuration has
    changed or been deleted.
    """

    schema_version: PlatformSchemaVersion = PLATFORM_SCHEMA_V1
    agent_name: str | None = None
    agent_id: str | None = None
    # Immutable agent version this run executed under (R5 versioning): the
    # deployment pointer's version id at run start, when a deployment exists.
    agent_version_id: str | None = None
    model_name: str | None = None
    tool_groups: tuple[str, ...] = ()
    source: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class RunFact(FrozenContractModel):
    """Durable record of one platform execution identity."""

    schema_version: PlatformSchemaVersion = PLATFORM_SCHEMA_V1
    tenant_id: TenantId
    run_id: str
    task_id: str
    correlation_id: str | None = None
    thread_id: str | None = None
    workload: IdentityRef
    actor: IdentityRef | None = None
    state: RunState = RUN_CREATED
    snapshot: ExecutionSnapshot = Field(default_factory=ExecutionSnapshot)
    started_at: UtcDatetime
    finished_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def references_share_tenant(self) -> "RunFact":
        references = (self.workload, self.actor)
        if any(ref is not None and ref.tenant_id != self.tenant_id for ref in references):
            raise ValueError("run fact references must belong to the same tenant")
        return self


def run_fact_from_envelope(
    envelope: ExecutionEnvelope,
    snapshot: ExecutionSnapshot | None = None,
) -> RunFact:
    """Project an execution envelope into its durable run fact.

    The envelope stays the in-flight execution identity; the fact is what
    survives restarts. Idempotent per (tenant, run): recording the same run
    twice must not create a second row or mutate the frozen snapshot.
    """

    return RunFact(
        tenant_id=envelope.tenant_id,
        run_id=envelope.run_id,
        task_id=envelope.task_id,
        correlation_id=envelope.correlation_id,
        thread_id=envelope.attributes.get("thread_id"),
        workload=envelope.workload,
        actor=envelope.actor,
        state=RUN_CREATED,
        snapshot=snapshot or ExecutionSnapshot(),
        started_at=envelope.occurred_at,
    )
