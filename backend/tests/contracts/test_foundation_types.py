from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.platform.contracts.identifiers import new_platform_id, stable_platform_id
from app.platform.contracts.types import FrozenContractModel, TenantId, UtcDatetime
from app.platform.contracts.versioning import PLATFORM_SCHEMA_V1


class ExampleContract(FrozenContractModel):
    tenant_id: TenantId
    occurred_at: UtcDatetime


def test_schema_version_is_explicit_and_stable() -> None:
    assert PLATFORM_SCHEMA_V1 == "prismos.platform/v1"


@pytest.mark.parametrize("kind", ["resource", "task", "run", "event"])
def test_new_platform_id_has_kind_prefix(kind: str) -> None:
    value = new_platform_id(kind)
    assert value.startswith(f"{kind}_")
    assert value == value.lower()


def test_stable_platform_id_is_repeatable_and_namespaced() -> None:
    first = stable_platform_id("task", "aio-incident", "incident-42")
    second = stable_platform_id("task", "aio-incident", "incident-42")
    other = stable_platform_id("task", "research-job", "incident-42")
    assert first == second
    assert first != other


def test_contract_rejects_blank_tenant_naive_time_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ExampleContract(tenant_id=" ", occurred_at=datetime.now(UTC))
    with pytest.raises(ValidationError):
        ExampleContract(tenant_id="tenant-a", occurred_at=datetime.now())
    with pytest.raises(ValidationError):
        ExampleContract(
            tenant_id="tenant-a",
            occurred_at=datetime.now(UTC),
            hidden_domain_field="incident-1",
        )


def test_contract_is_frozen_and_serializes_time_as_utc() -> None:
    contract = ExampleContract(
        tenant_id="tenant-a",
        occurred_at=datetime(2026, 8, 8, 8, 30, tzinfo=UTC),
    )
    assert contract.model_dump(mode="json")["occurred_at"] == "2026-08-08T08:30:00Z"
    with pytest.raises(ValidationError):
        contract.tenant_id = "tenant-b"
