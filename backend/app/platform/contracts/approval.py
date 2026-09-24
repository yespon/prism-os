"""M1 Approval facts; persistence and concurrency control belong to the service layer."""

from typing import Literal

from pydantic import model_validator

from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.policy import ContextHash, PolicyDecision
from app.platform.contracts.resources import IdentityRef, StableName
from app.platform.contracts.types import FrozenContractModel, TenantId, UtcDatetime
from app.platform.contracts.versioning import PLATFORM_SCHEMA_V1, PlatformSchemaVersion

ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "consumed"]


class Approval(FrozenContractModel):
    schema_version: PlatformSchemaVersion = PLATFORM_SCHEMA_V1
    tenant_id: TenantId
    approval_id: StableName
    decision_id: StableName
    request_id: StableName
    execution: ExecutionEnvelope
    action: StableName
    resource_id: StableName | None = None
    context_hash: ContextHash
    policy_version: StableName
    requester: IdentityRef
    status: ApprovalStatus
    created_at: UtcDatetime
    expires_at: UtcDatetime
    approver: IdentityRef | None = None
    decided_at: UtcDatetime | None = None
    consumed_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def valid_state(self) -> "Approval":
        refs = (self.execution, self.requester, self.approver)
        if any(ref is not None and ref.tenant_id != self.tenant_id for ref in refs):
            raise ValueError("approval references must belong to the same tenant")
        if self.execution.actor is not None and self.requester != self.execution.actor:
            raise ValueError("approval requester must match the execution actor")
        if self.expires_at <= self.created_at:
            raise ValueError("approval expiry must follow creation")
        if self.status == "pending":
            if any(value is not None for value in (self.approver, self.decided_at, self.consumed_at)):
                raise ValueError("pending approval cannot have terminal fields")
        elif self.status in ("approved", "rejected", "consumed"):
            if self.approver is None or self.decided_at is None:
                raise ValueError("approval decision requires approver and decided_at")
            if not self.created_at <= self.decided_at < self.expires_at:
                raise ValueError("approval decision must occur before expiry")
            if self.status == "consumed":
                if self.consumed_at is None or not self.decided_at <= self.consumed_at < self.expires_at:
                    raise ValueError("consumption must occur after approval and before expiry")
            elif self.consumed_at is not None:
                raise ValueError("only approved approval may be consumed")
        elif self.status == "expired":
            if self.approver is not None or self.consumed_at is not None:
                raise ValueError("expired approval cannot have approver or consumption")
            if self.decided_at is None or self.decided_at < self.expires_at:
                raise ValueError("expiry must be recorded at or after deadline")
        return self

    def binds(self, decision: PolicyDecision) -> bool:
        """Check the immutable decision context before creating or resuming approval."""
        return (
            decision.verdict == "require_approval"
            and self.schema_version == decision.schema_version
            and self.tenant_id == decision.tenant_id
            and self.decision_id == decision.decision_id
            and self.request_id == decision.request_id
            and self.execution == decision.execution
            and self.action == decision.action
            and self.resource_id == decision.resource_id
            and self.context_hash == decision.context_hash
            and self.policy_version == decision.policy_version
            and self.expires_at <= decision.expires_at
        )
