from typing import Any, Literal

from pydantic import Field, model_validator

from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.resources import StableName
from app.platform.contracts.types import FrozenContractModel, TenantId, UtcDatetime
from app.platform.contracts.versioning import PLATFORM_SCHEMA_V1, PlatformSchemaVersion

AuditOutcome = Literal["pending", "succeeded", "failed", "denied", "cancelled"]
AuditSeverity = Literal["debug", "info", "warning", "error", "critical"]


class AuditEvent(FrozenContractModel):
    schema_version: PlatformSchemaVersion = PLATFORM_SCHEMA_V1
    tenant_id: TenantId
    event_id: StableName
    event_type: StableName
    action: StableName
    outcome: AuditOutcome
    severity: AuditSeverity = "info"
    execution: ExecutionEnvelope
    policy_decision_id: StableName | None = None
    approval_id: StableName | None = None
    resource_id: StableName | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    recorded_at: UtcDatetime

    @model_validator(mode="after")
    def execution_shares_tenant(self) -> "AuditEvent":
        if self.execution.tenant_id != self.tenant_id:
            raise ValueError("audit execution must belong to the same tenant")
        return self

    @property
    def task_id(self) -> str:
        return self.execution.task_id

    @property
    def run_id(self) -> str:
        return self.execution.run_id
