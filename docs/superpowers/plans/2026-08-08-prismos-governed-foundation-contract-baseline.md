# PrismOS Governed Foundation Contract Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 PrismOS M1 建立可版本化、领域无关且可持久化验证的治理基础契约，冻结 Resource/Identity/Definition/Environment 引用、Execution Envelope、AuditEvent、ID/Version/Tenant 不变量，并以 AIOps 场景证明核心契约不依赖运维领域对象。

**Architecture:** 新增 `app.platform` 边界作为平台契约所有者，Pydantic v2 模型负责传输和验证，SQLModel/Alembic 只为统一 AuditEvent 建立最小持久化投影。现有 Gateway JSONL 审计在 P0 保持原读写路径，通过纯函数 Adapter 和默认 dry-run 的迁移工具建立兼容入口；实际双写切换、Policy/Approval 执行和 Task/Run 生命周期留给后续 M1 工作包。

**Tech Stack:** Python 3.12；Pydantic v2；FastAPI；SQLModel/SQLAlchemy async；Alembic；pytest；现有 DeerFlow/LangGraph runtime。

## Global Constraints

- **执行编制：** 按 4–5 名核心成员并行实施；只有 Contract Owner 可以修改公共导出和创建 Alembic migration。
- **唯一迁移链：** 新 migration 必须以当前唯一 head `g1a2b3c4d5e6` 为 `down_revision`；开始实施前重新运行 `uv run alembic heads`，若 head 已变化，先将 `down_revision` 更新为新的唯一 head。
- **Python 版本：** 保持 `requires-python = ">=3.12"`，不增加第三方 ID、Schema 或事件库。
- **Runtime 兼容：** 继续使用 DeerFlow/LangGraph；不修改现有 API path、LangGraph graph、checkpointer、thread/run API 或 `deerflow` import。
- **P0 Task/Run 语义：** `task_id` 和 `run_id` 仅是稳定、不可复用的关联 ID；本计划不建立 Task/Run 表、生命周期、状态转换、恢复、取消或重试。
- **领域隔离：** `backend/app/platform/**` 不得 import `app.alerting`、`app.agent`、`app.services.terminal` 或 LangGraph 私有类型；AIOps 只能依赖平台契约，平台契约不能反向依赖 AIOps。
- **Tenant 不变量：** Resource、Identity、Execution、Audit 的 tenant 必须显式存在；跨 tenant 引用在模型验证阶段拒绝。
- **时间不变量：** 所有契约时间必须包含时区，序列化统一为 UTC；naive datetime 必须拒绝。
- **扩展规则：** 核心模型使用 `extra="forbid"`；领域扩展只能进入 `attributes`/`payload`，且不能成为核心必填字段。
- **兼容策略：** P0 不删除、不重命名、不改写 `backend/app/gateway/audit.py`、`audit/events.jsonl` 或 `terminal_audit_logs`；旧数据迁移默认 dry-run，只有显式 `--apply` 才写数据库。
- **安全边界：** P0 只定义 `policy_decision_id`、`approval_id` 等可选关联，不实现 allow/deny/require_approval 决策或 Approval 状态机。
- **质量基线：** 当前证据为 `1173 tests collected`，Tenant/Guardrail/Terminal Security 相邻测试为 `46 passed`；新增测试必须全部通过，已有测试失败不能因 P0 增加。
- **提交纪律：** 每项 Task 通过其局部测试后独立提交；并行分支不得共同修改同一文件，公共导出统一在 Task 4 汇合。

---

## File and Ownership Map

| Owner | Files | Responsibility |
|---|---|---|
| Contract Owner | `backend/app/platform/contracts/versioning.py`, `identifiers.py`, `types.py` | Schema version、ID、UTC、Tenant 基础不变量 |
| Resource Track | `backend/app/platform/contracts/resources.py` | ResourceMetadata 与三类稳定引用 |
| Execution Track | `backend/app/platform/contracts/execution.py` | P0 ExecutionEnvelope，不引入生命周期 |
| Audit Track | `backend/app/platform/contracts/audit.py` | AuditEvent 及公共 contract export |
| Persistence Track | `backend/app/models/governance.py`, Alembic migration, `backend/app/platform/audit/repository.py` | AuditEvent 最小持久化投影 |
| Compatibility Track | `backend/app/platform/audit/legacy.py`, `backend/scripts/migrate_audit_jsonl.py` | JSONL 兼容映射、dry-run/apply 迁移 |
| Scenario/Quality Track | `backend/tests/contracts/fixtures/aio_ops_action_v1.json`, contract tests | AIOps 解耦证明、架构与发布门 |

公共依赖只允许按以下方向流动：

```text
versioning + identifiers + types
           │
           ├── resources
           ├── execution ── resources
           └── audit ────── execution
                              │
                              ├── governance SQLModel + repository
                              ├── legacy JSONL adapter + migration tool
                              └── AIOps contract fixture/tests
```

## Parallel Execution Waves

| Wave | Parallel tasks | Merge gate |
|---|---|---|
| 0 | Task 1 only | ID、Version、UTC、Tenant tests green；Contract Owner freezes signatures |
| 1 | Task 2, Task 3, Task 4 contract body | Each track owns disjoint files；Task 4 owner merges public exports last |
| 2 | Task 5 and Task 7 | Audit contract merged；Task 5 alone owns model/migration |
| 3 | Task 6 | Persistence repository merged；migration tool tests green |
| 4 | Task 8 | All focused suites green；architecture and migration gates green |

---

### Task 1: Freeze contract version, identifiers, UTC and tenant primitives

**Files:**
- Create: `backend/app/platform/__init__.py`
- Create: `backend/app/platform/contracts/versioning.py`
- Create: `backend/app/platform/contracts/identifiers.py`
- Create: `backend/app/platform/contracts/types.py`
- Create: `backend/tests/contracts/__init__.py`
- Create: `backend/tests/contracts/conftest.py`
- Create: `backend/tests/contracts/test_foundation_types.py`

**Interfaces:**
- Produces: `PLATFORM_SCHEMA_V1`, `PlatformSchemaVersion`, `IdentifierKind`, `new_platform_id(kind)`, `stable_platform_id(kind, namespace, external_id)`, `TenantId`, `UtcDatetime`, `FrozenContractModel`.
- Consumed by: Tasks 2–7.

- [ ] **Step 1: Add failing tests for version, ID and UTC invariants**

Create `backend/tests/contracts/__init__.py` as an empty package marker, and create `backend/tests/contracts/conftest.py` so async contract tests use the installed asyncio backend rather than requiring Trio:

```python
import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
```

Then create `backend/tests/contracts/test_foundation_types.py`:

```python
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
```

- [ ] **Step 2: Run the test and confirm the missing package failure**

Run: `cd backend && uv run pytest tests/contracts/test_foundation_types.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'app.platform'`.

- [ ] **Step 3: Implement version and identifier primitives**

Create `backend/app/platform/__init__.py`:

```python
"""PrismOS platform-owned contracts and governance services."""
```

Create `backend/app/platform/contracts/versioning.py`:

```python
from typing import Literal

PLATFORM_SCHEMA_V1 = "prismos.platform/v1"
PlatformSchemaVersion = Literal["prismos.platform/v1"]
```

Create `backend/app/platform/contracts/identifiers.py`:

