# External SDK compatibility worker

This is an explicitly invoked local compatibility sandbox. It is not registered
as a PrismOS execution worker. The host dependency lock and SDK remain unchanged.

`octop_worker_compat.py` first verifies the retained external manifests and bytes.
It copies the three original MIT wheels and only the already filtered Harness
source plus its license. The excluded 51 Harness members and 186 main Office
members remain excluded. Harness is **source only**, not an official installed
distribution: its actual runtime version is `0.0.0+unknown`; source version 1.0.1
and the retained archive/member hashes are recorded separately.

Dependencies are wheel-only, hash pinned, and constrained by unique versions in
the retained upstream lock. The current worker uses langchain-mcp-adapters 0.3.0,
MCP 1.28.1 and Deep Agents 0.7.9; the host retains adapter 0.2.1 and MCP 1.29.0.
A future changed source requirement or unique upstream version that conflicts
with the reviewed worker lock fails preparation. Re-resolve/review the worker
lock separately; do not resolve external SDK dependencies into the host lock.

Run from the repository root after installing the locked backend:

```sh
backend/.venv/bin/python scripts/octop_worker_compat.py --output-dir "$PWD/backend/tmp/octop-worker-local"
docker build -t prismos-octop-worker-compat:local backend/tmp/octop-worker-local
image_id=$(docker image inspect prismos-octop-worker-compat:local --format '{{.Id}}')
backend/.venv/bin/python scripts/octop_worker_probe.py --image "$image_id" --output /tmp/octop-worker-compat.json
```

Contexts and evidence outputs must be new or byte-identical; changed contexts
are rejected. Use a new owned context directory when inputs change. The probe
requires an immutable local image ID, uses stdio only, runs non-root with no
network, a read-only root, all capabilities dropped, no-new-privileges, bounded
memory/CPU/PIDs and a limited temporary filesystem. It mounts no user resources,
credentials or Docker socket and exposes no ports. Its random owned container
is removed on exit.

The two tools only echo bounded text and import SDK modules/classes. No Agent is
constructed, model or external tool is called, persistent Run is created, or
native execution is enabled. The invocation count belongs to synthetic local
echo calls; it is not the N04 real ticket/tool count. Provider/browser/gateway
channel lifecycle, optional memory backends, native policy/approval/audit
integration, actual cancellation/recovery and production registration remain
future work under their original exit conditions. N08 does not start here.
