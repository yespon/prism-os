# PrismOS Platform Contract Baseline

**Status:** P0 baseline and M1 Policy/Approval contracts, deterministic evaluation, and atomic fact recording implemented; governed execution is not yet complete.

## Supported API

The original nine P0 imports remain stable. M1 adds five contract-only symbols:

```python
from app.platform.contracts import (
    PLATFORM_SCHEMA_V1,
    ActionContextInput,
    Approval,
    AuditEvent,
    DefinitionRef,
    EnvironmentRef,
    ExecutionEnvelope,
    IdentityRef,
    PolicyDecision,
    PolicyRequest,
    ResourceMetadata,
    hash_action_context,
    new_platform_id,
    stable_platform_id,
)
```

`ActionContextInput` is transient: its `parameters` are excluded from serialization.
`hash_action_context` includes the validated parameters in a canonical SHA-256
digest. Adapters must pass only approved nonsecret facts; key checks cannot infer
whether an arbitrary value is a credential. Policy and Approval models describe
facts; importing them does not enable evaluation, approval authorization or enforcement.
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

The current checkout does not implement an authenticated Approval API,
governed Action dispatcher, Task/Run lifecycle, Workflow, retry,
cancellation, recovery or Evaluation resource. PolicyDecision and Approval now
have independent tenant-scoped stores; Approval state updates use compare-and-swap.
The internal `PolicyFactWriter` records a Decision, its critical AuditEvent,
and an optional pending Approval in one transaction. It is not connected to an
authenticated Action dispatcher. The internal evaluator uses explicit versioned
rules and fails closed, but no existing Tool is yet forced through it.
`task_id` and `run_id` remain correlation references only. An AuditEvent
carrying `policy_decision_id` or `approval_id` does not by itself prove that
the related fact was persisted.

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

## P0 verification evidence at completion

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