```python
from hashlib import sha256
from typing import Literal, cast
from uuid import uuid4

IdentifierKind = Literal["resource", "task", "run", "event"]


def _validate_source(value: str, name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be blank")
    return normalized


def new_platform_id(kind: IdentifierKind) -> str:
    return f"{kind}_{uuid4().hex}"


def stable_platform_id(
    kind: IdentifierKind,
    namespace: str,
    external_id: str,
) -> str:
    source = ":".join(
        (_validate_source(namespace, "namespace"), _validate_source(external_id, "external_id"))
    )
    digest = sha256(source.encode("utf-8")).hexdigest()[:32]
    return cast(str, f"{kind}_{digest}")
```

- [ ] **Step 4: Implement frozen contract and timezone-aware field types**

Create `backend/app/platform/contracts/types.py`:

```python
from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer


def _non_blank(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


def _timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


TenantId = Annotated[str, Field(min_length=1, max_length=255), AfterValidator(_non_blank)]
UtcDatetime = Annotated[
    datetime,
    AfterValidator(_timezone_aware),
    PlainSerializer(lambda value: value.isoformat().replace("+00:00", "Z"), return_type=str),
]


class FrozenContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
```

- [ ] **Step 5: Run focused tests and static lint**

Run: `cd backend && uv run pytest tests/contracts/test_foundation_types.py -q && uv run ruff check app/platform tests/contracts/test_foundation_types.py`

Expected: `8 passed` and Ruff exits 0.

- [ ] **Step 6: Commit the frozen primitives**

```bash
git add backend/app/platform backend/tests/contracts
git commit -m "feat: define platform contract primitives"
```

---

### Task 2: Define ResourceMetadata and stable references

**Files:**
- Create: `backend/app/platform/contracts/resources.py`
- Create: `backend/tests/contracts/test_resource_contracts.py`

**Interfaces:**
- Consumes: `TenantId`, `UtcDatetime`, `FrozenContractModel` from Task 1.
- Produces: `IdentityKind`, `IdentityRef`, `DefinitionRef`, `EnvironmentRef`, `ResourceMetadata`.
- Contract: every reference carries `tenant_id`; `ResourceMetadata` carries stable ID/type/version and UTC creation time; labels are bounded strings and annotations hold non-secret extension metadata.

- [ ] **Step 1: Write failing resource contract tests**

Create `backend/tests/contracts/test_resource_contracts.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run: `cd backend && uv run pytest tests/contracts/test_resource_contracts.py -q`

Expected: collection fails because `app.platform.contracts.resources` does not exist.

- [ ] **Step 3: Implement the resource and reference models**

Create `backend/app/platform/contracts/resources.py`:

```python
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
```

- [ ] **Step 4: Run focused tests and lint**

Run: `cd backend && uv run pytest tests/contracts/test_resource_contracts.py -q && uv run ruff check app/platform/contracts/resources.py tests/contracts/test_resource_contracts.py`

Expected: `6 passed` and Ruff exits 0.

- [ ] **Step 5: Commit without touching public exports**

```bash
git add backend/app/platform/contracts/resources.py backend/tests/contracts/test_resource_contracts.py
git commit -m "feat: define platform resource references"
```

---

### Task 3: Define the P0 ExecutionEnvelope without lifecycle semantics

**Files:**
- Create: `backend/app/platform/contracts/execution.py`
- Create: `backend/tests/contracts/test_execution_envelope.py`

**Interfaces:**
- Consumes: Task 1 primitives and Task 2 references.
- Produces: `ExecutionEnvelope`；领域扩展保存在 `attributes: dict[str, Any]`，不引入独立生命周期类型。
- Contract: required `tenant_id`, `task_id`, `run_id`, `workload`, `correlation_id`, `schema_version`, `occurred_at`; no status, attempt, retry, cancel or workflow fields.

- [ ] **Step 1: Write failing ExecutionEnvelope tests**

Create `backend/tests/contracts/test_execution_envelope.py`:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.resources import DefinitionRef, EnvironmentRef, IdentityRef


def _payload() -> dict:
    return {
        "schema_version": "prismos.platform/v1",
        "tenant_id": "tenant-a",
        "task_id": "task_0123456789abcdef0123456789abcdef",
        "run_id": "run_0123456789abcdef0123456789abcdef",
        "correlation_id": "alert-delivery-42",
        "workload": IdentityRef(kind="workload", id="agent-7", tenant_id="tenant-a"),
        "actor": IdentityRef(kind="user", id="user-9", tenant_id="tenant-a"),
        "definition": DefinitionRef(kind="agent", id="definition-4", version="3", tenant_id="tenant-a"),
        "environment": EnvironmentRef(kind="production", id="prod-cn", tenant_id="tenant-a"),
        "occurred_at": datetime(2026, 8, 8, 8, 30, tzinfo=UTC),
        "attributes": {"source": "contract-test"},
    }


def test_execution_envelope_round_trips_as_v1() -> None:
    envelope = ExecutionEnvelope.model_validate(_payload())
    restored = ExecutionEnvelope.model_validate_json(envelope.model_dump_json())
    assert restored == envelope
    assert restored.schema_version == "prismos.platform/v1"


@pytest.mark.parametrize("field", ["tenant_id", "task_id", "run_id", "correlation_id"])
def test_execution_envelope_requires_stable_context(field: str) -> None:
    payload = _payload()
    payload.pop(field)
    with pytest.raises(ValidationError):
        ExecutionEnvelope.model_validate(payload)


def test_execution_envelope_rejects_cross_tenant_refs() -> None:
    payload = _payload()
    payload["workload"] = IdentityRef(kind="workload", id="agent-7", tenant_id="tenant-b")
    with pytest.raises(ValidationError, match="same tenant"):
        ExecutionEnvelope.model_validate(payload)


def test_execution_envelope_has_no_m2_lifecycle_fields() -> None:
    required = set(ExecutionEnvelope.model_json_schema()["required"])
    forbidden = {"status", "attempt", "retry_count", "cancelled_at", "workflow_id"}
    assert required.isdisjoint(forbidden)
    with pytest.raises(ValidationError):
        ExecutionEnvelope.model_validate({**_payload(), "status": "running"})
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run: `cd backend && uv run pytest tests/contracts/test_execution_envelope.py -q`

Expected: collection fails because `app.platform.contracts.execution` does not exist.

- [ ] **Step 3: Implement tenant consistency and the immutable envelope**

Create `backend/app/platform/contracts/execution.py`:

```python
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
```

- [ ] **Step 4: Run focused tests and lint**

Run: `cd backend && uv run pytest tests/contracts/test_execution_envelope.py -q && uv run ruff check app/platform/contracts/execution.py tests/contracts/test_execution_envelope.py`

Expected: `7 passed` and Ruff exits 0.

- [ ] **Step 5: Commit the envelope independently**

```bash
git add backend/app/platform/contracts/execution.py backend/tests/contracts/test_execution_envelope.py
git commit -m "feat: define execution envelope contract"
```

---

### Task 4: Define AuditEvent and freeze the public contract API

**Files:**
- Create: `backend/app/platform/contracts/audit.py`
- Create: `backend/app/platform/contracts/__init__.py`
- Create: `backend/tests/contracts/test_audit_event.py`
- Create: `backend/tests/contracts/test_public_contract_api.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `AuditOutcome`, `AuditSeverity`, `AuditEvent`, and the only supported imports from `app.platform.contracts`.
- Contract: AuditEvent embeds one ExecutionEnvelope and optional opaque Policy/Approval references; it does not implement those resources.

