from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field

from app.platform.contracts.types import FrozenContractModel, TenantId, UtcDatetime


def _non_blank(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


StableName = Annotated[str, Field(min_length=1, max_length=255), AfterValidator(_non_blank)]
IdentityKind = Literal["user", "workload", "service", "system"]


class IdentityRef(FrozenContractModel):
    kind: IdentityKind
    id: StableName
    tenant_id: TenantId


class DefinitionRef(FrozenContractModel):
    kind: StableName
    id: StableName
    version: StableName
    tenant_id: TenantId


class EnvironmentRef(FrozenContractModel):
    kind: Literal["development", "test", "staging", "production", "custom"]
    id: StableName
    tenant_id: TenantId


class ResourceMetadata(FrozenContractModel):
    id: StableName
    tenant_id: TenantId
    resource_type: StableName
    resource_version: StableName
    created_at: UtcDatetime
    labels: dict[StableName, StableName] = Field(default_factory=dict)
    annotations: dict[str, Any] = Field(default_factory=dict)
