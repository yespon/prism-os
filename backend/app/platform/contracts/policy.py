"""M1 Policy facts; no evaluator or side-effect execution lives here."""

import json
import re
from hashlib import sha256
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator

from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.resources import StableName
from app.platform.contracts.types import FrozenContractModel, TenantId, UtcDatetime
from app.platform.contracts.versioning import PLATFORM_SCHEMA_V1, PlatformSchemaVersion

RiskClass = Literal["read_only", "side_effect"]
PolicyVerdict = Literal["allow", "deny", "require_approval"]
ContextHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

_SENSITIVE_KEY_PARTS = ("password", "secret", "token", "apikey", "authorization", "credential", "privatekey")
_MAX_CONTEXT_BYTES = 64 * 1024
_MAX_CONTEXT_DEPTH = 8


def _validate_parameter(value: Any, *, depth: int = 0) -> None:
    if depth > _MAX_CONTEXT_DEPTH:
        raise ValueError("Action parameters are too deeply nested")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, list):
        for item in value:
            _validate_parameter(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Action parameter keys must be strings")
            normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
            if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                raise ValueError("Action parameters contain a sensitive field")
            _validate_parameter(item, depth=depth + 1)
        return
    raise ValueError("Action parameters must use canonical JSON values")


def _canonical_parameters(value: dict[str, Any]) -> str:
    _validate_parameter(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    if len(encoded.encode("utf-8")) > _MAX_CONTEXT_BYTES:
        raise ValueError("Action parameters are too large")
    return encoded


class ActionContextInput(FrozenContractModel):
    """Transient, nonsecret Action facts used only to calculate a context digest."""

    schema_version: PlatformSchemaVersion = PLATFORM_SCHEMA_V1
    tenant_id: TenantId
    execution: ExecutionEnvelope
    action: StableName
    risk_class: RiskClass
    resource_id: StableName | None = None
    parameters: dict[str, Any] = Field(default_factory=dict, exclude=True, repr=False)

    @field_validator("parameters")
    @classmethod
    def safe_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        _canonical_parameters(value)
        return value

    @model_validator(mode="after")
    def execution_shares_tenant(self) -> "ActionContextInput":
        if self.execution.tenant_id != self.tenant_id:
            raise ValueError("Action execution must belong to the same tenant")
        return self


def hash_action_context(context: ActionContextInput) -> str:
    """Hash the exact Action context without exposing its transient parameters."""
    if context.schema_version != PLATFORM_SCHEMA_V1 or context.execution.tenant_id != context.tenant_id:
        raise ValueError("Action context version or tenant changed")
    payload = {
        **context.model_dump(mode="json"),
        "parameters": json.loads(_canonical_parameters(context.parameters)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


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