- [ ] **Step 1: Write failing AuditEvent and public API tests**

Create `backend/tests/contracts/test_audit_event.py`:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.platform.contracts.audit import AuditEvent
from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.resources import IdentityRef


def _execution() -> ExecutionEnvelope:
    return ExecutionEnvelope(
        tenant_id="tenant-a",
        task_id="task_0123456789abcdef0123456789abcdef",
        run_id="run_0123456789abcdef0123456789abcdef",
        correlation_id="correlation-7",
        workload=IdentityRef(kind="workload", id="agent-7", tenant_id="tenant-a"),
        occurred_at=datetime(2026, 8, 8, 8, 30, tzinfo=UTC),
    )


def test_audit_event_carries_complete_execution_correlation() -> None:
    event = AuditEvent(
        tenant_id="tenant-a",
        event_id="event_0123456789abcdef0123456789abcdef",
        event_type="action.policy_evaluated",
        action="terminal.execute",
        outcome="pending",
        severity="info",
        execution=_execution(),
        policy_decision_id="decision-4",
        approval_id="approval-2",
        payload={"risk": "high"},
        recorded_at=datetime(2026, 8, 8, 8, 31, tzinfo=UTC),
    )
    assert event.tenant_id == "tenant-a"
    assert event.task_id == event.execution.task_id
    assert event.run_id == event.execution.run_id


def test_audit_event_rejects_wrong_schema_and_unknown_outcome() -> None:
    common = {
        "tenant_id": "tenant-a",
        "event_id": "event_0123456789abcdef0123456789abcdef",
        "event_type": "action.completed",
        "action": "terminal.execute",
        "severity": "info",
        "execution": _execution(),
        "recorded_at": datetime.now(UTC),
    }
    with pytest.raises(ValidationError):
        AuditEvent(**common, schema_version="prismos.platform/v2", outcome="succeeded")
    with pytest.raises(ValidationError):
        AuditEvent(**common, outcome="maybe")


def test_audit_event_rejects_cross_tenant_execution() -> None:
    with pytest.raises(ValidationError, match="same tenant"):
        AuditEvent(
            tenant_id="tenant-b",
            event_id="event_0123456789abcdef0123456789abcdef",
            event_type="action.completed",
            action="terminal.execute",
            outcome="succeeded",
            execution=_execution(),
            recorded_at=datetime.now(UTC),
        )
```

Create `backend/tests/contracts/test_public_contract_api.py`:

```python
def test_public_contract_api_exports_only_stable_foundation_types() -> None:
    from app.platform import contracts

    expected = {
        "PLATFORM_SCHEMA_V1",
        "AuditEvent",
        "DefinitionRef",
        "EnvironmentRef",
        "ExecutionEnvelope",
        "IdentityRef",
        "ResourceMetadata",
        "new_platform_id",
        "stable_platform_id",
    }
    assert set(contracts.__all__) == expected
    assert not hasattr(contracts, "Task")
    assert not hasattr(contracts, "Run")
    assert not hasattr(contracts, "Approval")
```

- [ ] **Step 2: Run tests and confirm AuditEvent/public exports are missing**

Run: `cd backend && uv run pytest tests/contracts/test_audit_event.py tests/contracts/test_public_contract_api.py -q`

Expected: collection fails because `app.platform.contracts.audit` and the public exports do not exist.

- [ ] **Step 3: Implement AuditEvent with derived correlation accessors**

Create `backend/app/platform/contracts/audit.py`:

```python
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
```

- [ ] **Step 4: Freeze the supported public imports after Tasks 2 and 3 merge**

Create `backend/app/platform/contracts/__init__.py`:

```python
from app.platform.contracts.audit import AuditEvent
from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.identifiers import new_platform_id, stable_platform_id
from app.platform.contracts.resources import DefinitionRef, EnvironmentRef, IdentityRef, ResourceMetadata
from app.platform.contracts.versioning import PLATFORM_SCHEMA_V1

__all__ = [
    "PLATFORM_SCHEMA_V1",
    "AuditEvent",
    "DefinitionRef",
    "EnvironmentRef",
    "ExecutionEnvelope",
    "IdentityRef",
    "ResourceMetadata",
    "new_platform_id",
    "stable_platform_id",
]
```

- [ ] **Step 5: Run all contract tests and lint**

Run: `cd backend && uv run pytest tests/contracts/test_foundation_types.py tests/contracts/test_resource_contracts.py tests/contracts/test_execution_envelope.py tests/contracts/test_audit_event.py tests/contracts/test_public_contract_api.py -q && uv run ruff check app/platform/contracts tests/contracts`

Expected: `25 passed` and Ruff exits 0.

- [ ] **Step 6: Commit the AuditEvent and public API freeze**

```bash
git add backend/app/platform/contracts backend/tests/contracts
git commit -m "feat: define audit event contract"
```

---

### Task 5: Add the minimal AuditEvent persistence projection and migration

**Files:**
- Create: `backend/app/models/governance.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/h2b3c4d5e6f7_add_platform_audit_events.py`
- Create: `backend/app/platform/audit/__init__.py`
- Create: `backend/app/platform/audit/repository.py`
- Create: `backend/tests/contracts/test_audit_repository.py`
- Create: `backend/tests/contracts/test_audit_migration.py`

**Interfaces:**
- Consumes: `AuditEvent` from Task 4 and existing `get_session_factory()` behavior.
- Produces: `PlatformAuditEventRecord`, `AuditEventRepository.append(event)`, `get(event_id, tenant_id)`, `list_recent(tenant_id, limit)`.
- Migration ownership: only this task creates or edits the Alembic revision.

- [ ] **Step 1: Reconfirm the single Alembic head before naming the migration**

Run: `cd backend && uv run alembic heads`

Expected at plan creation: exactly `g1a2b3c4d5e6 (head)`. If implementation starts after another migration lands, use that single new head as `down_revision` and keep the filename/revision ID unique.

- [ ] **Step 2: Write failing repository tests with an isolated SQLite database**

Create `backend/tests/contracts/test_audit_repository.py` with an async fixture that imports `PlatformAuditEventRecord`, creates SQLModel metadata in `sqlite+aiosqlite://`, and asserts:

```python
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformAuditEventRecord  # noqa: F401
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import AuditEvent, ExecutionEnvelope, IdentityRef


@pytest.fixture
async def audit_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield AuditEventRepository(factory)
    await engine.dispose()


def _event(event_id: str = "event_0123456789abcdef0123456789abcdef") -> AuditEvent:
    execution = ExecutionEnvelope(
        tenant_id="tenant-a",
        task_id="task_0123456789abcdef0123456789abcdef",
        run_id="run_0123456789abcdef0123456789abcdef",
        correlation_id="correlation-7",
        workload=IdentityRef(kind="workload", id="agent-7", tenant_id="tenant-a"),
        occurred_at=datetime(2026, 8, 8, 8, 30, tzinfo=UTC),
    )
    return AuditEvent(
        tenant_id="tenant-a",
        event_id=event_id,
        event_type="action.completed",
        action="terminal.execute",
        outcome="succeeded",
        execution=execution,
        recorded_at=datetime(2026, 8, 8, 8, 31, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_repository_round_trips_event(audit_repository) -> None:
    await audit_repository.append(_event())
    restored = await audit_repository.get(
        "event_0123456789abcdef0123456789abcdef",
        tenant_id="tenant-a",
    )
    assert restored == _event()


@pytest.mark.anyio
async def test_repository_is_tenant_scoped_and_idempotent(audit_repository) -> None:
    event = _event()
    await audit_repository.append(event)
    await audit_repository.append(event)
    assert await audit_repository.get(event.event_id, tenant_id="tenant-b") is None
    assert len(await audit_repository.list_recent("tenant-a", limit=10)) == 1


@pytest.mark.anyio
async def test_repository_rejects_reused_event_id_with_different_payload(
    audit_repository,
) -> None:
    event = _event()
    await audit_repository.append(event)
    with pytest.raises(ValueError, match="different payload"):
        await audit_repository.append(event.model_copy(update={"outcome": "failed"}))
```

