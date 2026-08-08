#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

uv run --offline python - <<'PY'
import tomllib
from pathlib import Path

data = tomllib.loads(Path("backend/pyproject.toml").read_text())
project = data["project"]
assert project["name"] == "prismos", project["name"]
assert "deerflow-harness" in project["dependencies"]
PY

node - <<'NODE'
const pkg = require('./frontend/package.json');
if (pkg.name !== 'prismos-frontend') {
  throw new Error(`unexpected frontend package name: ${pkg.name}`);
}
NODE

grep -Fq 'https://github.com/yespon/prism-os' frontend/src/components/landing/header.tsx
grep -Fq 'PrismOS API Gateway' backend/app/gateway/app.py
grep -Fq 'opsintech.current_tenant_id' frontend/src/core/tenants/store.ts
grep -Fq '.opsintech' backend/packages/harness/deerflow/config/paths.py

if rg -n 'https://github.com/opsintech/opsintech-platform|OpsinTech' \
  frontend/src backend/app/gateway/app.py; then
  echo 'unexpected first-party OpsinTech branding remains in public product surfaces' >&2
  exit 1
fi

echo 'PASS: PrismOS product identity and compatibility boundaries'
