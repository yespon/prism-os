from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.platform.contracts.resources import (
    DefinitionRef,
    EnvironmentRef,
    IdentityRef,
    ResourceMetadata,
)


def test_resource_metadata_is_domain_neutral() -> None:
    metadata = ResourceMetadata(
        id="resource_0123456789abcdef0123456789abcdef",
        tenant_id="tenant-a",
        resource_type="report",
        resource_version="7",
        created_at=datetime(2026, 8, 8, tzinfo=UTC),
        labels={"risk": "high"},
        annotations={"source": "golden-scenario"},
    )
    assert metadata.resource_type == "report"
    assert "incident_id" not in metadata.model_json_schema()["required"]


def test_identity_definition_and_environment_are_tenant_scoped() -> None:
    identity = IdentityRef(kind="workload", id="agent-7", tenant_id="tenant-a")
    definition = DefinitionRef(kind="agent", id="definition-4", version="3", tenant_id="tenant-a")
    environment = EnvironmentRef(kind="production", id="prod-cn", tenant_id="tenant-a")
    assert identity.kind == "workload"
    assert definition.version == "3"
    assert environment.id == "prod-cn"


@pytest.mark.parametrize("field", ["id", "resource_type", "resource_version"])
def test_resource_metadata_rejects_blank_stable_fields(field: str) -> None:
    payload = {
        "id": "resource_0123456789abcdef0123456789abcdef",
        "tenant_id": "tenant-a",
        "resource_type": "artifact",
        "resource_version": "1",
        "created_at": datetime.now(UTC),
    }
    payload[field] = " "
    with pytest.raises(ValidationError):
        ResourceMetadata.model_validate(payload)


def test_resource_labels_reject_blank_keys_and_values() -> None:
    common = {
        "id": "resource_0123456789abcdef0123456789abcdef",
        "tenant_id": "tenant-a",
        "resource_type": "artifact",
        "resource_version": "1",
        "created_at": datetime.now(UTC),
    }
    with pytest.raises(ValidationError):
        ResourceMetadata(**common, labels={" ": "high"})
    with pytest.raises(ValidationError):
        ResourceMetadata(**common, labels={"risk": " "})