- [ ] **Step 3: Run repository tests and confirm the missing model/repository failure**

Run: `cd backend && uv run pytest tests/contracts/test_audit_repository.py -q`

Expected: collection fails because `app.platform.audit.repository` does not exist.

- [ ] **Step 4: Implement the SQLModel projection**

Create `backend/app/models/governance.py`:

```python
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Index, String
from sqlmodel import Field, SQLModel


class PlatformAuditEventRecord(SQLModel, table=True):
    __tablename__ = "platform_audit_events"
    __table_args__ = (
        Index("ix_platform_audit_tenant_recorded", "tenant_id", "recorded_at"),
        Index("ix_platform_audit_tenant_run", "tenant_id", "run_id"),
    )

    id: str = Field(sa_column=Column(String(255), primary_key=True))
    schema_version: str = Field(sa_column=Column(String(64), nullable=False))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    event_type: str = Field(sa_column=Column(String(255), nullable=False))
    action: str = Field(sa_column=Column(String(255), nullable=False))
    outcome: str = Field(sa_column=Column(String(32), nullable=False))
    severity: str = Field(sa_column=Column(String(32), nullable=False))
    task_id: str = Field(sa_column=Column(String(255), nullable=False))
    run_id: str = Field(sa_column=Column(String(255), nullable=False))
    correlation_id: str = Field(sa_column=Column(String(255), nullable=False))
    policy_decision_id: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    approval_id: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    resource_id: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    event_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    occurred_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    recorded_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
```

Add the following import to `backend/app/models/__init__.py`:

```python
from app.models import governance as _governance_models  # noqa: F401
```

Add the same model registration to `backend/alembic/env.py` beside the existing `app.models` imports:

```python
from app.models import governance as _governance_models  # noqa: F401
```

- [ ] **Step 5: Implement the async repository with idempotent append**

Create `backend/app/platform/audit/__init__.py` without re-exporting persistence types, so importing the audit adapter does not initialize database modules:

```python
"""Audit persistence and compatibility adapters for platform contracts."""
```

Create `backend/app/platform/audit/repository.py` with:

```python
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformAuditEventRecord
from app.platform.contracts import AuditEvent
from deerflow.database.session import get_session_factory


class AuditEventRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()

    @staticmethod
    def _record(event: AuditEvent) -> PlatformAuditEventRecord:
        return PlatformAuditEventRecord(
            id=event.event_id,
            schema_version=event.schema_version,
            tenant_id=event.tenant_id,
            event_type=event.event_type,
            action=event.action,
            outcome=event.outcome,
            severity=event.severity,
            task_id=event.task_id,
            run_id=event.run_id,
            correlation_id=event.execution.correlation_id,
            policy_decision_id=event.policy_decision_id,
            approval_id=event.approval_id,
            resource_id=event.resource_id,
            event_json=event.model_dump(mode="json"),
            occurred_at=event.execution.occurred_at,
            recorded_at=event.recorded_at,
        )

    @staticmethod
    def _assert_same_event(
        record: PlatformAuditEventRecord,
        event: AuditEvent,
    ) -> None:
        if record.event_json != event.model_dump(mode="json"):
            raise ValueError("event_id already exists with different payload")

    async def append(self, event: AuditEvent) -> None:
        async with self._session_factory() as session:
            existing = await session.get(PlatformAuditEventRecord, event.event_id)
            if existing is not None:
                self._assert_same_event(existing, event)
                return
            session.add(self._record(event))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.get(PlatformAuditEventRecord, event.event_id)
                if existing is None:
                    raise
                self._assert_same_event(existing, event)

    async def get(self, event_id: str, tenant_id: str) -> AuditEvent | None:
        async with self._session_factory() as session:
            statement = select(PlatformAuditEventRecord).where(
                PlatformAuditEventRecord.id == event_id,
                PlatformAuditEventRecord.tenant_id == tenant_id,
            )
            row = (await session.execute(statement)).scalar_one_or_none()
            return None if row is None else AuditEvent.model_validate(row.event_json)

    async def list_recent(self, tenant_id: str, limit: int = 100) -> list[AuditEvent]:
        if limit <= 0:
            return []
        async with self._session_factory() as session:
            statement = (
                select(PlatformAuditEventRecord)
                .where(PlatformAuditEventRecord.tenant_id == tenant_id)
                .order_by(PlatformAuditEventRecord.recorded_at.desc())
                .limit(min(limit, 1000))
            )
            rows = (await session.execute(statement)).scalars().all()
            return [AuditEvent.model_validate(row.event_json) for row in rows]
```

- [ ] **Step 6: Create and test the single Alembic migration**

Create `backend/alembic/versions/h2b3c4d5e6f7_add_platform_audit_events.py`. If Step 1 found a head other than `g1a2b3c4d5e6`, replace only `down_revision` below and the matching test assertion with that verified single head:

```python
"""add platform audit events

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "h2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "g1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_audit_events",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("policy_decision_id", sa.String(length=255), nullable=True),
        sa.Column("approval_id", sa.String(length=255), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("event_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_audit_tenant_recorded",
        "platform_audit_events",
        ["tenant_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        "ix_platform_audit_tenant_run",
        "platform_audit_events",
        ["tenant_id", "run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_audit_tenant_run",
        table_name="platform_audit_events",
    )
    op.drop_index(
        "ix_platform_audit_tenant_recorded",
        table_name="platform_audit_events",
    )
    op.drop_table("platform_audit_events")
```

Create `backend/tests/contracts/test_audit_migration.py`:

```python
from pathlib import Path


def test_platform_audit_migration_extends_one_head() -> None:
    migration = Path(
        "alembic/versions/h2b3c4d5e6f7_add_platform_audit_events.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "h2b3c4d5e6f7"' in migration
    assert 'down_revision: str | Sequence[str] | None = "g1a2b3c4d5e6"' in migration
    assert 'op.create_table(' in migration
    assert '"platform_audit_events"' in migration
    assert '"ix_platform_audit_tenant_recorded"' in migration
    assert '"ix_platform_audit_tenant_run"' in migration
    assert 'op.drop_table("platform_audit_events")' in migration
```

Run: `cd backend && uv run pytest tests/contracts/test_audit_repository.py tests/contracts/test_audit_migration.py -q && uv run alembic heads`

Expected: `4 passed` and exactly `h2b3c4d5e6f7 (head)`.

- [ ] **Step 7: Verify upgrade/downgrade/upgrade on a temporary SQLite database**

Run with a temporary config/database path rather than the developer database:

