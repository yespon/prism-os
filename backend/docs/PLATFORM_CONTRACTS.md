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

| Evidence | Result |
| --- | --- |
| Date | 2026-09-24 |
| Base commit under test | `58a01a2937ab9db33e4d95f1375f89c923fd465e` |
| Contract suite | `39 passed in 2.95s` |
| Adjacent Tenant/Guardrail/Terminal suite | `48 passed in 2.68s` |
| Persistence/migration suite | `7 passed in 4.32s` |
| Collection | `1257 tests collected in 9.56s` |
| Alembic | `h2b3c4d5e6f7 (head)` |
| Full backend suite | Not executed in P0 gate; collection and focused suites only. |
