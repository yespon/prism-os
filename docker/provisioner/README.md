# PrismOS scoped command provisioner

The remote Provider now uses authenticated finite command leases. The previous
`/api/sandboxes` endpoints return 503: their global resource mounts and unscoped
thread paths do not satisfy current resource authority. Their old NodePort
behavior is retained in Git history, not exposed as a working scoped runtime.

The new path is integrated with the original resource materialization and live
Tenant/member/Agent/source checks. Local Docker behavior remains available.
Remote Browser/interactive sandbox sessions, Apple runtime and real Kubernetes
acceptance retain separate pending exits. Protocol tests using a fake Kubernetes
API are not real cluster execution evidence.

## Configuration

Backend configuration uses references, never credential values:

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  provisioner_url: https://sandbox-provisioner.example
  provisioner_token_env: PRISMOS_PROVISIONER_TOKEN
  provisioner_shared_root: /absolute/backend-data
```

The credential environment variable must contain at least 32 characters. The
provisioner reads `PRISMOS_PROVISIONER_TOKEN`. Use TLS termination for non-loopback
connections; the client verifies certificates and rejects redirects. HTTP is
accepted only for loopback development probes. No deployment is performed by
these changes.

Provisioner environment:

| Setting | Required meaning |
| --- | --- |
| PRISMOS_SCOPED_DATA_ROOT | Existing absolute shared-data root visible inside the provisioner; aliases and `/` are rejected |
| PRISMOS_SCOPED_NODE_ROOT | Absolute path to that same filesystem on the selected Kubernetes node |
| PRISMOS_SCOPED_NODE | Explicit `kubernetes.io/hostname` label of that node |
| PRISMOS_SCOPED_IMAGE | Fully qualified image pinned with `@sha256:` and a 64-digit digest |
| PRISMOS_PROVISIONER_TOKEN | Service credential injected through the deployment's secret mechanism |
| KUBECONFIG_PATH | Existing kubeconfig file, or in-cluster configuration when absent |
| K8S_NAMESPACE | Namespace managed by the provisioner |

The configured data mapping must refer to the same underlying files. The backend,
provisioner and node must be able to access owned temporary resource views and
thread directories with the command UID/GID. A copied directory or a different
node filesystem is not an accepted mapping. Admission validates existing paths;
real cluster acceptance must verify mapping, readonly resources, permissions,
revocation, actual child-process termination and cleanup.

The provisioner requires namespace-scoped Pod create/get/delete/log access and
ConfigMap create/get/update and Pod patch access, in addition to existing startup namespace
inspection. Command Pods receive no service account token and expose no Service
or NodePort. Host directories are exactly the current resource view (readonly)
and current workspace/uploads/outputs (read/write). The root filesystem is
readonly, capabilities are dropped, privilege escalation is disabled, and finite
CPU/memory/storage/deadline limits apply. No configured host environment, global
Skills root or extra mount is inherited.

## Lease semantics

`POST /api/scoped-commands` accepts a new random lease ID, exact relative mounts,
command, explicit environment, UID/GID and a maximum 600-second timeout. All
endpoints require the service bearer credential. GET and DELETE additionally
require `X-Prismos-Contract`, the SHA-256 of canonical request JSON.

A namespace ConfigMap records the contract and publication/cancellation facts.
Atomic creation and resourceVersion updates prevent duplicate dispatch across
workers and restarts. A lost submission response is inspected and cancelled;
the client never repeats POST. Cancellation before submission leaves a tombstone
that blocks late dispatch. Missing Pods while dispatch is in flight do not prove
termination. Unknown publication remains an inspection item.

Observation and cleanup validate labels, contract and Pod UID. Log delivery
rechecks the UID after reading. DELETE uses normal graceful deletion with UID preconditions. A command finalizer
holds the Pod until kubelet container termination is recorded in its receipt; only
then is that finalizer removed with UID/resourceVersion tests. Object disappearance
without the terminal fact remains unknown, including force deletion on an
unreachable node. No dispatch may remain in flight. Finite
command receipts remain for inspection; do not delete an unresolved receipt or
reuse a lease ID. Retention cleanup is an operator action after resolving the
recorded operation, not automatic business retry or N08 persistent execution.

Backend live-authority checks run before dispatch, around each observation and
before delivery; withdrawal discards output and requests cleanup. Network calls
have bounded timeouts; unconfirmed cancellation is reported as unknown and must
not be treated as successful interruption or replay permission.

`GET /health` is process health only. It does not certify node mapping, image
availability, current permission or real execution. Original Policy, Approval,
Action and Audit remain authoritative above this deployment adapter.

When an existing cluster is configured, run the opt-in probe from the locked
backend environment:

```bash
.venv/bin/python ../scripts/octop_remote_smoke.py \
  --url https://sandbox-provisioner.example \
  --shared-root /absolute/backend-data \
  --output /absolute/evidence/remote-command.json
```

It creates unique owned directories, verifies readonly selected input and actual
owned output, waits for a command-start marker, then withdraws authority and checks
that a child cannot write later. It preserves directories on unknown outcomes.
Its receipt cannot claim real model, external tool or ticket acceptance.

The provisioner builds from the complete pinned dependency set in requirements.lock. Dependency updates require a new image and protocol/admission regression.