```bash
cd backend
migration_dir="$(mktemp -d /tmp/prismos-p0-migration.XXXXXX)"
config_path="$migration_dir/config.yaml"
database_path="$migration_dir/audit.db"
trap 'rm -f "$config_path" "$database_path"; rmdir "$migration_dir" 2>/dev/null || true' EXIT
sed "s#sqlite+aiosqlite:///.prismos/tenant.db#sqlite+aiosqlite:///$database_path#" \
  ../config.example.yaml > "$config_path"
OPSINTECH_CONFIG_PATH="$config_path" uv run alembic upgrade head
OPSINTECH_CONFIG_PATH="$config_path" uv run alembic downgrade g1a2b3c4d5e6
OPSINTECH_CONFIG_PATH="$config_path" uv run alembic upgrade head
P0_DATABASE_PATH="$database_path" uv run python -c \
  'import os, sqlite3; db = sqlite3.connect(os.environ["P0_DATABASE_PATH"]); assert db.execute("select name from sqlite_master where type=\"table\" and name=\"platform_audit_events\"").fetchone()'
```

Expected: all four verification commands exit 0; the final temporary database contains `platform_audit_events`. Keep the existing `OPSINTECH_CONFIG_PATH` compatibility input because direct `AppConfig` loading does not resolve `PRISMOS_CONFIG_PATH`; do not point this verification at a user database.

- [ ] **Step 8: Commit persistence and its one migration**

```bash
git add backend/app/models backend/app/platform/audit backend/alembic backend/tests/contracts
git commit -m "feat: persist platform audit events"
```

---

### Task 6: Add legacy JSONL compatibility mapping and an explicit migration tool

**Files:**
- Create: `backend/app/platform/audit/legacy.py`
- Create: `backend/scripts/migrate_audit_jsonl.py`
- Create: `backend/tests/contracts/test_legacy_audit_adapter.py`
- Create: `backend/tests/contracts/test_audit_migration_script.py`

**Interfaces:**
- Consumes: `AuditEventRepository`, `AuditEvent`, stable ID helpers, existing JSONL fields from `app.gateway.audit`.
- Produces: `legacy_audit_to_event(row: dict[str, object], source_name: str, line_number: int, fallback_tenant_id: str | None = None) -> AuditEvent`, `MigrationSummary`, `migrate(source: Path, repository: AuditEventAppender, *, apply: bool, fallback_tenant_id: str | None) -> MigrationSummary`, CLI `--source`, `--apply`, `--tenant-id`.
- Compatibility rule: resolved tenant + source line + canonical JSON produces a deterministic event ID, so repeated migration is idempotent without creating cross-tenant ID collisions.

- [ ] **Step 1: Write failing adapter tests using the existing JSONL shape**

Create `backend/tests/contracts/test_legacy_audit_adapter.py`:

```python
import pytest

from app.platform.audit.legacy import legacy_audit_to_event


def test_legacy_gateway_event_maps_to_v1_contract_deterministically() -> None:
    row = {
        "ts": "2026-08-08T08:30:00Z",
        "event_type": "tenant.member.added",
        "severity": "info",
        "actor_id": "admin-1",
        "target_user_id": "user-2",
        "tenant_id": "tenant-a",
        "scope": "tenant",
        "metadata": {"role": "member"},
    }
    first = legacy_audit_to_event(row, "audit/events.jsonl", 7)
    second = legacy_audit_to_event(row, "audit/events.jsonl", 7)
    assert first == second
    assert first.tenant_id == "tenant-a"
    assert first.execution.attributes["legacy_source"] == "audit/events.jsonl"
    assert first.payload["target_user_id"] == "user-2"


def test_legacy_event_requires_explicit_fallback_tenant() -> None:
    row = {"ts": "2026-08-08T08:30:00Z", "event_type": "platform.started"}
    event = legacy_audit_to_event(
        row,
        "audit/events.jsonl",
        1,
        fallback_tenant_id="system-tenant",
    )
    assert event.tenant_id == "system-tenant"


def test_legacy_event_without_tenant_or_fallback_is_rejected() -> None:
    row = {"ts": "2026-08-08T08:30:00Z", "event_type": "platform.started"}
    with pytest.raises(ValueError, match="tenant_id"):
        legacy_audit_to_event(row, "audit/events.jsonl", 1)


def test_fallback_tenant_participates_in_deterministic_identity() -> None:
    row = {"ts": "2026-08-08T08:30:00Z", "event_type": "platform.started"}
    first = legacy_audit_to_event(
        row,
        "audit/events.jsonl",
        1,
        fallback_tenant_id="tenant-a",
    )
    second = legacy_audit_to_event(
        row,
        "audit/events.jsonl",
        1,
        fallback_tenant_id="tenant-b",
    )
    assert first.event_id != second.event_id
```

- [ ] **Step 2: Run tests and confirm the adapter is missing**

Run: `cd backend && uv run pytest tests/contracts/test_legacy_audit_adapter.py -q`

Expected: collection fails because `app.platform.audit.legacy` does not exist.

- [ ] **Step 3: Implement deterministic legacy conversion**

Create `backend/app/platform/audit/legacy.py`:

```python
import json
from datetime import datetime
from typing import cast

from app.platform.contracts import (
    AuditEvent,
    ExecutionEnvelope,
    IdentityRef,
    stable_platform_id,
)
from app.platform.contracts.audit import AuditSeverity

_AUDIT_SEVERITIES = {"debug", "info", "warning", "error", "critical"}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"legacy {field} must be a non-blank string")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("legacy optional text fields must be non-blank strings")
    return value.strip()


def legacy_audit_to_event(
    row: dict[str, object],
    source_name: str,
    line_number: int,
    fallback_tenant_id: str | None = None,
) -> AuditEvent:
    source = _required_text(source_name, "source_name")
    if line_number <= 0:
        raise ValueError("legacy line_number must be positive")

    timestamp = _required_text(row.get("ts"), "ts")
    occurred_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    event_type = _required_text(row.get("event_type"), "event_type")
    tenant_id = _optional_text(row.get("tenant_id")) or fallback_tenant_id
    if tenant_id is None:
        raise ValueError("legacy tenant_id is required unless a fallback is explicit")
    tenant_id = _required_text(tenant_id, "tenant_id")

    metadata = row.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("legacy metadata must be an object")

    canonical = json.dumps(
        row,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    source_identity = f"{tenant_id}:{source}:{line_number}:{canonical}"
    raw_severity = _optional_text(row.get("severity")) or "info"
    normalized_severity = raw_severity if raw_severity in _AUDIT_SEVERITIES else "warning"
    severity = cast(AuditSeverity, normalized_severity)

    payload: dict[str, object] = {
        "scope": row.get("scope"),
        "target_user_id": row.get("target_user_id"),
        "metadata": metadata,
    }
    if raw_severity != normalized_severity:
        payload["legacy_severity"] = raw_severity

    actor_id = _optional_text(row.get("actor_id"))
    actor = (
        IdentityRef(kind="user", id=actor_id, tenant_id=tenant_id)
        if actor_id is not None
        else None
    )
    execution = ExecutionEnvelope(
        tenant_id=tenant_id,
        task_id=stable_platform_id("task", "legacy-gateway-audit", source_identity),
        run_id=stable_platform_id("run", "legacy-gateway-audit", source_identity),
        correlation_id=f"legacy:{source}:{line_number}",
        workload=IdentityRef(
            kind="system",
            id="legacy-gateway-audit",
            tenant_id=tenant_id,
        ),
        actor=actor,
        occurred_at=occurred_at,
        attributes={"legacy_source": source, "legacy_line": line_number},
    )
    return AuditEvent(
        tenant_id=tenant_id,
        event_id=stable_platform_id("event", "legacy-gateway-audit", source_identity),
        event_type=event_type,
        action="legacy.audit",
        outcome="succeeded",
        severity=severity,
        execution=execution,
        payload=payload,
        recorded_at=occurred_at,
    )
```

