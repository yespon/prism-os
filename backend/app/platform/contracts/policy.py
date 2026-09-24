"""M1 Policy facts; no evaluator or side-effect execution lives here."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.resources import StableName
from app.platform.contracts.types import FrozenContractModel, TenantId, UtcDatetime
from app.platform.contracts.versioning import PLATFORM_SCHEMA_V1, PlatformSchemaVersion

RiskClass = Literal["read_only", "side_effect"]
PolicyVerdict = Literal["allow", "deny", "require_approval"]
ContextHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class PolicyRequest(FrozenContractModel):
    schema_version: PlatformSchemaVersion = PLATFORM_SCHEMA_V1
    tenant_id: TenantId
    request_id: StableName
    execution: ExecutionEnvelope
    action: StableName
    risk_class: RiskClass
    resource_id: StableName | None = None
    context_hash: ContextHash
    requested_at: UtcDatetime

    @model_validator(mode="after")
    def execution_shares_tenant(self) -> "PolicyRequest":
        if self.execution.tenant_id != self.tenant_id:
            raise ValueError("policy execution must belong to the same tenant")
        return self


class PolicyDecision(FrozenContractModel):
    schema_version: PlatformSchemaVersion = PLATFORM_SCHEMA_V1
    tenant_id: TenantId
    decision_id: StableName
    request_id: StableName
    execution: ExecutionEnvelope
    action: StableName
    risk_class: RiskClass
    resource_id: StableName | None = None
    context_hash: ContextHash
    verdict: PolicyVerdict
    policy_id: StableName
    policy_version: StableName
    reason_code: StableName
    decided_at: UtcDatetime
    expires_at: UtcDatetime

    @model_validator(mode="after")
    def valid_context_and_expiry(self) -> "PolicyDecision":
        if self.execution.tenant_id != self.tenant_id:
            raise ValueError("policy execution must belong to the same tenant")
        if self.expires_at <= self.decided_at:
            raise ValueError("policy decision expiry must follow decision time")
        return self

    def binds(self, request: PolicyRequest) -> bool:
        """Check that a decision belongs to this exact Action context."""
        return (
            self.schema_version == request.schema_version
            and self.tenant_id == request.tenant_id
            and self.request_id == request.request_id
            and self.execution == request.execution
            and self.action == request.action
            and self.risk_class == request.risk_class
            and self.resource_id == request.resource_id
            and self.context_hash == request.context_hash
        )
