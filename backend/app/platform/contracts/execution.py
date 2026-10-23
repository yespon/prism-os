from typing import Any

from pydantic import Field, model_validator

from app.platform.contracts.resources import DefinitionRef, EnvironmentRef, IdentityRef, StableName
from app.platform.contracts.types import FrozenContractModel, TenantId, UtcDatetime
from app.platform.contracts.versioning import PLATFORM_SCHEMA_V1, PlatformSchemaVersion


class ExecutionEnvelope(FrozenContractModel):
    schema_version: PlatformSchemaVersion = PLATFORM_SCHEMA_V1
    tenant_id: TenantId
    task_id: StableName
    run_id: StableName
    correlation_id: StableName
    workload: IdentityRef
    actor: IdentityRef | None = None
    definition: DefinitionRef | None = None
    environment: EnvironmentRef | None = None
    occurred_at: UtcDatetime
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def references_share_tenant(self) -> "ExecutionEnvelope":
        references = (self.workload, self.actor, self.definition, self.environment)
        if any(ref is not None and ref.tenant_id != self.tenant_id for ref in references):
            raise ValueError("execution references must belong to the same tenant")
        return self