- [ ] **Step 4: Write migration script tests for dry-run and apply**

Create `backend/tests/contracts/test_audit_migration_script.py`:

```python
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from scripts.migrate_audit_jsonl import MigrationSummary, migrate

LEGACY_EVENT = {
    "ts": "2026-08-08T08:30:00Z",
    "event_type": "tenant.member.added",
    "severity": "info",
    "tenant_id": "tenant-a",
    "metadata": {},
}


@pytest.mark.anyio
async def test_migration_dry_run_does_not_append(tmp_path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps(LEGACY_EVENT) + "\n", encoding="utf-8")
    repository = AsyncMock()
    summary = await migrate(source, repository, apply=False, fallback_tenant_id=None)
    assert summary == MigrationSummary(scanned=1, valid=1, written=0, invalid=0)
    repository.append.assert_not_awaited()


@pytest.mark.anyio
async def test_migration_apply_appends_valid_rows_and_counts_invalid(tmp_path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps(LEGACY_EVENT) + "\n{broken-json}\n", encoding="utf-8")
    repository = AsyncMock()
    summary = await migrate(source, repository, apply=True, fallback_tenant_id=None)
    assert summary == MigrationSummary(scanned=2, valid=1, written=1, invalid=1)
    repository.append.assert_awaited_once()


def test_cli_defaults_to_dry_run_without_database_config(tmp_path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps(LEGACY_EVENT) + "\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[2] / "scripts" / "migrate_audit_jsonl.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--source", str(source)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "invalid": 0,
        "scanned": 1,
        "valid": 1,
        "written": 0,
    }
```

- [ ] **Step 5: Implement a safe-by-default migration CLI**

Create `backend/scripts/migrate_audit_jsonl.py` with:

```python
import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.platform.audit.legacy import legacy_audit_to_event  # noqa: E402
from app.platform.audit.repository import AuditEventRepository  # noqa: E402
from app.platform.contracts import AuditEvent  # noqa: E402


class AuditEventAppender(Protocol):
    async def append(self, event: AuditEvent) -> None:
        pass


class _DryRunAppender:
    async def append(self, event: AuditEvent) -> None:
        raise AssertionError("dry-run must not append audit events")


@dataclass(frozen=True)
class MigrationSummary:
    scanned: int
    valid: int
    written: int
    invalid: int


async def migrate(
    source: Path,
    repository: AuditEventAppender,
    *,
    apply: bool,
    fallback_tenant_id: str | None,
) -> MigrationSummary:
    scanned = valid = written = invalid = 0
    with source.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            scanned += 1
            try:
                decoded = json.loads(stripped)
                if not isinstance(decoded, dict):
                    raise ValueError("legacy audit row must be a JSON object")
                event = legacy_audit_to_event(
                    decoded,
                    str(source),
                    line_number,
                    fallback_tenant_id=fallback_tenant_id,
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                invalid += 1
                print(f"invalid legacy audit line: {line_number}", file=sys.stderr)
                continue

            valid += 1
            if apply:
                await repository.append(event)
                written += 1

    return MigrationSummary(
        scanned=scanned,
        valid=valid,
        written=written,
        invalid=invalid,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy JSONL audit events")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--tenant-id", dest="fallback_tenant_id")
    args = parser.parse_args(argv)
    if not args.source.is_file():
        parser.error("--source must reference an existing file")
    return args


async def _run(args: argparse.Namespace) -> int:
    repository: AuditEventAppender
    repository = AuditEventRepository() if args.apply else _DryRunAppender()
    summary = await migrate(
        args.source,
        repository,
        apply=args.apply,
        fallback_tenant_id=args.fallback_tenant_id,
    )
    print(json.dumps(asdict(summary), sort_keys=True))
    return 2 if summary.invalid else 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
```

The dry-run path deliberately uses `_DryRunAppender`, so validation does not load database configuration. `--tenant-id` supplies only the fallback for legacy rows without tenant context.

- [ ] **Step 6: Verify adapters, CLI behavior and unchanged legacy writer**

Run:

```bash
cd backend
uv run pytest tests/contracts/test_legacy_audit_adapter.py tests/contracts/test_audit_migration_script.py -q
sample_file="$(mktemp /tmp/prismos-p0-audit-sample.XXXXXX)"
trap 'rm -f "$sample_file"' EXIT
printf '%s\n' '{"ts":"2026-08-08T08:30:00Z","event_type":"platform.started","tenant_id":"tenant-a"}' > "$sample_file"
uv run python scripts/migrate_audit_jsonl.py --source "$sample_file"
git diff --exit-code -- app/gateway/audit.py
```

Expected: `7 passed`; CLI exits 0 and reports `"written": 0` without `--apply`; `app/gateway/audit.py` has no diff.

- [ ] **Step 7: Commit compatibility without activating dual write**

```bash
git add backend/app/platform/audit/legacy.py backend/scripts/migrate_audit_jsonl.py backend/tests/contracts
git commit -m "feat: map legacy audit events to platform contracts"
```

---

### Task 7: Establish the AIOps Golden Scenario contract baseline

**Files:**
- Create: `backend/tests/contracts/fixtures/aio_ops_action_v1.json`
- Create: `backend/tests/contracts/test_aio_ops_golden_contract.py`
- Create: `backend/tests/contracts/test_platform_architecture.py`

**Interfaces:**
- Consumes: public exports from Task 4.
- Produces: a reviewable v1 fixture proving an AIOps action can use the generic core, plus architecture tests preventing reverse dependencies.
- This task creates no production AIOps adapter and modifies no `app.alerting` code.

- [ ] **Step 1: Add one complete AIOps action fixture using only generic fields**

Create `backend/tests/contracts/fixtures/aio_ops_action_v1.json` with this shape and fixed values:

```json
{
  "schema_version": "prismos.platform/v1",
  "tenant_id": "tenant-golden",
  "event_id": "event_1fca8dd66c904e65aa4a880530ef7298",
  "event_type": "action.policy_evaluated",
  "action": "terminal.execute",
  "outcome": "pending",
  "severity": "warning",
  "execution": {
    "schema_version": "prismos.platform/v1",
    "tenant_id": "tenant-golden",
    "task_id": "task_a9f3697ce9ec4ae3b2e2776127f18b12",
    "run_id": "run_06562d595bc948c1abe4a296e2cbb928",
    "correlation_id": "alert-delivery-42",
    "workload": {
      "kind": "workload",
      "id": "diagnosis-agent-v1",
      "tenant_id": "tenant-golden"
    },
    "actor": {
      "kind": "system",
      "id": "alert-ingest",
      "tenant_id": "tenant-golden"
    },
    "definition": {
      "kind": "agent",
      "id": "diagnosis-agent",
      "version": "1",
      "tenant_id": "tenant-golden"
    },
    "environment": {
      "kind": "production",
      "id": "golden-prod",
      "tenant_id": "tenant-golden"
    },
    "occurred_at": "2026-08-08T08:30:00Z",
    "attributes": {
      "domain": "aio_ops",
      "external_incident_id": "incident-42",
      "risk_level": "high"
    }
  },
  "policy_decision_id": "decision-golden-42",
  "approval_id": null,
  "resource_id": "asset-server-7",
  "payload": {
    "tool_name": "terminal.execute",
    "command_class": "service_restart"
  },
  "recorded_at": "2026-08-08T08:30:01Z"
}
```

