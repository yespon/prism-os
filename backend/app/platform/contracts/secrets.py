"""Opaque, immutable reference to a source-scoped ticket credential."""

from typing import Literal

from app.platform.contracts.resources import StableName
from app.platform.contracts.types import FrozenContractModel, TenantId
from app.platform.contracts.versioning import PLATFORM_SCHEMA_V1, PlatformSchemaVersion


class SecretRef(FrozenContractModel):
    schema_version: PlatformSchemaVersion = PLATFORM_SCHEMA_V1
    id: StableName
    tenant_id: TenantId
    source_id: StableName
    purpose: Literal["ticket.create"] = "ticket.create"
    version: Literal[1] = 1