- [ ] **Step 2: Write contract and domain-neutrality assertions**

Create `backend/tests/contracts/test_aio_ops_golden_contract.py`:

```python
import json
from pathlib import Path

from app.platform.contracts import AuditEvent, ExecutionEnvelope

FIXTURE = Path(__file__).parent / "fixtures" / "aio_ops_action_v1.json"


def test_aio_ops_fixture_validates_and_round_trips() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    event = AuditEvent.model_validate(payload)
    assert AuditEvent.model_validate_json(event.model_dump_json()) == event
    assert event.execution.attributes["external_incident_id"] == "incident-42"


def test_core_required_fields_are_not_aio_ops_specific() -> None:
    audit_required = set(AuditEvent.model_json_schema()["required"])
    execution_required = set(ExecutionEnvelope.model_json_schema()["required"])
    domain_fields = {
        "incident_id",
        "alert_id",
        "asset_id",
        "command",
        "diagnosis",
        "severity_label",
    }
    assert audit_required.isdisjoint(domain_fields)
    assert execution_required.isdisjoint(domain_fields)
```

- [ ] **Step 3: Add architecture tests against core-to-domain imports**

Create `backend/tests/contracts/test_platform_architecture.py`:

```python
import ast
from pathlib import Path

PLATFORM_ROOT = Path("app/platform")
FORBIDDEN_PREFIXES = (
    "app.alerting",
    "app.agent",
    "app.services.terminal",
    "langgraph",
)


def test_platform_core_does_not_import_domain_or_runtime_private_modules() -> None:
    violations: list[str] = []
    for path in PLATFORM_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.startswith(FORBIDDEN_PREFIXES):
                    violations.append(f"{path}:{node.lineno}:{name}")
    assert violations == []
```

- [ ] **Step 4: Run Golden Scenario and architecture tests**

Run: `cd backend && uv run pytest tests/contracts/test_aio_ops_golden_contract.py tests/contracts/test_platform_architecture.py -q`

Expected: `3 passed`.

- [ ] **Step 5: Run the same fixture with the AIOps plugin disabled at the contract layer**

Run: `cd backend && PRISMOS_PLUGIN_OPS_ALERTING=false uv run pytest tests/contracts/test_aio_ops_golden_contract.py -q`

Expected: `2 passed`; importing and validating core contracts does not initialize `app.alerting`.

- [ ] **Step 6: Commit the Golden Scenario evidence**

```bash
git add backend/tests/contracts
git commit -m "test: establish AIOps platform contract baseline"
```

---

### Task 8: Add release gates, document the frozen boundary and record the baseline

**Files:**
- Create: `backend/docs/PLATFORM_CONTRACTS.md`
- Create: `scripts/test-platform-contracts.sh`
- Modify: `README.md`
- Modify: `README_zh.md`
- Verify: `docs/superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: one reproducible P0 gate and documentation that distinguishes “contract baseline” from complete M1/M2 capabilities.

- [ ] **Step 1: Document the v1 contract and explicit non-capabilities**

Create `backend/docs/PLATFORM_CONTRACTS.md` with this initial content; Step 7 replaces the verification section with the measured output from this implementation:

````markdown
# PrismOS Platform Contract Baseline

**Status:** M1/P0 contract baseline implemented; governed execution is not yet complete.

## Supported API

Only these imports from `app.platform.contracts` are public in v1:

```python
from app.platform.contracts import (
    PLATFORM_SCHEMA_V1,
    AuditEvent,
    DefinitionRef,
    EnvironmentRef,
    ExecutionEnvelope,
    IdentityRef,
    ResourceMetadata,
    new_platform_id,
    stable_platform_id,
)
```

Private modules and persistence classes are not compatibility promises.

## Contract example

The complete review fixture is
`tests/contracts/fixtures/aio_ops_action_v1.json`. Its platform-owned shape is:

```json
{
  "schema_version": "prismos.platform/v1",
  "tenant_id": "tenant-golden",
  "event_id": "event_1fca8dd66c904e65aa4a880530ef7298",
  "event_type": "action.policy_evaluated",
  "action": "terminal.execute",
  "outcome": "pending",
  "severity": "warning",
  "execution": {
    "schema_version": "prismos.platform/v1",
    "tenant_id": "tenant-golden",
    "task_id": "task_a9f3697ce9ec4ae3b2e2776127f18b12",
    "run_id": "run_06562d595bc948c1abe4a296e2cbb928",
    "correlation_id": "alert-delivery-42",
    "workload": {
      "kind": "workload",
      "id": "diagnosis-agent-v1",
      "tenant_id": "tenant-golden"
    },
    "occurred_at": "2026-08-08T08:30:00Z",
    "attributes": {"domain": "aio_ops"}
  },
  "payload": {"tool_name": "terminal.execute"},
  "recorded_at": "2026-08-08T08:30:01Z"
}
```

The AIOps values are extension data and do not define core required fields.

## Invariants

- Writers emit `prismos.platform/v1`; v1 readers reject unknown schema strings.
- IDs are opaque, kind-prefixed and never reusable for different content.
- `stable_platform_id` is reserved for deterministic legacy or external correlation.
- Resource, identity, execution and audit objects carry an explicit tenant.
- Cross-tenant references fail validation.
- Datetimes require a timezone and serialize as UTC with a `Z` suffix.
- Unknown top-level fields fail validation.
- Domain data belongs only in `attributes` or `payload`. Neither field may contain secrets.

## Explicit non-capabilities

P0 does not implement a Policy engine, Approval lifecycle, Task/Run lifecycle,
Workflow, retry, cancellation, recovery or Evaluation resource. `task_id`,
`run_id`, `policy_decision_id` and `approval_id` are correlation references only.

## Legacy JSONL migration

Validate without database writes:

```bash
cd backend
uv run python scripts/migrate_audit_jsonl.py --source .prismos/audit/events.jsonl
```

Write valid rows after reviewing the summary and backing up the database:

```bash
cd backend
uv run python scripts/migrate_audit_jsonl.py \
  --source .prismos/audit/events.jsonl \
  --tenant-id system-tenant \
  --apply
```

The existing JSONL writer remains active and unchanged. Downgrade exports or backs
up new records first, removes only `platform_audit_events`, and never rewrites or
deletes the legacy JSONL file.

## Verification evidence

This section is written from fresh command output in the release-gate task. It
records the date, tested commit, exact focused-test counts, collection count,
single Alembic head and whether the full backend suite was executed.
````

Insert after the introductory blockquote in `README.md`:

```markdown
## Platform contract status

M1/P0 contract baseline implemented; governed execution is not yet complete.
See [Platform Contract Baseline](./backend/docs/PLATFORM_CONTRACTS.md) for the
frozen v1 boundary, migration guidance, verification evidence, and explicit
non-capabilities.
```

Insert at the corresponding location in `README_zh.md`:

```markdown
## 平台契约状态

M1/P0 契约基线已实现；可治理执行闭环尚未完成。冻结的 v1 边界、迁移指引、
验证证据和明确的非能力范围见[平台契约基线](./backend/docs/PLATFORM_CONTRACTS.md)。
```

- [ ] **Step 2: Add a narrow executable release gate**

Create executable `scripts/test-platform-contracts.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root/backend"

uv run pytest tests/contracts -q
uv run pytest \
  tests/test_authorization_tenant_context.py \
  tests/test_guardrail_middleware.py \
  tests/test_terminal_security.py -q
alembic_heads="$(uv run alembic heads)"
printf '%s\n' "$alembic_heads"
head_count="$(printf '%s\n' "$alembic_heads" | awk '/\(head\)$/ {count++} END {print count + 0}')"
if [[ "$head_count" -ne 1 ]]; then
  printf 'expected exactly one Alembic head, found %s\n' "$head_count" >&2
  exit 1
fi
uv run ruff check app/platform app/models/governance.py tests/contracts
```

Run `chmod +x scripts/test-platform-contracts.sh` after creating the file.

- [ ] **Step 3: Verify the approved Roadmap staffing boundary remains intact**

Run:

```bash
rg -n "1–2 名核心开发者为持续规划基线|M1 可采用 4–5 名核心贡献者|不授权把 M2/M3 范围提前带入 M1" \
  docs/superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md
git diff --exit-code -- docs/superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md
```

Expected: all three approved staffing/boundary phrases are present and the Roadmap has no implementation-time diff. The planning commit already records the 4–5 contributor acceleration scenario while preserving the 1–2 contributor sustainable baseline; Task 8 must not append a duplicate note, change M1–M3 definitions, or mark M1 complete.

- [ ] **Step 4: Run the P0 gate and collection baseline**

Run:

```bash
./scripts/test-platform-contracts.sh
cd backend && uv run pytest --collect-only -q
```

Expected: all contract and adjacent tests pass; collection succeeds with at least the existing 1173 collected tests plus the new contract tests. Record the exact pytest summaries from stdout for Step 7; do not infer counts from the number of test functions in this plan.

- [ ] **Step 5: Run migration and repository focused verification once more**

Run: `cd backend && uv run pytest tests/contracts/test_audit_repository.py tests/contracts/test_audit_migration.py tests/contracts/test_audit_migration_script.py -q`

Expected: all focused persistence/migration tests pass and no network service is required. Record the exact pytest summary for Step 7.

- [ ] **Step 6: Run compatibility and formatting checks**

Run:

```bash
git diff --check
git diff --exit-code -- backend/app/gateway/audit.py backend/app/models/terminal.py
rg -n "from app\.(alerting|agent|services\.terminal)|from langgraph|import langgraph" backend/app/platform
rg -n "TB[D]|TO[D]O|FIXM[E]|XX[X]|待定" backend/app/platform backend/docs/PLATFORM_CONTRACTS.md backend/tests/contracts
```

Expected: the first two commands exit 0; both `rg` commands return no matches and therefore exit 1.

- [ ] **Step 7: Record honest verification evidence**

Capture evidence directly from fresh commands rather than memory:

```bash
set -euo pipefail
evidence_dir="$(mktemp -d /tmp/prismos-p0-evidence.XXXXXX)"
trap 'rm -f "$evidence_dir"/*.log; rmdir "$evidence_dir" 2>/dev/null || true' EXIT
git rev-parse HEAD > "$evidence_dir/base-commit.log"
cd backend
uv run pytest tests/contracts -q | tee "$evidence_dir/contracts.log"
uv run pytest \
  tests/test_authorization_tenant_context.py \
  tests/test_guardrail_middleware.py \
  tests/test_terminal_security.py -q | tee "$evidence_dir/adjacent.log"
uv run pytest \
  tests/contracts/test_audit_repository.py \
  tests/contracts/test_audit_migration.py \
  tests/contracts/test_audit_migration_script.py -q | tee "$evidence_dir/persistence.log"
uv run pytest --collect-only -q | tee "$evidence_dir/collection.log"
uv run alembic heads | tee "$evidence_dir/alembic.log"
P0_EVIDENCE_DIR="$evidence_dir" uv run python - <<'PY'
import os
from pathlib import Path

evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
document = Path("docs/PLATFORM_CONTRACTS.md")
text = document.read_text(encoding="utf-8")
marker = """This section is written from fresh command output in the release-gate task. It
records the date, tested commit, exact focused-test counts, collection count,
single Alembic head and whether the full backend suite was executed."""


def last_line(filename: str) -> str:
    lines = (evidence_dir / filename).read_text(encoding="utf-8").splitlines()
    return lines[-1]


table = "\n".join(
    (
        "| Evidence | Result |",
        "| --- | --- |",
        "| Date | 2026-08-08 |",
        f"| Base commit under test | `{last_line('base-commit.log')}` |",
        f"| Contract suite | `{last_line('contracts.log')}` |",
        f"| Adjacent Tenant/Guardrail/Terminal suite | `{last_line('adjacent.log')}` |",
        f"| Persistence/migration suite | `{last_line('persistence.log')}` |",
        f"| Collection | `{last_line('collection.log')}` |",
        f"| Alembic | `{last_line('alembic.log')}` |",
        "| Full backend suite | Not executed in P0 gate; collection and focused suites only. |",
    )
)
if marker not in text:
    raise SystemExit("verification evidence marker not found")
document.write_text(text.replace(marker, table), encoding="utf-8")
PY
```

Expected: every command exits 0 and the marker paragraph becomes a table containing the literal final summary line from each command. The table calls the SHA the base commit because Task 8 documentation and gate changes are not committed yet. Do not translate “collected” into “passed”. If the full backend suite is also run, replace the final row with its exact summary.

- [ ] **Step 8: Commit documentation and the release gate**

```bash
git add backend/docs/PLATFORM_CONTRACTS.md scripts/test-platform-contracts.sh README.md README_zh.md
git commit -m "docs: freeze governed foundation contract baseline"
```

---

## Final P0 Review Gate

Before P0 is declared complete, the Contract Owner must verify all of the following from a clean worktree:

- `app.platform.contracts` exports exactly the nine approved public symbols;
- the core package contains no AIOps, Terminal or LangGraph private imports;
- all contract models reject extra top-level fields and cross-tenant references;
- all serialized datetimes are UTC and naive datetimes fail validation;
- `task_id`/`run_id` remain correlation-only and no lifecycle model/table has appeared;
- `platform_audit_events` is the only new table and Alembic has exactly one head;
- JSONL migration is dry-run by default, deterministic and idempotent;
- `backend/app/gateway/audit.py` and `terminal_audit_logs` remain compatible and unchanged;
- AIOps fixture validates while the AIOps plugin is disabled;
- focused tests, adjacent 46-test baseline, Ruff, migration cycle, collection and `git diff --check` have current evidence;
- status documentation says P0 contract baseline, not “M1 governed execution complete”.

## Commit Sequence

1. `feat: define platform contract primitives`
2. `feat: define platform resource references`
3. `feat: define execution envelope contract`
4. `feat: define audit event contract`
5. `feat: persist platform audit events`
6. `feat: map legacy audit events to platform contracts`
7. `test: establish AIOps platform contract baseline`
8. `docs: freeze governed foundation contract baseline`

## P0 Exit Result and Next Boundary

P0 exits only when the v1 contracts, AuditEvent persistence, compatibility tooling and AIOps contract fixture pass the Final P0 Review Gate. The next design package may then implement the M1 governed action path—PolicyRequest/PolicyDecision, Approval Primitive, durable decision/audit-before-side-effect ordering and adapters—using these frozen contracts.

P0 completion does not authorize Task/Run lifecycle work. M2 starts only after the complete M1 exit gate in the Capability Roadmap passes.
