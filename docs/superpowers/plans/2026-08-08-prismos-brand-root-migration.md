# PrismOS Brand Root Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏既有部署和用户数据的前提下，把 PrismOS 建立为产品、配置模型、客户端状态、部署资源和发布制品的唯一规范身份，并将旧品牌兼容压缩到 `0.2.x` 一个 minor 内可删除的迁移舱。

**Architecture:** 仓库建立机器可执行的品牌门禁；应用进程通过唯一 legacy environment adapter 将旧输入规范化为 `PRISMOS_*`，核心模块只消费 PrismOS 配置；数据目录使用独立的 dry-run/apply 迁移器，浏览器状态使用“新键优先、读旧迁新、只写新”的 helper。数据库 schema、API path、Alembic 历史和 `deerflow` import 保持不变；运行时兼容桥在 `0.3.0` 删除，离线数据迁移器继续保留。

**Tech Stack:** Python 3.12；Pydantic v2；pytest；Bash；Docker Compose；Next.js 16；React 19；TypeScript 5；Vitest；GitHub Actions。

## Global Constraints

- **唯一品牌：** 产品与 UI 使用 `PrismOS`；仓库 `yespon/prism-os`；Python 项目 `prismos`；前端包 `prismos-frontend`；镜像 `ghcr.io/yespon/prism-os`。
- **规范命名：** 新环境变量只使用 `PRISMOS_*`；新用户数据目录只使用 `.prismos`；新浏览器键使用 `prismos_*` 或 `prismos:*`；新部署资源使用 `prismos-*`。
- **兼容版本：** 兼容桥首次进入 `0.2.x`，运行时旧输入读取在 `0.3.0` 删除；不得延长到第二个 minor。
- **读写规则：** `PRISMOS_*` 优先；旧输入只读；新状态只写；显式但无效的新输入不得回退旧输入。
- **数据安全：** 不静默移动、覆盖或删除 `.opsintech`；目录迁移必须支持 dry-run、复制、全文件校验、原子切换和回滚。
- **历史资料：** 旧名称只允许出现在逐文件白名单内的 compatibility code、迁移工具/测试、迁移说明和标注 `Legacy / Historical` 的历史资料。
- **运行时边界：** 不重命名 `deerflow` import、数据库表、Alembic revision、已有 API path、持久化 ID 或 LangGraph graph/checkpointer 接口。
- **AI 运维定位：** AI 运维只作为验证场景，不成为 PrismOS 内核品牌、配置或架构依赖。
- **对象存储：** 本轮只改变新 bucket/prefix 默认值并提供旧资源检测；不复制或删除真实远端对象。
- **本地数据：** 不修改或删除 `backend/opsintech.db`、`.opsintech`、`.superpowers/` 或其他用户运行数据；这些文件不得进入提交。
- **测试纪律：** 每个任务先写失败测试，再做最小实现；每个任务通过局部验收后独立提交。
- **Git 纪律：** 不重写历史；不使用破坏性 reset/checkout；本地目录改名只能在所有代码提交和验证完成后执行。

---

## File and Ownership Map

| Workstream | Files | Responsibility |
|---|---|---|
| Brand Gate | `scripts/check_brand_identity.py`, `config/brand-legacy-allowlist.json`, scanner tests, workflows | 扫描受版本控制的内容和文件名，执行逐文件白名单与只减不增门禁 |
| Public Brand | README/UI/prompt/docs/assets/default copy | 清除所有用户与开发者可见旧品牌，建立 PrismOS 视觉与文案 |
| Runtime Config | `deerflow/config/prismos_env.py`, config/path/storage consumers, tests | 将旧环境输入规范化为 PrismOS settings，禁止核心代码直接读取旧变量 |
| Deployment Config | `scripts/prismos-env.sh`, Compose files, start/deploy scripts | 在 Shell 边界兼容旧部署输入，Compose 与容器内部只使用新变量 |
| Home Migration | `deerflow/config/home_migration.py`, `backend/scripts/migrate_prismos_home.py`, tests | `.opsintech` 到 `.prismos` 的显式、安全、可重复迁移 |
| Browser Migration | `frontend/src/core/storage/brand-migration.ts` and consumers/tests | localStorage 读旧迁新、只写新，事件名与导出名切换 |
| Internal Protocol | terminal marker/heredoc/User-Agent tests and code | 重命名内部标识并证明没有外部/持久化契约回归 |
| Release/Docs | migration guide, historical banners, release notes | 声明兼容与移除版本、升级/回滚路径和历史资料边界 |
| GitHub Surface | `.github` templates plus read-only remote metadata checks | 保证 About、Topics、Release 和 Packages 表面只使用 PrismOS；任何远端修正必须先取得明确授权 |

公共依赖方向：

```text
Brand vocabulary + scanner
          │
          ├── Public brand cleanup
          ├── Runtime legacy adapter ──→ Paths / AppConfig / Storage / Sandbox
          ├── Home migration CLI
          ├── Browser migration helper ──→ localStorage consumers
          └── Internal protocol rename
                         │
                         └── Deployment + docs + final allowlist + CI
```

## Parallel Execution Waves

| Wave | Parallel tasks | Merge gate |
|---|---|---|
| 0 | Task 1 | Scanner unit tests pass；扫描契约冻结，但暂不阻断当前基线 |
| 1 | Task 2, Task 3, Task 6, Task 7, Task 8 | 文件所有权互斥；Task 3 冻结 runtime adapter API |
| 2 | Task 4, Task 5, Task 9 | Task 4/5 消费 Task 3；公开表面已由 Task 2 清理 |
| 3 | Task 10 | 最终 allowlist 收缩；CI、版本和 Release 契约通过 |
| 4 | Task 11 | 全量回归通过后才改本地目录；之后再启动 M1/P0 计划 |

---

### Task 1: Build the executable brand identity gate

**Files:**
- Create: `scripts/check_brand_identity.py`
- Create: `config/brand-legacy-allowlist.json`
- Create: `backend/tests/test_brand_identity_gate.py`

**Interfaces:**
- Produces: `LegacyMatch(path: str, line: int, token: str, text: str)`, `tracked_paths(repo_root: Path) -> list[str]`, `scan_paths(repo_root: Path, paths: Iterable[str]) -> list[LegacyMatch]`, `validate_matches(matches: list[LegacyMatch], allowlist: dict[str, Any], *, repo_root: Path) -> list[str]`.
- Allowlist entry schema: `path`, `classification`, `reason`, `owner`, `remove_by`, `max_matches`.
- Consumed by: Task 10 CI integration and final repository audit.

- [ ] **Step 1: Write failing scanner contract tests**

Create `backend/tests/test_brand_identity_gate.py`:

```python
import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "check_brand_identity.py"
SPEC = importlib.util.spec_from_file_location("brand_gate", SCRIPT)
assert SPEC and SPEC.loader
brand_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = brand_gate
SPEC.loader.exec_module(brand_gate)


def test_unlisted_legacy_match_fails(tmp_path: Path) -> None:
    source = tmp_path / "ui.ts"
    source.write_text('const key = "opsintech.old";\n', encoding="utf-8")
    matches = brand_gate.scan_paths(tmp_path, ["ui.ts"])
    errors = brand_gate.validate_matches(matches, {"entries": []}, repo_root=tmp_path)
    assert errors == ["ui.ts:1: unallowlisted legacy token: opsintech"]


def test_exact_allowlist_enforces_match_ceiling(tmp_path: Path) -> None:
    source = tmp_path / "legacy.py"
    source.write_text('OLD = "OPSINTECH_HOME"\n', encoding="utf-8")
    allowlist = {
        "entries": [{
            "path": "legacy.py",
            "classification": "compatibility-code",
            "reason": "Reads the 0.2.x deployment input",
            "owner": "runtime-config",
            "remove_by": "0.3.0",
            "max_matches": 1,
        }]
    }
    assert brand_gate.validate_matches(
        brand_gate.scan_paths(tmp_path, ["legacy.py"]), allowlist, repo_root=tmp_path
    ) == []
    source.write_text('A = "OPSINTECH_HOME"\nB = ".opsintech"\n', encoding="utf-8")
    errors = brand_gate.validate_matches(
        brand_gate.scan_paths(tmp_path, ["legacy.py"]), allowlist, repo_root=tmp_path
    )
    assert errors == ["legacy.py: legacy matches 2 exceed allowed maximum 1"]


def test_allowlist_rejects_wildcards_and_missing_metadata() -> None:
    errors = brand_gate.validate_allowlist({"entries": [{"path": "docs/**"}]})
    assert "allowlist entry 1 path must be exact" in errors
    assert "allowlist entry 1 missing classification" in errors


def test_historical_file_requires_banner(tmp_path: Path) -> None:
    source = tmp_path / "history.md"
    source.write_text("OpsinTech release notes\n", encoding="utf-8")
    allowlist = {"entries": [{
        "path": "history.md",
        "classification": "historical-document",
        "reason": "Preserves release history",
        "owner": "documentation",
        "remove_by": "never-historical",
        "max_matches": 1,
    }]}
    errors = brand_gate.validate_matches(
        brand_gate.scan_paths(tmp_path, ["history.md"]), allowlist, repo_root=tmp_path
    )
    assert errors == ["history.md: historical document is missing 'Legacy / Historical' banner"]


def test_historical_banner_may_be_below_title(tmp_path: Path) -> None:
    source = tmp_path / "history.md"
    source.write_text(
        "# Old release\n\n> **Legacy / Historical:** superseded\n\nOpsinTech notes\n",
        encoding="utf-8",
    )
    allowlist = {"entries": [{
        "path": "history.md",
        "classification": "historical-document",
        "reason": "Preserves release history",
        "owner": "documentation",
        "remove_by": "never-historical",
        "max_matches": 1,
    }]}
    assert brand_gate.validate_matches(
        brand_gate.scan_paths(tmp_path, ["history.md"]), allowlist, repo_root=tmp_path
    ) == []
```

- [ ] **Step 2: Run the tests and confirm the script is missing**

Run: `cd backend && uv run pytest tests/test_brand_identity_gate.py -q`

Expected: collection fails because `scripts/check_brand_identity.py` does not exist.

- [ ] **Step 3: Implement the scanner and strict allowlist validator**

Create `scripts/check_brand_identity.py` with these exact public contracts:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

LEGACY_PATTERN = re.compile(r"opsintech(?:-platform)?|OPSINTECH", re.IGNORECASE)
REQUIRED_FIELDS = {"path", "classification", "reason", "owner", "remove_by", "max_matches"}


@dataclass(frozen=True)
class LegacyMatch:
    path: str
    line: int
    token: str
    text: str


def tracked_paths(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo_root, check=True, capture_output=True
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def scan_paths(repo_root: Path, paths: Iterable[str]) -> list[LegacyMatch]:
    matches: list[LegacyMatch] = []
    for relative in paths:
        path = repo_root / relative
        filename_match = LEGACY_PATTERN.search(relative)
        if filename_match:
            matches.append(LegacyMatch(relative, 0, filename_match.group(0), relative))
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            for match in LEGACY_PATTERN.finditer(line):
                matches.append(LegacyMatch(relative, line_number, match.group(0), line.strip()))
    return matches


def validate_allowlist(allowlist: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for index, entry in enumerate(allowlist.get("entries", []), 1):
        path = entry.get("path", "")
        if any(char in path for char in "*?[]") or not path:
            errors.append(f"allowlist entry {index} path must be exact")
        for field in sorted(REQUIRED_FIELDS - entry.keys()):
            errors.append(f"allowlist entry {index} missing {field}")
    return errors


def validate_matches(
    matches: list[LegacyMatch],
    allowlist: dict[str, Any],
    *,
    repo_root: Path,
) -> list[str]:
    errors = validate_allowlist(allowlist)
    entries = {entry.get("path"): entry for entry in allowlist.get("entries", [])}
    grouped: dict[str, list[LegacyMatch]] = {}
    for match in matches:
        grouped.setdefault(match.path, []).append(match)
        if match.path not in entries:
            errors.append(
                f"{match.path}:{match.line}: unallowlisted legacy token: {match.token.lower()}"
            )
    for path, entry in entries.items():
        path_matches = grouped.get(path, [])
        if len(path_matches) > entry.get("max_matches", -1):
            errors.append(
                f"{path}: legacy matches {len(path_matches)} exceed allowed maximum {entry['max_matches']}"
            )
        if entry.get("classification") == "historical-document" and path_matches:
            try:
                document = (repo_root / path).read_text(encoding="utf-8")
            except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
                document = ""
            if "Legacy / Historical" not in document:
                errors.append(f"{path}: historical document is missing 'Legacy / Historical' banner")
    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Enforce the PrismOS brand boundary")
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=repo_root / "config" / "brand-legacy-allowlist.json",
    )
    args = parser.parse_args()
    allowlist = json.loads(args.allowlist.read_text(encoding="utf-8"))
    paths = tracked_paths(repo_root)
    matches = scan_paths(repo_root, paths)
    errors = validate_matches(matches, allowlist, repo_root=repo_root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"PrismOS brand gate passed: {len(paths)} tracked files, {len(matches)} allowlisted matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Add `import sys` to the implementation imports. The CLI must use the repository root derived from `__file__`, so it behaves identically when invoked from the root, `backend/`, or CI.

- [ ] **Step 4: Add a non-blocking bootstrap allowlist**

Create `config/brand-legacy-allowlist.json` with an empty `entries` array and metadata:

```json
{
  "schema_version": 1,
  "policy": "Exact paths only; compatibility entries expire at 0.3.0; historical documents require a Legacy / Historical banner.",
  "entries": []
}
```

Do not add the scanner to CI yet: the current tree is intentionally red until Tasks 2–9 remove or classify every occurrence.

- [ ] **Step 5: Run focused tests and syntax checks**

Run: `cd backend && uv run pytest tests/test_brand_identity_gate.py -q`

Expected: `5 passed`.

Run: `uv run --offline python -m py_compile scripts/check_brand_identity.py && git diff --check`

Expected: both commands exit 0.

- [ ] **Step 6: Commit the brand gate foundation**

```bash
git add scripts/check_brand_identity.py config/brand-legacy-allowlist.json backend/tests/test_brand_identity_gate.py
git commit -m "test: establish PrismOS brand identity gate"
```

---

### Task 2: Replace public product branding and visual assets

**Files:**
- Rename: `frontend/public/images/opsintech.svg` → `frontend/public/images/prismos.svg`
- Replace: `frontend/public/images/opsintech-full.svg` → `frontend/public/images/prismos-full.svg`
- Modify: `frontend/src/app/sign-in/page.tsx`
- Modify: `frontend/src/components/landing/hero.tsx`
- Modify: `frontend/src/components/workspace/workspace-header.tsx`
- Modify: `frontend/src/components/tenant-admin/alert-sources-tab.tsx`
- Modify: `frontend/src/components/workspace/incidents/alert-sources-panel.tsx`
- Modify: `frontend/src/components/workspace/artifacts/artifact-file-detail.tsx`
- Modify: `frontend/src/core/terminal-agent/security/security-settings-ui.tsx`
- Modify: `backend/app/agent/prompts.py`
- Modify: `backend/app/gateway/routers/channels.py`
- Modify: `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`
- Modify: `backend/scripts/reset_admin_password_explicit.py`
- Modify: `skills/public/incident-diagnosis/SKILL.md`
- Modify: `rewrite_ui.py`
- Create: `frontend/src/core/brand/public-identity.test.ts`

**Interfaces:**
- Produces: `/images/prismos.svg`, `/images/prismos-full.svg`, visible product name `PrismOS`, default webhook receiver `prismos-receiver`, export filename `prismos-security-config.json`.
- Preserves: the existing prism-shaped icon geometry and color palette; the full wordmark text changes to `PrismOS`.

- [ ] **Step 1: Add a failing public identity test**

Create `frontend/src/core/brand/public-identity.test.ts`:

```typescript
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const root = path.resolve(__dirname, "../../..");
const publicFiles = [
  "src/app/sign-in/page.tsx",
  "src/components/landing/hero.tsx",
  "src/components/workspace/workspace-header.tsx",
  "src/components/tenant-admin/alert-sources-tab.tsx",
  "src/components/workspace/incidents/alert-sources-panel.tsx",
  "src/core/terminal-agent/security/security-settings-ui.tsx",
];

describe("PrismOS public identity", () => {
  it("uses PrismOS assets and copy", () => {
    for (const relative of publicFiles) {
      const content = fs.readFileSync(path.join(root, relative), "utf8");
      expect(content).not.toMatch(/opsintech/i);
    }
    expect(fs.existsSync(path.join(root, "public/images/prismos.svg"))).toBe(true);
    expect(fs.existsSync(path.join(root, "public/images/prismos-full.svg"))).toBe(true);
    expect(fs.existsSync(path.join(root, "public/images/opsintech.svg"))).toBe(false);
    expect(fs.readFileSync(path.join(root, "public/images/prismos-full.svg"), "utf8"))
      .toContain("PrismOS");
  });
});
```

- [ ] **Step 2: Run the test and confirm old assets/copy fail**

Run: `cd frontend && pnpm test:unit -- src/core/brand/public-identity.test.ts`

Expected: FAIL because PrismOS assets do not exist and public files still contain old names.

- [ ] **Step 3: Rename the icon and create the PrismOS wordmark**

Use `git mv` for the icon-only SVG. Create `prismos-full.svg` from the same icon geometry, replace the three old text spans with one accessible wordmark:

```svg
<text class="logo-text" aria-label="PrismOS">PrismOS</text>
```

Use `fill: currentColor` or the existing dark-mode-safe neutral text class. Delete the old full-logo file only after all references point at `/images/prismos-full.svg` or `/images/prismos.svg`.

- [ ] **Step 4: Replace all public copy and defaults in the owned files**

Apply these exact mappings:

```text
/images/opsintech.svg             → /images/prismos.svg
opsintech-receiver                → prismos-receiver
opsintech-security-config.json    → prismos-security-config.json
OpsinTech Chaterm                 → PrismOS Terminal Agent
admin-<id>@opsintech.local        → admin-<id>@prismos.local
opsintech-platform path label     → prism-os path label
```

In `lead_agent/prompt.py`, remove fake old repository/website citations and describe the agent as the PrismOS lead agent. Keep factual DeerFlow/LangGraph attribution where it describes actual dependencies.

- [ ] **Step 5: Verify frontend and backend public surfaces**

Run:

```bash
cd frontend && pnpm test:unit -- src/core/brand/public-identity.test.ts
cd ../backend && uv run pytest tests/test_incident_diagnosis.py tests/test_channels.py -q
cd .. && git grep -In -e 'OpsinTech' -e 'opsintech-platform' -- \
  frontend/src backend/app/agent/prompts.py backend/app/gateway/routers/channels.py \
  backend/packages/harness/deerflow/agents/lead_agent/prompt.py \
  backend/scripts/reset_admin_password_explicit.py skills/public/incident-diagnosis/SKILL.md rewrite_ui.py
```

Expected: focused tests pass and `git grep` returns no matches.

- [ ] **Step 6: Commit public brand replacement**

```bash
git add frontend/public/images frontend/src/app/sign-in/page.tsx \
  frontend/src/components/landing/hero.tsx \
  frontend/src/components/workspace/workspace-header.tsx \
  frontend/src/components/tenant-admin/alert-sources-tab.tsx \
  frontend/src/components/workspace/incidents/alert-sources-panel.tsx \
  frontend/src/components/workspace/artifacts/artifact-file-detail.tsx \
  frontend/src/core/terminal-agent/security/security-settings-ui.tsx \
  frontend/src/core/brand/public-identity.test.ts backend/app/agent/prompts.py \
  backend/app/gateway/routers/channels.py \
  backend/packages/harness/deerflow/agents/lead_agent/prompt.py \
  backend/scripts/reset_admin_password_explicit.py skills/public/incident-diagnosis/SKILL.md rewrite_ui.py
git commit -m "refactor: establish PrismOS public brand identity"
```

---

### Task 3: Create the bounded runtime environment adapter

**Files:**
- Create: `backend/packages/harness/deerflow/config/prismos_env.py`
- Create: `backend/tests/test_prismos_env_adapter.py`

**Interfaces:**
- Produces: `ConfigSource`, `ResolvedSetting`, `resolve_setting()`, `legacy_usage_report()`.
- Signature: `resolve_setting(name: str, *, default: str | None = None, environ: Mapping[str, str] | None = None, validator: Callable[[str], str] | None = None) -> ResolvedSetting`.
- Owns: the complete `LEGACY_ENV_ALIASES: dict[str, tuple[str, ...]]`; no caller names an `OPSINTECH_*` variable.
- Constants: `BRIDGE_MINOR = "0.2.x"`, `REMOVE_IN_VERSION = "0.3.0"`.
- Produces: `discover_legacy_home(canonical_home: Path) -> Path | None`; it reports a sibling legacy directory but never selects or mutates it.
- Consumed by: Tasks 4 and 5.

- [ ] **Step 1: Write failing adapter tests**

Create `backend/tests/test_prismos_env_adapter.py`:

```python
import logging

import pytest

from deerflow.config.prismos_env import (
    ConfigSource,
    discover_legacy_home,
    legacy_usage_report,
    resolve_setting,
)


def non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def test_prismos_value_wins_and_conflict_hides_values(caplog) -> None:
    caplog.set_level(logging.WARNING)
    result = resolve_setting(
        "PRISMOS_HOME",
        default="/default",
        environ={"PRISMOS_HOME": "/new", "OPSINTECH_HOME": "/secret-old"},
    )
    assert result.value == "/new"
    assert result.source is ConfigSource.PRISMOS
    assert "OPSINTECH_HOME" in caplog.text
    assert "/new" not in caplog.text
    assert "/secret-old" not in caplog.text


def test_legacy_value_is_read_with_removal_warning(caplog) -> None:
    caplog.set_level(logging.WARNING)
    result = resolve_setting(
        "PRISMOS_HOME",
        default="/default",
        environ={"OPSINTECH_HOME": "/legacy"},
    )
    assert result.value == "/legacy"
    assert result.source is ConfigSource.LEGACY
    assert result.source_name == "OPSINTECH_HOME"
    assert "0.3.0" in caplog.text


def test_invalid_new_value_never_falls_back_to_legacy() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        resolve_setting(
            "PRISMOS_HOME",
            environ={"PRISMOS_HOME": " ", "OPSINTECH_HOME": "/legacy"},
            validator=non_blank,
        )


def test_default_and_usage_report_are_deterministic() -> None:
    result = resolve_setting("PRISMOS_HOME", default="/default", environ={})
    assert result.value == "/default"
    assert result.source is ConfigSource.DEFAULT
    assert legacy_usage_report([result]) == []


def test_legacy_home_is_discovered_without_becoming_active(tmp_path, caplog) -> None:
    canonical = tmp_path / ".prismos"
    legacy = tmp_path / ".opsintech"
    legacy.mkdir()
    caplog.set_level(logging.WARNING)
    assert discover_legacy_home(canonical) == legacy
    assert str(legacy) in caplog.text
    assert "migrate_prismos_home.py" in caplog.text
    assert not canonical.exists()
```

- [ ] **Step 2: Run the tests and confirm the adapter is missing**

Run: `cd backend && uv run pytest tests/test_prismos_env_adapter.py -q`

Expected: collection fails with `ModuleNotFoundError` for `deerflow.config.prismos_env`.

- [ ] **Step 3: Implement the adapter**

Create `deerflow/config/prismos_env.py` with:

```python
from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

BRIDGE_MINOR = "0.2.x"
REMOVE_IN_VERSION = "0.3.0"
logger = logging.getLogger(__name__)

LEGACY_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "PRISMOS_HOME": ("OPSINTECH_HOME",),
    "PRISMOS_CONFIG_PATH": ("OPSINTECH_CONFIG_PATH",),
    "PRISMOS_EXTENSIONS_CONFIG_PATH": ("OPSINTECH_EXTENSIONS_CONFIG_PATH",),
    "PRISMOS_HOST_BASE_DIR": ("OPSINTECH_HOST_BASE_DIR",),
    "PRISMOS_HOST_SKILLS_PATH": ("OPSINTECH_HOST_SKILLS_PATH",),
    "PRISMOS_SANDBOX_HOST": ("OPSINTECH_SANDBOX_HOST",),
    "PRISMOS_STORAGE_BACKEND": ("OPSINTECH_STORAGE_BACKEND",),
    "PRISMOS_STORAGE_LOCAL_ROOT": ("OPSINTECH_STORAGE_LOCAL_ROOT",),
    "PRISMOS_STORAGE_S3_ENDPOINT": ("OPSINTECH_STORAGE_S3_ENDPOINT",),
    "PRISMOS_STORAGE_S3_ACCESS_KEY": ("OPSINTECH_STORAGE_S3_ACCESS_KEY",),
    "PRISMOS_STORAGE_S3_SECRET_KEY": ("OPSINTECH_STORAGE_S3_SECRET_KEY",),
    "PRISMOS_STORAGE_S3_BUCKET": ("OPSINTECH_STORAGE_S3_BUCKET",),
    "PRISMOS_STORAGE_S3_REGION": ("OPSINTECH_STORAGE_S3_REGION",),
    "PRISMOS_STORAGE_S3_USE_SSL": ("OPSINTECH_STORAGE_S3_USE_SSL",),
    "PRISMOS_STORAGE_JUICEFS_MOUNT": ("OPSINTECH_STORAGE_JUICEFS_MOUNT",),
    "PRISMOS_STORAGE_JUICEFS_SUBDIR": ("OPSINTECH_STORAGE_JUICEFS_SUBDIR",),
}


class ConfigSource(StrEnum):
    PRISMOS = "PrismOS"
    LEGACY = "Legacy"
    DEFAULT = "Default"


@dataclass(frozen=True)
class ResolvedSetting:
    name: str
    value: str | None
    source: ConfigSource
    source_name: str


def resolve_setting(
    name: str,
    *,
    default: str | None = None,
    environ: Mapping[str, str] | None = None,
    validator: Callable[[str], str] | None = None,
) -> ResolvedSetting:
    values = os.environ if environ is None else environ
    legacy_names = LEGACY_ENV_ALIASES.get(name, ())
    if name in values:
        value = values[name]
        if validator:
            value = validator(value)
        conflicts = [legacy for legacy in legacy_names if legacy in values and values[legacy] != value]
        if conflicts:
            logger.warning("%s overrides conflicting legacy input(s): %s", name, ", ".join(conflicts))
        return ResolvedSetting(name, value, ConfigSource.PRISMOS, name)
    for legacy in legacy_names:
        if legacy in values:
            value = values[legacy]
            if validator:
                value = validator(value)
            logger.warning("%s is deprecated; use %s before removal in %s", legacy, name, REMOVE_IN_VERSION)
            return ResolvedSetting(name, value, ConfigSource.LEGACY, legacy)
    value = validator(default) if validator and default is not None else default
    return ResolvedSetting(name, value, ConfigSource.DEFAULT, "default")


def legacy_usage_report(settings: Sequence[ResolvedSetting]) -> list[dict[str, str]]:
    return [
        {"name": item.name, "source": item.source.value, "source_name": item.source_name,
         "remove_in": REMOVE_IN_VERSION}
        for item in settings if item.source is ConfigSource.LEGACY
    ]


def discover_legacy_home(canonical_home: Path) -> Path | None:
    legacy_home = canonical_home.with_name(".opsintech")
    if canonical_home.exists() or not legacy_home.is_dir():
        return None
    logger.warning(
        "Legacy PrismOS data detected at %s; run migrate_prismos_home.py before "
        "0.3.0. The directory was not selected or modified.",
        legacy_home,
    )
    return legacy_home
```

- [ ] **Step 4: Run tests and lint**

Run: `cd backend && uv run pytest tests/test_prismos_env_adapter.py -q && uv run ruff check packages/harness/deerflow/config/prismos_env.py tests/test_prismos_env_adapter.py`

Expected: `5 passed`, Ruff exits 0, and captured logs contain variable names but no configured values.

- [ ] **Step 5: Commit the runtime adapter**

```bash
git add backend/packages/harness/deerflow/config/prismos_env.py backend/tests/test_prismos_env_adapter.py
git commit -m "feat: add bounded PrismOS legacy input adapter"
```

---

### Task 4: Route backend paths, config, storage, and sandbox through PrismOS settings

**Files:**
- Modify: `backend/packages/harness/deerflow/config/paths.py`
- Modify: `backend/packages/harness/deerflow/config/app_config.py`
- Modify: `backend/packages/harness/deerflow/config/extensions_config.py`
- Modify: `backend/packages/harness/deerflow/config/database_config.py`
- Modify: `backend/packages/harness/deerflow/config/checkpointer_config.py`
- Modify: `backend/packages/harness/deerflow/config/memory_config.py`
- Modify: `backend/packages/harness/deerflow/database/session.py`
- Modify: `backend/packages/harness/deerflow/database/user_config_store.py`
- Modify: `backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py`
- Modify: `backend/packages/harness/deerflow/community/aio_sandbox/local_backend.py`
- Modify: `backend/packages/harness/deerflow/storage/provider.py`
- Modify: `backend/packages/harness/deerflow/storage/local.py`
- Modify: `backend/packages/harness/deerflow/storage/s3.py`
- Modify: `backend/packages/harness/deerflow/storage/juicefs.py`
- Create: `backend/packages/harness/deerflow/storage/legacy_resources.py`
- Modify: `backend/packages/harness/deerflow/mcp/cache.py`
- Modify: `backend/alembic.ini`
- Modify: `backend/app/gateway/routers/memory.py`
- Test: `backend/tests/test_prismos_runtime_defaults.py`
- Create: `backend/tests/test_prismos_legacy_object_storage.py`
- Test: `backend/tests/test_app_config_reload.py`
- Test: `backend/tests/test_checkpointer.py`
- Test: `backend/tests/test_database_session.py`
- Test: `backend/tests/test_user_config_store.py`
- Test: `backend/tests/test_storage_local.py`
- Test: `backend/tests/test_storage_s3.py`
- Test: `backend/tests/test_storage_juicefs.py`
- Test: `backend/tests/test_aio_sandbox_isolation.py`
- Test: `backend/tests/test_docker_sandbox_mode_detection.py`

**Interfaces:**
- Consumes: `resolve_setting()` and `discover_legacy_home()` from Task 3.
- Produces new defaults: `.prismos`, `prismos-files`, `prismos-sandbox`, `PRISMOS_CONFIG_PATH`, `PRISMOS_EXTENSIONS_CONFIG_PATH`, `PRISMOS_HOST_BASE_DIR`, `PRISMOS_HOST_SKILLS_PATH`, `PRISMOS_SANDBOX_HOST`, and `PRISMOS_STORAGE_*`.
- Produces: `LegacyObjectResource`, `detect_legacy_object_resources(config)`, `validate_s3_bucket_access(client, bucket)`; these inspect and report but never copy or delete objects.
- Legacy environment names may appear only in `prismos_env.py` and its tests. Core consumers pass only canonical `PRISMOS_*` names.

- [ ] **Step 1: Add failing tests for new-install defaults and legacy reads**

Create `backend/tests/test_prismos_runtime_defaults.py`:

```python
from pathlib import Path

from deerflow.config.app_config import AppConfig
from deerflow.config.database_config import DatabaseConfig
from deerflow.config.paths import Paths
from deerflow.storage.local import _load_storage_config
from deerflow.storage.provider import StorageProviderConfig


def test_new_install_defaults_use_prismos(monkeypatch, tmp_path: Path) -> None:
    for name in list(__import__("os").environ):
        if name.startswith(("PRISMOS_", "OPSINTECH_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert Paths().base_dir == tmp_path / ".prismos"
    assert DatabaseConfig().url.endswith("/.prismos/tenant.db")
    assert StorageProviderConfig().s3_bucket_name == "prismos-files"
    assert StorageProviderConfig().juicefs_subdir == "prismos-files"


def test_legacy_config_path_is_read_only_through_adapter(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "legacy.yaml"
    config.write_text("sandbox:\n  use: local\n", encoding="utf-8")
    monkeypatch.delenv("PRISMOS_CONFIG_PATH", raising=False)
    monkeypatch.setenv("OPSINTECH_CONFIG_PATH", str(config))
    assert AppConfig.resolve_config_path() == config


def test_storage_new_variable_wins(monkeypatch) -> None:
    monkeypatch.setenv("PRISMOS_STORAGE_BACKEND", "local")
    monkeypatch.setenv("OPSINTECH_STORAGE_BACKEND", "s3")
    assert _load_storage_config().backend == "local"


def test_existing_legacy_home_is_reported_but_not_selected(monkeypatch, tmp_path, caplog) -> None:
    legacy = tmp_path / ".opsintech"
    legacy.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PRISMOS_HOME", raising=False)
    monkeypatch.delenv("OPSINTECH_HOME", raising=False)
    assert Paths().base_dir == tmp_path / ".prismos"
    assert str(legacy) in caplog.text
```

- [ ] **Step 2: Run focused tests and confirm old defaults fail**

Run: `cd backend && uv run pytest tests/test_prismos_runtime_defaults.py -q`

Expected: failures show `.opsintech` and `opsintech-files` are still defaults.

- [ ] **Step 3: Migrate config and path consumers to the adapter**

For each canonical setting in the exact mapping below, call `resolve_setting()` with the PrismOS name and default; Task 3 owns the legacy alias mapping. Use this implementation for `Paths.base_dir`:

```python
home = resolve_setting(
    "PRISMOS_HOME",
    default=str(self._fallback_base_dir()),
)
candidate = Path(home.value).resolve()
```

Change fallback candidates to `$HOME/.prismos` and `/tmp/.prismos`. Do not automatically select an existing `.opsintech`; detection must emit migration guidance and compatibility use must be explicit through the adapter or migration tool.

For config paths, new variable names are authoritative. If a new variable points to a missing file, raise a message naming the new variable and do not inspect the legacy variable.

Use this exact mapping for every direct legacy read found in the baseline:

```text
paths.py                 PRISMOS_HOME, PRISMOS_HOST_BASE_DIR
app_config.py            PRISMOS_CONFIG_PATH
extensions_config.py     PRISMOS_EXTENSIONS_CONFIG_PATH
user_config_store.py     PRISMOS_CONFIG_PATH, PRISMOS_EXTENSIONS_CONFIG_PATH
aio_sandbox_provider.py  PRISMOS_HOST_SKILLS_PATH
local_backend.py         PRISMOS_SANDBOX_HOST
storage/local.py         PRISMOS_STORAGE_BACKEND, PRISMOS_STORAGE_LOCAL_ROOT,
                         PRISMOS_STORAGE_S3_ENDPOINT, PRISMOS_STORAGE_S3_ACCESS_KEY,
                         PRISMOS_STORAGE_S3_SECRET_KEY, PRISMOS_STORAGE_S3_BUCKET,
                         PRISMOS_STORAGE_S3_REGION, PRISMOS_STORAGE_S3_USE_SSL,
                         PRISMOS_STORAGE_JUICEFS_MOUNT, PRISMOS_STORAGE_JUICEFS_SUBDIR
```

For `PRISMOS_STORAGE_S3_USE_SSL`, pass a validator that accepts only case-insensitive `true` or `false` and returns the normalized string; convert the resolved value to boolean after resolution. Keep unrelated third-party variables such as `DEERFLOW_*`, `POSTGRES_*`, and model-provider secrets unchanged.

- [ ] **Step 4: Change new storage, database, sandbox, and memory defaults**

Apply exact new defaults:

```text
sqlite+aiosqlite:///.prismos/auth.db
sqlite+aiosqlite:///.prismos/tenant.db
.prismos/memory.json
prismos-files
prismos-sandbox
.prismos_write_probe
```

Tests that describe new installations must use PrismOS values. Tests whose sole purpose is legacy compatibility retain old values and must be named with `legacy` in the test function.

- [ ] **Step 5: Add the read-only object-storage detector**

Create `backend/packages/harness/deerflow/storage/legacy_resources.py` with these contracts:

```python
from dataclasses import dataclass
from typing import Any

from deerflow.storage.provider import StorageProviderConfig


@dataclass(frozen=True)
class LegacyObjectResource:
    kind: str
    name: str
    guidance: str


@dataclass(frozen=True)
class BucketAccessReport:
    bucket: str
    accessible: bool
    error_type: str | None = None


def detect_legacy_object_resources(
    config: StorageProviderConfig,
) -> tuple[LegacyObjectResource, ...]:
    resources: list[LegacyObjectResource] = []
    if config.s3_bucket_name == "opsintech-files":
        resources.append(LegacyObjectResource(
            kind="s3-bucket",
            name=config.s3_bucket_name,
            guidance="Verify access and create an explicit remote migration plan; PrismOS will not copy or delete objects.",
        ))
    if config.juicefs_subdir == "opsintech-files":
        resources.append(LegacyObjectResource(
            kind="juicefs-prefix",
            name=config.juicefs_subdir,
            guidance="Verify access and create an explicit remote migration plan; PrismOS will not copy or delete objects.",
        ))
    return tuple(resources)


def validate_s3_bucket_access(client: Any, bucket: str) -> BucketAccessReport:
    try:
        client.head_bucket(Bucket=bucket)
    except Exception as exc:
        return BucketAccessReport(bucket, False, type(exc).__name__)
    return BucketAccessReport(bucket, True)
```

Call `detect_legacy_object_resources()` after storage config resolution and log only resource kind/name plus guidance. Do not call `validate_s3_bucket_access()` during startup; it is an explicit preflight helper because remote calls can incur latency and require credentials.

Create `backend/tests/test_prismos_legacy_object_storage.py`:

```python
from deerflow.storage.legacy_resources import (
    detect_legacy_object_resources,
    validate_s3_bucket_access,
)
from deerflow.storage.provider import StorageProviderConfig


class AccessibleClient:
    def head_bucket(self, *, Bucket: str) -> None:
        assert Bucket == "opsintech-files"


class DeniedClient:
    def head_bucket(self, *, Bucket: str) -> None:
        raise PermissionError(Bucket)


def test_new_defaults_have_no_legacy_remote_resources() -> None:
    assert detect_legacy_object_resources(StorageProviderConfig()) == ()


def test_legacy_resources_are_reported_without_mutation() -> None:
    config = StorageProviderConfig(
        s3_bucket_name="opsintech-files", juicefs_subdir="opsintech-files"
    )
    reports = detect_legacy_object_resources(config)
    assert [item.kind for item in reports] == ["s3-bucket", "juicefs-prefix"]
    assert all("will not copy or delete" in item.guidance for item in reports)


def test_bucket_access_probe_reports_success_and_permission_failure() -> None:
    assert validate_s3_bucket_access(AccessibleClient(), "opsintech-files").accessible
    denied = validate_s3_bucket_access(DeniedClient(), "opsintech-files")
    assert denied.accessible is False
    assert denied.error_type == "PermissionError"
```

- [ ] **Step 6: Prove core code has no direct old-variable reads**

Run:

```bash
git grep -In 'OPSINTECH_' -- backend/packages/harness/deerflow \
  ':!backend/packages/harness/deerflow/config/prismos_env.py'
```

Expected: no matches.

- [ ] **Step 7: Run focused backend suites**

Run:

```bash
cd backend && uv run pytest \
  tests/test_prismos_env_adapter.py tests/test_prismos_runtime_defaults.py \
  tests/test_prismos_legacy_object_storage.py \
  tests/test_app_config_reload.py tests/test_checkpointer.py \
  tests/test_database_session.py tests/test_user_config_store.py \
  tests/test_storage_local.py tests/test_storage_s3.py tests/test_storage_juicefs.py \
  tests/test_aio_sandbox_isolation.py tests/test_docker_sandbox_mode_detection.py -q
```

Expected: all available tests pass; optional S3 tests may report their pre-existing dependency-based skips.

- [ ] **Step 8: Commit normalized runtime defaults**

```bash
git add backend/packages/harness/deerflow backend/alembic.ini \
  backend/app/gateway/routers/memory.py backend/tests/test_prismos_runtime_defaults.py \
  backend/tests/test_prismos_legacy_object_storage.py \
  backend/tests/test_app_config_reload.py backend/tests/test_checkpointer.py \
  backend/tests/test_database_session.py backend/tests/test_user_config_store.py \
  backend/tests/test_storage_local.py backend/tests/test_storage_juicefs.py \
  backend/tests/test_storage_s3.py backend/tests/test_aio_sandbox_isolation.py \
  backend/tests/test_docker_sandbox_mode_detection.py
git commit -m "refactor: normalize PrismOS runtime settings"
```

---

### Task 5: Isolate Shell compatibility and make Compose PrismOS-only

**Files:**
- Modify: `scripts/prismos-env.sh`
- Modify: `scripts/test-prismos-env.sh`
- Modify: `scripts/deploy.sh`
- Modify: `scripts/serve.sh`
- Modify: `scripts/start-daemon.sh`
- Modify: `scripts/docker.sh`
- Modify: `docker-compose.yml`
- Modify: `docker/docker-compose.yaml`
- Modify: `docker/docker-compose-dev.yaml`
- Modify: `config.example.yaml`

**Interfaces:**
- Consumes: PrismOS environment vocabulary from Task 3.
- Produces: normalized exported `PRISMOS_*` variables and `PRISMOS_LEGACY_INPUTS`; no exported `OPSINTECH_*` aliases.
- Compose files consume only `PRISMOS_*`, `POSTGRES_*`, and unrelated third-party variables.

- [ ] **Step 1: Rewrite failing Shell contract assertions**

Update `scripts/test-prismos-env.sh` so `resolve()` prints only `PRISMOS_HOME|PRISMOS_LEGACY_INPUTS`. Add assertions:

```bash
result="$(resolve PRISMOS_HOME=/new OPSINTECH_HOME=/legacy)"
assert_equals "/new|" "$result" "new setting wins without exporting legacy aliases"

result="$(resolve OPSINTECH_HOME=/legacy)"
assert_equals "/legacy|OPSINTECH_HOME" "$result" "legacy input is normalized and reported"

if env -i PATH="$PATH" OPSINTECH_HOME=/legacy bash -c \
  'source "$1"; env | grep -q "^OPSINTECH_"' bash "$ENV_SCRIPT"; then
  echo "FAIL: legacy aliases leaked back into the environment" >&2
  exit 1
fi
```

- [ ] **Step 2: Run the Shell test and confirm reverse exports fail**

Run: `bash scripts/test-prismos-env.sh`

Expected: FAIL because the current script exports normalized values back into `OPSINTECH_*`.

- [ ] **Step 3: Refactor the Shell adapter**

Keep compatibility reads in `scripts/prismos-env.sh`, but remove every `export OPSINTECH_*=` assignment. Add a helper that records source without values:

```bash
prismos_record_legacy_input() {
    local legacy_name="$1"
    if [ -n "${PRISMOS_LEGACY_INPUTS:-}" ]; then
        PRISMOS_LEGACY_INPUTS="${PRISMOS_LEGACY_INPUTS},${legacy_name}"
    else
        PRISMOS_LEGACY_INPUTS="${legacy_name}"
    fi
    export PRISMOS_LEGACY_INPUTS
    printf 'WARNING: %s is deprecated; migrate before PrismOS 0.3.0\n' "$legacy_name" >&2
}
```

Resolve this exact host-boundary mapping using `PRISMOS_* → OPSINTECH_* → default` precedence:

```text
PRISMOS_REPO_ROOT        ← OPSINTECH_REPO_ROOT, then OPSINTECH_ROOT
PRISMOS_HOME             ← OPSINTECH_HOME
PRISMOS_CONFIG_PATH      ← OPSINTECH_CONFIG_PATH
PRISMOS_DOCKER_SOCKET    ← OPSINTECH_DOCKER_SOCKET
PRISMOS_HOST_BASE_DIR    ← OPSINTECH_HOST_BASE_DIR
PRISMOS_HOST_SKILLS_PATH ← OPSINTECH_HOST_SKILLS_PATH
PRISMOS_COMPOSE_PROJECT  ← OPSINTECH_COMPOSE_PROJECT
PRISMOS_K8S_NAMESPACE    ← OPSINTECH_K8S_NAMESPACE
PRISMOS_POSTGRES_USER    ← OPSINTECH_POSTGRES_USER, then POSTGRES_USER
PRISMOS_POSTGRES_PASSWORD← OPSINTECH_POSTGRES_PASSWORD, then POSTGRES_PASSWORD
PRISMOS_POSTGRES_DB      ← OPSINTECH_POSTGRES_DB, then POSTGRES_DB
```

When both names exist, keep the PrismOS value. Record a legacy name only when its value was actually selected; conflicting unused legacy values produce a warning naming both variables but no values. `PRISMOS_LEGACY_INPUTS` is a comma-separated, de-duplicated list in mapping order.

Do not auto-select `.opsintech`; when `backend/.opsintech` exists and neither home variable is set, keep the new `.prismos` default and print this explicit dry-run command:

```text
cd backend && uv run python scripts/migrate_prismos_home.py --source .opsintech --target .prismos
```

- [ ] **Step 4: Remove legacy interpolation and container aliases from Compose**

Change Compose expressions to PrismOS-only forms, for example:

```yaml
PRISMOS_HOST_BASE_DIR: ${PRISMOS_HOME:-./backend/.prismos}
PRISMOS_HOST_SKILLS_PATH: ${PRISMOS_HOST_SKILLS_PATH:-${PWD:-.}/skills}
PRISMOS_SANDBOX_HOST: host.docker.internal
```

Remove all `OPSINTECH_*` environment entries from container environments. Start/deploy scripts must source `scripts/prismos-env.sh` before invoking Compose, so old host inputs are normalized once at the boundary.

- [ ] **Step 5: Update new-deployment examples and script output**

`config.example.yaml`, help text and startup output must show only `PRISMOS_*` and `.prismos`. Legacy names belong only in the migration guide produced by Task 9.

- [ ] **Step 6: Validate Shell and Compose contracts**

Run:

```bash
bash scripts/test-prismos-env.sh
bash -n scripts/prismos-env.sh scripts/deploy.sh scripts/serve.sh scripts/start-daemon.sh scripts/docker.sh
docker compose config --quiet
docker compose -f docker/docker-compose.yaml config --quiet
touch .env
test -f frontend/.env || cp frontend/.env.example frontend/.env
docker compose -f docker/docker-compose-dev.yaml config --quiet
git grep -In 'OPSINTECH_' -- docker-compose.yml docker config.example.yaml \
  scripts/deploy.sh scripts/serve.sh scripts/start-daemon.sh scripts/docker.sh
```

Expected: tests and Compose validation pass; final grep returns no matches. Only `scripts/prismos-env.sh` and its test may contain legacy environment names.

- [ ] **Step 7: Commit deployment normalization**

```bash
git add scripts/prismos-env.sh scripts/test-prismos-env.sh scripts/deploy.sh \
  scripts/serve.sh scripts/start-daemon.sh scripts/docker.sh docker-compose.yml \
  docker/docker-compose.yaml docker/docker-compose-dev.yaml config.example.yaml
git commit -m "refactor: isolate PrismOS deployment compatibility"
```

---

### Task 6: Implement explicit and reversible home-directory migration

**Files:**
- Create: `backend/packages/harness/deerflow/config/home_migration.py`
- Create: `backend/scripts/migrate_prismos_home.py`
- Create: `backend/tests/test_prismos_home_migration.py`

**Interfaces:**
- Produces: `MigrationPlan`, `MigrationResult`, `plan_home_migration(source: Path, target: Path)`, `apply_home_migration(plan: MigrationPlan)`, `verify_manifest(manifest_path: Path)`.
- CLI: `uv run python scripts/migrate_prismos_home.py --source PATH --target PATH [--apply] [--manifest PATH]`.
- Default behavior is dry-run; `--apply` is required to copy and switch.

- [ ] **Step 1: Write failing migration tests**

Create `backend/tests/test_prismos_home_migration.py` covering:

```python
from pathlib import Path

import pytest

import deerflow.config.home_migration as migration
from deerflow.config.home_migration import apply_home_migration, plan_home_migration, verify_manifest


def test_plan_is_non_mutating_and_counts_files(tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "tenant.db").write_bytes(b"db")
    plan = plan_home_migration(source, target)
    assert plan.file_count == 1
    assert plan.total_bytes == 2
    assert not target.exists()


def test_apply_copies_verifies_and_retains_source(tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "memory.json").write_text('{"ok": true}', encoding="utf-8")
    result = apply_home_migration(plan_home_migration(source, target))
    assert source.exists()
    assert (target / "memory.json").read_text() == '{"ok": true}'
    assert verify_manifest(result.manifest_path).valid is True


def test_existing_nonempty_target_aborts_without_changes(tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir(); target.mkdir()
    (source / "source.db").write_bytes(b"source")
    (target / "keep.db").write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        plan_home_migration(source, target)
    assert (target / "keep.db").read_bytes() == b"keep"


def test_symlink_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    source.mkdir()
    (source / "external").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symbolic link"):
        plan_home_migration(source, tmp_path / ".prismos")


def test_insufficient_space_fails_before_target_creation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "tenant.db").write_bytes(b"database")
    monkeypatch.setattr(migration, "_available_bytes", lambda _path: 0)
    with pytest.raises(OSError, match="Insufficient disk space"):
        plan_home_migration(source, target)
    assert not target.exists()


def test_open_file_risk_fails_preflight(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    source.mkdir()
    (source / "tenant.db").write_bytes(b"database")
    monkeypatch.setattr(
        migration, "_open_files_under", lambda _source: (source / "tenant.db",)
    )
    with pytest.raises(RuntimeError, match="open file"):
        plan_home_migration(source, tmp_path / ".prismos")


def test_unreadable_source_fails_preflight(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    source.mkdir()
    blocked = source / "config.yaml"
    blocked.write_text("x", encoding="utf-8")
    monkeypatch.setattr(migration, "_is_readable", lambda path: path != blocked)
    with pytest.raises(PermissionError, match="config.yaml"):
        plan_home_migration(source, tmp_path / ".prismos")


def test_checksum_mismatch_keeps_source_and_removes_temporary_target(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "memory.json").write_text("{}", encoding="utf-8")
    plan = plan_home_migration(source, target)
    monkeypatch.setattr(migration, "_hash_file", lambda _path: "bad-digest")
    with pytest.raises(ValueError, match="checksum"):
        apply_home_migration(plan)
    assert source.exists()
    assert not target.exists()
    assert not plan.temporary_target.exists()


def test_copy_failure_removes_only_this_run_temporary_target(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "tenant.db").write_bytes(b"db")
    unrelated = tmp_path / ".prismos.migrating-keep"
    unrelated.mkdir()
    plan = plan_home_migration(source, target)

    def fail_copy(*_args) -> None:
        raise OSError("copy interrupted")

    monkeypatch.setattr(migration, "_copy_record", fail_copy)
    with pytest.raises(OSError, match="copy interrupted"):
        apply_home_migration(plan)
    assert source.exists()
    assert unrelated.exists()
    assert not plan.temporary_target.exists()


def test_repeated_apply_is_stable_and_never_deletes_source(tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "tenant.db").write_bytes(b"db")
    plan = plan_home_migration(source, target)
    apply_home_migration(plan)
    with pytest.raises(FileExistsError):
        apply_home_migration(plan)
    assert source.exists()
    assert (target / "tenant.db").read_bytes() == b"db"
```

- [ ] **Step 2: Run tests and confirm the migration module is missing**

Run: `cd backend && uv run pytest tests/test_prismos_home_migration.py -q`

Expected: collection fails for missing `deerflow.config.home_migration`.

- [ ] **Step 3: Implement immutable plan and manifest models**

Use frozen dataclasses with exact fields:

```python
@dataclass(frozen=True)
class FileRecord:
    relative_path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class MigrationPlan:
    source: Path
    target: Path
    temporary_target: Path
    files: tuple[FileRecord, ...]
    total_bytes: int
    manifest_path: Path

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass(frozen=True)
class ManifestVerification:
    valid: bool
    checked_files: int
    errors: tuple[str, ...]


@dataclass(frozen=True)
class MigrationResult:
    target: Path
    manifest_path: Path
    verification: ManifestVerification
```

`plan_home_migration()` must resolve source/target without creating either path; reject a missing/non-directory source, any pre-existing target, a target inside source, symlinks, sockets/FIFOs/devices, unreadable files, and source paths reported by `_open_files_under(source)`. Implement `_open_files_under()` with `lsof +D <source>` when `lsof` is available; parse only file paths under the resolved source, never log process arguments or file contents, and return an empty tuple when `lsof` is unavailable. Walk without following symlinks, hash every regular file with SHA-256, and require free space of at least `total_bytes + max(total_bytes // 10, 1 MiB)` via `_available_bytes(target.parent)`. Set `temporary_target` to `target.parent / f".{target.name}.migrating-{uuid4().hex}"` and `manifest_path` to `target / ".prismos-migration-manifest.json"`.

- [ ] **Step 4: Implement copy, verification, atomic switch, and cleanup**

Create exactly `plan.temporary_target` beside the target. Copy each `FileRecord` through `_copy_record(source, temporary_target, record)`, re-hash every copied file, and compare relative path, size, and digest. Write the JSON manifest at `temporary_target / plan.manifest_path.name`, fsync the manifest and temporary directory, then use `plan.temporary_target.replace(plan.target)` as the single activation step. Before activation, re-check that `plan.target` is absent. On any exception, call `shutil.rmtree(plan.temporary_target)` only when that exact path was created by this invocation; never touch source, target, or similarly named temporary paths.

The manifest must include schema version `1`, UTC timestamp, source, target, file records, total bytes, and status `verified`. `verify_manifest()` resolves the manifest parent as the migrated target, rejects paths escaping that root, and returns a concrete failure such as `ManifestVerification(valid=False, checked_files=0, errors=("missing: tenant.db",))` for missing files; size and checksum failures use the same structure with the affected relative path in `errors`. `apply_home_migration()` returns only after `verify_manifest(plan.manifest_path).valid` is true.

- [ ] **Step 5: Implement the dry-run/apply CLI**

The CLI defaults to `--source ~/.opsintech --target ~/.prismos`, accepts explicit overrides and optional `--manifest` as an additional copy of the generated manifest outside both data directories, and prints source, target, file count, total bytes, open-file result, required/free bytes, and manifest destination. Without `--apply`, it exits 0 after planning and creates nothing. With `--apply`, it prints the verified manifest path, copies the manifest to `--manifest` only after successful activation, and prints this rollback instruction:

```text
Rollback: set PRISMOS_HOME to the preserved source directory; neither copy is deleted automatically.
```

- [ ] **Step 6: Run migration tests and a manual dry-run**

Run:

```bash
cd backend && uv run pytest tests/test_prismos_home_migration.py -q
tmp_root="$(mktemp -d)" && mkdir -p "$tmp_root/.opsintech" && \
  printf '{}' > "$tmp_root/.opsintech/memory.json" && \
  uv run python scripts/migrate_prismos_home.py \
    --source "$tmp_root/.opsintech" --target "$tmp_root/.prismos" && \
  test ! -e "$tmp_root/.prismos"
```

Expected: all tests pass and dry-run leaves no target directory.

- [ ] **Step 7: Commit the migration tool**

```bash
git add backend/packages/harness/deerflow/config/home_migration.py \
  backend/scripts/migrate_prismos_home.py backend/tests/test_prismos_home_migration.py
git commit -m "feat: add reversible PrismOS home migration"
```

---

### Task 7: Migrate browser persistence to PrismOS keys

**Files:**
- Create: `frontend/src/core/storage/brand-migration.ts`
- Create: `frontend/src/core/storage/brand-migration.test.ts`
- Create: `frontend/src/core/storage/brand-consumers.test.ts`
- Modify: `frontend/src/core/settings/local.ts`
- Modify: `frontend/src/core/tenants/store.ts`
- Modify: `frontend/src/core/models/hooks.ts`
- Modify: `frontend/src/core/terminal-agent/chat-history.ts`
- Modify: `frontend/src/core/terminal-agent/security/auto-approval-settings.ts`
- Modify: `frontend/src/core/terminal-agent/security/security-config.ts`
- Create: `frontend/src/core/terminal-agent/terminal-preferences.ts`
- Create: `frontend/src/core/terminal-agent/terminal-preferences.test.ts`
- Modify: `frontend/src/components/workspace/terminal/persistent-terminal.tsx`
- Modify: `frontend/src/core/api/stream-mode.ts`
- Modify: `frontend/src/core/api/stream-mode.test.ts`

**Interfaces:**
- Produces: `readMigratedStorage<T>()`, `writePrismOSStorage()`, `removePrismOSStorage()`.
- Signature: `readMigratedStorage<T>({ storage, key, legacyKey, parse }): T | null`.
- New localStorage keys use `prismos_*`; new browser events use `prismos:*`. Old keys appear only as `legacyKey` arguments in helper consumers and tests.

- [ ] **Step 1: Write failing helper tests**

Create `frontend/src/core/storage/brand-migration.test.ts`:

```typescript
import { beforeEach, describe, expect, it } from "vitest";
import { readMigratedStorage, writePrismOSStorage } from "./brand-migration";

const parseString = (raw: string) => raw;

describe("brand storage migration", () => {
  beforeEach(() => localStorage.clear());

  it("prefers the new key and leaves legacy untouched", () => {
    localStorage.setItem("prismos_test", "new");
    localStorage.setItem("opsintech_test", "old");
    expect(readMigratedStorage({ storage: localStorage, key: "prismos_test",
      legacyKey: "opsintech_test", parse: parseString })).toBe("new");
    expect(localStorage.getItem("opsintech_test")).toBe("old");
  });

  it("copies valid legacy data, verifies it, then removes the old key", () => {
    localStorage.setItem("opsintech_test", "old");
    expect(readMigratedStorage({ storage: localStorage, key: "prismos_test",
      legacyKey: "opsintech_test", parse: parseString })).toBe("old");
    expect(localStorage.getItem("prismos_test")).toBe("old");
    expect(localStorage.getItem("opsintech_test")).toBeNull();
  });

  it("preserves malformed legacy data", () => {
    localStorage.setItem("opsintech_json", "not-json");
    expect(readMigratedStorage({ storage: localStorage, key: "prismos_json",
      legacyKey: "opsintech_json", parse: JSON.parse })).toBeNull();
    expect(localStorage.getItem("opsintech_json")).toBe("not-json");
  });

  it("writes only the new key", () => {
    writePrismOSStorage(localStorage, "prismos_test", "value");
    expect(localStorage.getItem("prismos_test")).toBe("value");
  });

  it("does not delete legacy data when the new write cannot be verified", () => {
    const storage = {
      getItem: (key: string) => key === "opsintech_test" ? "old" : null,
      setItem: () => undefined,
      removeItem: vi.fn(),
    } as unknown as Storage;
    expect(readMigratedStorage({ storage, key: "prismos_test",
      legacyKey: "opsintech_test", parse: parseString })).toBeNull();
    expect(storage.removeItem).not.toHaveBeenCalled();
  });
});
```

Add `vi` to the Vitest import.

- [ ] **Step 2: Run the test and confirm the helper is missing**

Run: `cd frontend && pnpm test:unit -- src/core/storage/brand-migration.test.ts`

Expected: FAIL because `brand-migration.ts` does not exist.

- [ ] **Step 3: Implement read-old/write-new semantics**

Create the helper:

```typescript
export function readMigratedStorage<T>({ storage, key, legacyKey, parse }: {
  storage: Storage; key: string; legacyKey: string; parse: (raw: string) => T;
}): T | null {
  const current = storage.getItem(key);
  if (current !== null) {
    try { return parse(current); } catch { return null; }
  }
  const legacy = storage.getItem(legacyKey);
  if (legacy === null) return null;
  try {
    const parsed = parse(legacy);
    storage.setItem(key, legacy);
    const written = storage.getItem(key);
    if (written !== legacy) return null;
    const verified = parse(written);
    storage.removeItem(legacyKey);
    return verified;
  } catch {
    console.warn(`[PrismOS migration] Unable to migrate legacy browser key to ${key}`);
    return null;
  }
}

export const writePrismOSStorage = (storage: Storage, key: string, value: string) =>
  storage.setItem(key, value);
export const removePrismOSStorage = (storage: Storage, key: string) =>
  storage.removeItem(key);
```

Do not log stored values or old key contents.

- [ ] **Step 4: Convert each consumer and add focused regression tests**

Use these mappings:

```text
opsintech.local-settings              → prismos_local_settings
opsintech.current_tenant_id           → prismos_current_tenant_id
opsintech:models:disabled             → prismos_models_disabled
opsintech_terminal_chats              → prismos_terminal_chats
opsintech_auto_approval_settings      → prismos_auto_approval_settings
opsintech_terminal_security_config    → prismos_terminal_security_config
opsintech_terminal_theme              → prismos_terminal_theme
opsintech_host_sidebar_collapsed      → prismos_host_sidebar_collapsed
opsintech:* event names               → prismos:*
```

Use `readMigratedStorage()` in each read path, and `writePrismOSStorage()` / `removePrismOSStorage()` in each mutation path. Parsers must validate the outer shape before accepting migration: object for local/security settings, string array for disabled models and chat sessions, enum membership for terminal theme, and `"true" | "false"` for sidebar state. New code dispatches only `prismos:tenant-changed`; the baseline repository search shows no old-event listener, so do not create a dual-event publisher.

Extract terminal theme/sidebar storage from the React component into `terminal-preferences.ts`:

```typescript
import { readMigratedStorage, writePrismOSStorage } from "@/core/storage/brand-migration";

export type TerminalTheme = "light" | "dark" | "hacker";

export const loadTerminalTheme = (storage: Storage): TerminalTheme | null =>
  readMigratedStorage({ storage, key: "prismos_terminal_theme",
    legacyKey: "opsintech_terminal_theme", parse: (raw) => {
      if (!(["light", "dark", "hacker"] as string[]).includes(raw)) throw new Error("theme");
      return raw as TerminalTheme;
    }});

export const saveTerminalTheme = (storage: Storage, value: TerminalTheme) =>
  writePrismOSStorage(storage, "prismos_terminal_theme", value);

export const loadHostSidebarCollapsed = (storage: Storage): boolean | null =>
  readMigratedStorage({ storage, key: "prismos_host_sidebar_collapsed",
    legacyKey: "opsintech_host_sidebar_collapsed", parse: (raw) => {
      if (raw !== "true" && raw !== "false") throw new Error("boolean");
      return raw === "true";
    }});

export const saveHostSidebarCollapsed = (storage: Storage, value: boolean) =>
  writePrismOSStorage(storage, "prismos_host_sidebar_collapsed", String(value));
```

- [ ] **Step 5: Add concrete consumer regression tests**

Create `frontend/src/core/storage/brand-consumers.test.ts`:

```typescript
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getLocalSettings, saveLocalSettings, DEFAULT_LOCAL_SETTINGS } from "@/core/settings/local";
import { getDisabledModelsStore, setDisabledModelsStore } from "@/core/models/hooks";
import { ChatHistoryManager } from "@/core/terminal-agent/chat-history";
import { AutoApprovalManager } from "@/core/terminal-agent/security/auto-approval-settings";
import { SecurityConfigManager } from "@/core/terminal-agent/security/security-config";

describe("PrismOS branded storage consumers", () => {
  beforeEach(() => localStorage.clear());

  it("migrates local settings and writes only the canonical key", () => {
    localStorage.setItem("opsintech.local-settings", JSON.stringify(DEFAULT_LOCAL_SETTINGS));
    expect(getLocalSettings()).toMatchObject(DEFAULT_LOCAL_SETTINGS);
    saveLocalSettings(DEFAULT_LOCAL_SETTINGS);
    expect(localStorage.getItem("prismos_local_settings")).not.toBeNull();
    expect(localStorage.getItem("opsintech.local-settings")).toBeNull();
  });

  it("migrates disabled models and writes only the canonical key", () => {
    localStorage.setItem("opsintech:models:disabled", '["legacy-model"]');
    expect(getDisabledModelsStore()).toEqual(["legacy-model"]);
    setDisabledModelsStore(["new-model"]);
    expect(localStorage.getItem("prismos_models_disabled")).toBe('["new-model"]');
  });

  it("migrates terminal chat history", () => {
    localStorage.setItem("opsintech_terminal_chats", "[]");
    expect(ChatHistoryManager.loadSessions()).toEqual([]);
    expect(localStorage.getItem("prismos_terminal_chats")).toBe("[]");
    expect(localStorage.getItem("opsintech_terminal_chats")).toBeNull();
  });

  it("migrates auto-approval and security settings", () => {
    localStorage.setItem("opsintech_auto_approval_settings", '{"enabled":true}');
    localStorage.setItem("opsintech_terminal_security_config", '{"enableCommandSecurity":false}');
    expect(new AutoApprovalManager().getSettings().enabled).toBe(true);
    expect(new SecurityConfigManager().getConfig().enableCommandSecurity).toBe(false);
    expect(localStorage.getItem("prismos_auto_approval_settings")).not.toBeNull();
    expect(localStorage.getItem("prismos_terminal_security_config")).not.toBeNull();
  });

  it("keeps malformed legacy objects and falls back safely", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    localStorage.setItem("opsintech.local-settings", "[]");
    expect(getLocalSettings()).toEqual(DEFAULT_LOCAL_SETTINGS);
    expect(localStorage.getItem("opsintech.local-settings")).toBe("[]");
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
```

Create `frontend/src/core/terminal-agent/terminal-preferences.test.ts`:

```typescript
import { beforeEach, describe, expect, it } from "vitest";
import {
  loadHostSidebarCollapsed, loadTerminalTheme,
  saveHostSidebarCollapsed, saveTerminalTheme,
} from "./terminal-preferences";

describe("terminal preference migration", () => {
  beforeEach(() => localStorage.clear());

  it("migrates valid legacy preferences", () => {
    localStorage.setItem("opsintech_terminal_theme", "hacker");
    localStorage.setItem("opsintech_host_sidebar_collapsed", "true");
    expect(loadTerminalTheme(localStorage)).toBe("hacker");
    expect(loadHostSidebarCollapsed(localStorage)).toBe(true);
    expect(localStorage.getItem("opsintech_terminal_theme")).toBeNull();
    expect(localStorage.getItem("opsintech_host_sidebar_collapsed")).toBeNull();
  });

  it("writes only canonical preferences", () => {
    saveTerminalTheme(localStorage, "dark");
    saveHostSidebarCollapsed(localStorage, false);
    expect(localStorage.getItem("prismos_terminal_theme")).toBe("dark");
    expect(localStorage.getItem("prismos_host_sidebar_collapsed")).toBe("false");
  });
});
```

Add a tenant test in `frontend/src/core/tenants/store.test.ts` using a fresh module for its module-level cache:

```typescript
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("tenant storage migration", () => {
  beforeEach(() => { localStorage.clear(); vi.resetModules(); });

  it("migrates the tenant key and emits only the PrismOS event", async () => {
    localStorage.setItem("opsintech.current_tenant_id", "tenant-1");
    const legacy = vi.fn();
    const canonical = vi.fn();
    window.addEventListener("opsintech:tenant-changed", legacy);
    window.addEventListener("prismos:tenant-changed", canonical);
    const store = await import("./store");
    expect(store.getCurrentTenantId()).toBe("tenant-1");
    store.setCurrentTenantId("tenant-2");
    expect(localStorage.getItem("prismos_current_tenant_id")).toBe("tenant-2");
    expect(legacy).not.toHaveBeenCalled();
    expect(canonical).toHaveBeenCalledOnce();
  });
});
```

Update `stream-mode.test.ts` with an assertion that the warning starts with `[PrismOS]` and contains no legacy brand.

- [ ] **Step 6: Run frontend migration and dependent tests**

Run:

```bash
cd frontend && pnpm test:unit -- \
  src/core/storage/brand-migration.test.ts \
  src/core/storage/brand-consumers.test.ts \
  src/core/tenants/store.test.ts \
  src/core/terminal-agent/terminal-preferences.test.ts \
  src/core/api/stream-mode.test.ts
pnpm typecheck
```

Expected: all focused tests pass and typecheck exits 0.

- [ ] **Step 7: Prove old keys are isolated to migration arguments/tests**

Run:

```bash
git grep -In 'opsintech[.:_]' -- frontend/src \
  ':!frontend/src/core/storage/brand-migration.test.ts'
```

Expected: matches only occur in explicit `legacyKey` arguments and migration tests; no `setItem`, event dispatch, filename, or UI copy writes an old name.

- [ ] **Step 8: Commit browser-state migration**

```bash
git add frontend/src/core/storage frontend/src/core/settings frontend/src/core/tenants \
  frontend/src/core/models/hooks.ts frontend/src/core/terminal-agent \
  frontend/src/components/workspace/terminal/persistent-terminal.tsx \
  frontend/src/core/api/stream-mode.ts
git commit -m "feat: migrate browser state to PrismOS keys"
```

---

### Task 8: Rename internal terminal protocol markers and User-Agent identity

**Files:**
- Modify: `backend/app/agent/terminal_graph.py`
- Modify: `backend/app/agent/terminal_tools.py`
- Modify: `backend/app/gateway/routers/terminal.py`
- Modify: `backend/app/services/terminal/session.py`
- Modify: `backend/tests/test_terminal_security.py`
- Modify: `backend/tests/test_terminal_multihost.py`
- Delete: `backend/scratch_test.py` after its useful marker cases are moved into collected pytest tests.

**Interfaces:**
- Produces: `PRISMOS_EOF`, `__PRISMOS_MARKER_<uuid>__`, `PrismOS/0.2` User-Agent, `_new_command_marker() -> str`, `_strip_command_markers(data: str) -> str`.
- Produces in `terminal_tools.py`: `_build_write_file_command(path: str, content: str) -> str` and `_build_web_fetch_command(url: str) -> str`; `terminal_graph.py` imports both instead of duplicating command construction.
- Produces in `routers/terminal.py`: `_build_web_fetch_argv(url: str) -> list[str]` for the compatible browser User-Agent form.
- No compatibility adapter is needed if repository audit proves markers are neither persisted nor consumed externally.

- [ ] **Step 1: Add failing protocol identity tests**

Add to `backend/tests/test_terminal_multihost.py`:

```python
from app.services.terminal.session import _new_command_marker, _strip_command_markers


def test_terminal_marker_uses_prismos_identity() -> None:
    marker = _new_command_marker()
    assert marker.startswith("__PRISMOS_MARKER_")
    assert "OPSINTECH" not in marker


def test_terminal_output_strips_prismos_marker() -> None:
    marker = "__PRISMOS_MARKER_abc__"
    assert _strip_command_markers(f"hello\n{marker}\n") == "hello\n"


def test_terminal_output_preserves_lines_around_marker() -> None:
    marker = "__PRISMOS_MARKER_abc__"
    assert _strip_command_markers(f"before\n{marker}\nafter\n") == "before\nafter\n"
```

Implement these helpers at module scope in `app/services/terminal/session.py`; use them in both `_on_pty_output()` and `execute_command()` so marker filtering has one implementation. `_strip_command_markers()` removes only complete lines containing `__PRISMOS_MARKER_`, preserves every non-marker line and its line endings, and never strips arbitrary text merely because it surrounds a marker.

- [ ] **Step 2: Run focused tests and confirm old markers fail**

Run: `cd backend && uv run pytest tests/test_terminal_security.py tests/test_terminal_multihost.py -q`

Expected: new identity assertions fail against old marker generation.

- [ ] **Step 3: Audit producer/consumer and persistence boundaries**

Run:

```bash
git grep -In -e '__OPSINTECH_MARKER_' -e 'OPSINTECH_EOF' -- \
  ':!docs/superpowers/**' ':!docs/releases/**'
```

Expected pre-change matches are exactly `terminal_graph.py`, `terminal_tools.py`, `session.py`, and `scratch_test.py`; the current baseline has no persisted or external consumer. If the audit finds a new database model, external plugin protocol, or serialized task fixture, do not continue this task: record the path and add a dedicated protocol-adapter task to this plan with removal version `0.3.0` before implementation resumes.

- [ ] **Step 4: Rename internal markers and User-Agent strings**

Apply exact values:

```text
OPSINTECH_EOF              → PRISMOS_EOF
__OPSINTECH_MARKER_        → __PRISMOS_MARKER_
OpsinTech/1.0              → PrismOS/0.2
Mozilla/5.0 (compatible; OpsinTech/1.0) → Mozilla/5.0 (compatible; PrismOS/0.2)
```

Convert useful marker cases from `backend/scratch_test.py` into pytest assertions and delete the scratch file; do not preserve an uncollected script as compatibility evidence.

Extract the exact pure helpers declared in this task's Interfaces. Add these direct assertions to `backend/tests/test_terminal_security.py`:

```python
from app.agent.terminal_tools import _build_web_fetch_command, _build_write_file_command
from app.gateway.routers.terminal import _build_web_fetch_argv


def test_write_file_command_uses_prismos_heredoc() -> None:
    command = _build_write_file_command("/tmp/report.txt", "hello")
    assert command.count("PRISMOS_EOF") == 2
    assert "OPSINTECH_EOF" not in command


def test_web_fetch_commands_use_prismos_user_agents() -> None:
    command = _build_web_fetch_command("https://example.com")
    argv = _build_web_fetch_argv("https://example.com")
    assert "User-Agent: PrismOS/0.2" in command
    assert "User-Agent: Mozilla/5.0 (compatible; PrismOS/0.2)" in argv
    assert "OpsinTech" not in command
    assert all("OpsinTech" not in part for part in argv)
```

Use `_build_write_file_command()` and `_build_web_fetch_command()` in both `terminal_tools.py` and `terminal_graph.py`; use `_build_web_fetch_argv()` in `web_fetch_proxy()`. The heredoc helper must preserve the current single-quote escaping behavior and the fetch helpers must preserve timeout, redirect, output-limit, and URL validation behavior.

- [ ] **Step 5: Run protocol tests and legacy search**

Run:

```bash
cd backend && uv run pytest tests/test_terminal_security.py tests/test_terminal_multihost.py \
  tests/test_terminal_trimming.py -q
cd .. && git grep -In -e '__OPSINTECH_MARKER_' -e 'OPSINTECH_EOF' -e 'OpsinTech/1.0' -- \
  ':!docs/superpowers/**' ':!docs/releases/**'
```

Expected: tests pass and grep returns no matches.

- [ ] **Step 6: Commit internal protocol identity**

```bash
git add backend/app/agent/terminal_graph.py backend/app/agent/terminal_tools.py \
  backend/app/gateway/routers/terminal.py backend/app/services/terminal/session.py \
  backend/tests/test_terminal_security.py backend/tests/test_terminal_multihost.py \
  backend/tests/test_terminal_trimming.py backend/scratch_test.py
git commit -m "refactor: rename PrismOS internal protocol markers"
```

---

### Task 9: Rewrite active documentation and classify historical records

**Files:**
- Modify: `README.md`, `README_zh.md`, `QUICKSTART.md`, `QUICKSTART_zh.md`
- Modify: `backend/README.md`, `backend/README_zh.md`
- Modify: `frontend/README.md`
- Modify: `backend/docs/API.md`, `backend/docs/ARCHITECTURE.md`, `backend/docs/README.md`, `backend/docs/SETUP.md`, `backend/docs/CONFIGURATION.md`
- Modify: `docker/provisioner/README.md`
- Create: `docs/migrations/prismos-brand-migration.md`
- Create: `docs/migrations/prismos-legacy-bridge-removal.md`
- Modify: `docs/releases/v0.1.0-alpha.1.md`, `docs/releases/v0.1.0-alpha.2.md`
- Modify: `docs/superpowers/plans/2026-07-19-v1.1-platform-slimming.md`
- Modify: `docs/superpowers/plans/2026-07-25-v1.2-agent-loop-primitive.md`
- Modify: `docs/superpowers/plans/2026-08-07-prismos-project-publishing.md`
- Modify: `docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v2.md`
- Modify: `docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v3.md`
- Modify: `docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v4.md`
- Modify: `docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v5.md`
- Modify: `docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v6.md`
- Modify: `docs/superpowers/specs/2026-08-07-prismos-project-publishing-design.md`
- Modify: `docs/superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md`
- Modify: `docs/superpowers/plans/2026-08-08-prismos-governed-foundation-contract-baseline.md`
- Modify: `.github/ISSUE_TEMPLATE/bug_report.md`
- Modify: `.github/ISSUE_TEMPLATE/feature_request.md`
- Modify: `.github/ISSUE_TEMPLATE/config.yml`
- Modify: `.github/PULL_REQUEST_TEMPLATE.md`
- Create: `.github/RELEASE_TEMPLATE.md`
- Modify: `.gitignore`, `.dockerignore` only to preserve ignored legacy user-data paths alongside new paths.

**Interfaces:**
- Produces: canonical migration command, rollback instructions, compatibility matrix, removal checklist, active docs with no old names.
- Historical banner exact text: `> **Legacy / Historical:** This document records an earlier project state and may contain superseded product names or compatibility decisions.`

- [ ] **Step 1: Add a failing active-document identity check**

Extend `scripts/test-prismos-product-identity.sh` with an exact active-doc list and fail if any contains old branding:

```bash
active_docs=(
  README.md README_zh.md QUICKSTART.md QUICKSTART_zh.md
  backend/README.md backend/README_zh.md frontend/README.md
  backend/docs/API.md backend/docs/ARCHITECTURE.md backend/docs/README.md
  backend/docs/SETUP.md backend/docs/CONFIGURATION.md docker/provisioner/README.md
  .github/ISSUE_TEMPLATE/bug_report.md .github/ISSUE_TEMPLATE/feature_request.md
  .github/ISSUE_TEMPLATE/config.yml .github/PULL_REQUEST_TEMPLATE.md
  .github/RELEASE_TEMPLATE.md
)
if rg -n -i 'opsintech|opsintech-platform' "${active_docs[@]}"; then
  echo 'active documentation contains legacy branding' >&2
  exit 1
fi
```

- [ ] **Step 2: Run the identity test and confirm active docs fail**

Run: `bash scripts/test-prismos-product-identity.sh`

Expected: FAIL with current README/backend documentation matches.

- [ ] **Step 3: Rewrite active documents around PrismOS-only usage**

Active docs must show:

- clone URL `https://github.com/yespon/prism-os`;
- local directory `prism-os`;
- `.prismos` paths and `PRISMOS_*` examples only;
- `prismos-*` containers/buckets/resources;
- current API paths unchanged;
- DeerFlow/LangGraph described as runtime dependencies, not product identity;
- AI operations described only as a validation scenario.

Do not explain old input names in active Quickstart/README; link to the migration guide instead.

Update Issue and PR templates so prompts, links, labels, and examples identify PrismOS. Create `.github/RELEASE_TEMPLATE.md` with exact sections for version, compatibility/removal boundary, migration command, rollback, verification evidence, image/package coordinates, known limitations, and breaking changes. It must refer to `yespon/prism-os`, `ghcr.io/yespon/prism-os`, and `PRISMOS_*` only.

- [ ] **Step 4: Write the migration and removal guides**

`docs/migrations/prismos-brand-migration.md` must include:

```text
Migration release: 0.2.x
Runtime compatibility removal: 0.3.0
Preflight: uv run python scripts/migrate_prismos_home.py --source ~/.opsintech --target ~/.prismos
Apply: add --apply
Rollback: set PRISMOS_HOME to the preserved source
Conflict behavior: PRISMOS_* wins; invalid PRISMOS_* never falls back
Browser behavior: read old once, verify new, write only new
Object storage: detect and plan only; no automatic remote copy/delete
```

`docs/migrations/prismos-legacy-bridge-removal.md` is an executable `0.3.0` checklist: remove legacy aliases from Python/Shell/frontend helpers, reduce runtime allowlist to zero, keep the offline home migration CLI, run all gates, and publish the breaking-change note.

Both guides start with `#` titles; migration documentation is allowlisted as `migration-document`, not marked historical. The migration guide must enumerate every environment alias from `LEGACY_ENV_ALIASES`, every localStorage mapping from Task 7, the legacy remote-resource detector, and the exact `0.3.0` owner/checklist item for each runtime compatibility entry.

- [ ] **Step 5: Mark historical files without rewriting facts**

Add the exact `Legacy / Historical` banner immediately below the first `#` title in these files:

```text
docs/releases/v0.1.0-alpha.1.md
docs/releases/v0.1.0-alpha.2.md
docs/superpowers/plans/2026-07-19-v1.1-platform-slimming.md
docs/superpowers/plans/2026-07-25-v1.2-agent-loop-primitive.md
docs/superpowers/plans/2026-08-07-prismos-project-publishing.md
docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v2.md
docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v3.md
docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v4.md
docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v5.md
docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v6.md
docs/superpowers/specs/2026-08-07-prismos-project-publishing-design.md
```

Do not rewrite their historical commands, identifiers, or decisions. The current brand migration design/plan and migration guides are `migration-document`, not historical documents.

Update `2026-08-07-prismos-project-publishing-design.md` with an additional note that its indefinite compatibility decision is superseded by the brand-root migration design.

Keep the current roadmap and M1 handoff active: in `2026-08-08-prismos-capability-roadmap-design.md`, change the project path to `prism-os` and link the bounded migration guide instead of presenting old inputs as a standing boundary. In `2026-08-08-prismos-governed-foundation-contract-baseline.md`, replace the three `OPSINTECH_CONFIG_PATH` verification assignments with `PRISMOS_CONFIG_PATH` and remove the sentence requiring the old variable.

- [ ] **Step 6: Verify active docs, links, and Shell test**

Run:

```bash
bash scripts/test-prismos-product-identity.sh
rg -n -i 'opsintech|opsintech-platform' README.md README_zh.md QUICKSTART.md QUICKSTART_zh.md \
  backend/README.md backend/README_zh.md frontend/README.md backend/docs docker/provisioner/README.md
rg -L 'Legacy / Historical' docs/releases/v0.1.0-alpha.1.md docs/releases/v0.1.0-alpha.2.md
rg -n 'OPSINTECH_|\.opsintech|prism-platform' \
  docs/superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md \
  docs/superpowers/plans/2026-08-08-prismos-governed-foundation-contract-baseline.md
git diff --check
```

Expected: both active-doc searches and active-roadmap search return no matches; historical release docs contain the banner; diff check passes.

- [ ] **Step 7: Commit documentation migration**

```bash
git add README.md README_zh.md QUICKSTART.md QUICKSTART_zh.md backend/README.md \
  backend/README_zh.md frontend/README.md backend/docs docker/provisioner/README.md \
  .github/ISSUE_TEMPLATE .github/PULL_REQUEST_TEMPLATE.md .github/RELEASE_TEMPLATE.md \
  docs/migrations docs/releases docs/superpowers .gitignore .dockerignore \
  scripts/test-prismos-product-identity.sh
git commit -m "docs: complete PrismOS brand migration guidance"
```

---

### Task 10: Shrink the allowlist, wire CI, and publish the 0.2.x contract

**Files:**
- Modify: `config/brand-legacy-allowlist.json`
- Modify: `.github/workflows/docker-build.yml`
- Modify: `.github/workflows/container-publish.yml`
- Modify: `backend/pyproject.toml`
- Modify: `frontend/package.json`
- Modify: `frontend/pnpm-lock.yaml`
- Create: `docs/releases/v0.2.0-alpha.1.md`

**Interfaces:**
- CI command: `uv run --offline python scripts/check_brand_identity.py`.
- Bridge release: `0.2.0-alpha.1`; compatibility family `0.2.x`; removal version `0.3.0`.
- Runtime allowlist classifications: `compatibility-code`, `migration-tool`, `test-fixture`, `migration-document`, `historical-document`.

- [ ] **Step 1: Run the scanner and capture all remaining matches**

Run: `uv run --offline python scripts/check_brand_identity.py`

Expected: FAIL, listing every still-unclassified old-name match after Tasks 2–9.

- [ ] **Step 2: Classify each legitimate remaining file with an exact entry**

For each scanner-reported file, either remove a prohibited match or add one exact-path entry whose `max_matches` equals that file's scanner count. Use `remove_by: "0.3.0"` for runtime compatibility, frontend migration consumers and their tests; `remove_by: "never-historical"` only for the 11 historical files listed in Task 9; and `remove_by: "offline-tool-retained"` only for home-migration implementation/tests and legacy data ignore rules.

Expected legitimate categories include:

- `backend/packages/harness/deerflow/config/prismos_env.py` and its tests;
- `scripts/prismos-env.sh` and its tests;
- `home_migration.py`, CLI and tests;
- frontend storage migration helper/consumers and tests;
- `.gitignore` and `.dockerignore` legacy data exclusions;
- migration documents and explicitly marked historical plans/specs/releases.

Do not allowlist public UI, active docs, default values, Compose files, prompts, User-Agent strings, marker names, or production writes to old browser keys.

After editing, run this consistency check so an entry cannot silently outlive all of its matches:

```bash
uv run --offline python - <<'PY'
import importlib.util, json, sys
from pathlib import Path
root = Path.cwd()
spec = importlib.util.spec_from_file_location("brand_gate", root / "scripts/check_brand_identity.py")
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
allowlist = json.loads((root / "config/brand-legacy-allowlist.json").read_text())
counts = {}
for match in module.scan_paths(root, module.tracked_paths(root)):
    counts[match.path] = counts.get(match.path, 0) + 1
for entry in allowlist["entries"]:
    assert counts.get(entry["path"], 0) == entry["max_matches"], entry
PY
```

- [ ] **Step 3: Add the blocking gate to both workflows**

After the existing `Set up uv` step and before environment compatibility tests in both workflow `validate` jobs, add:

```yaml
- name: Enforce PrismOS brand identity
  run: uv run --offline python scripts/check_brand_identity.py
```

Keep environment compatibility tests after this gate. A new unallowlisted old name must prevent build and publish.

- [ ] **Step 4: Set the bridge release identity**

Set `backend/pyproject.toml` to PEP 440 version `0.2.0a1` and `frontend/package.json` to `0.2.0-alpha.1`; update both root importer version occurrences in `frontend/pnpm-lock.yaml` by running `cd frontend && pnpm install --lockfile-only`.

Create release notes stating this is the one-minor compatibility bridge, listing migration commands, rollback, known limits, and mandatory `0.3.0` removal.

- [ ] **Step 5: Verify the GitHub public surface without mutating remote state**

Run read-only checks against `yespon/prism-os`:

```bash
gh repo view yespon/prism-os \
  --json nameWithOwner,isFork,isPrivate,description,homepageUrl,repositoryTopics
gh release list --repo yespon/prism-os --limit 10
gh api '/user/packages?package_type=container' --paginate \
  --jq '.[] | select(.name == "prism-os") | {name,visibility,package_type}'
```

Expected repository metadata:

```text
nameWithOwner: yespon/prism-os
isFork: false
isPrivate: true
description: PrismOS is a governed Agent operating system for enterprise teams, with multi-tenant control, RBAC, sandboxed execution, Skills, MCP, artifacts, and an extensible runtime foundation.
homepageUrl: https://github.com/yespon/prism-os
topics: agentos, ai-agents, agent-platform, agent-governance, agent-runtime, mcp,
        langgraph, multi-tenant, sandboxed-execution, enterprise-ai, agentops,
        python, nextjs, docker
```

Existing GitHub releases and the `prism-os` container package must contain no first-party old-brand metadata. This task verifies existing remote state and does not publish `0.2.0-alpha.1` or change package visibility.

If a mismatch is found, record the exact field and stop the remote portion for explicit user authorization. After authorization, use only the narrow `gh repo edit`, `gh api --method PATCH`, or release/package metadata operation needed for that field, then rerun all three read-only checks. Never delete a release, package, image version, or tag as part of brand cleanup.

- [ ] **Step 6: Run brand, version, workflow, and identity checks**

Run:

```bash
uv run --offline python scripts/check_brand_identity.py
bash scripts/test-prismos-env.sh
bash scripts/test-prismos-product-identity.sh
uv run --offline python - <<'PY'
import tomllib
from pathlib import Path
version = tomllib.loads(Path('backend/pyproject.toml').read_text())['project']['version']
assert version == '0.2.0a1', version
PY
node -e "const p=require('./frontend/package.json'); if(p.version!=='0.2.0-alpha.1') process.exit(1)"
docker compose config --quiet
docker compose -f docker/docker-compose.yaml config --quiet
git diff --check
```

Expected: all commands exit 0 and scanner reports only allowlisted matches at or below their ceilings.

- [ ] **Step 7: Commit the bounded release gate**

```bash
git add config/brand-legacy-allowlist.json scripts/check_brand_identity.py \
  .github/workflows/docker-build.yml .github/workflows/container-publish.yml \
  backend/pyproject.toml frontend/package.json frontend/pnpm-lock.yaml \
  docs/releases/v0.2.0-alpha.1.md
git commit -m "ci: enforce PrismOS brand migration boundary"
```

---

### Task 11: Run full verification, rename the local repository directory, and hand off to M1

**Files:**
- No tracked file edits are planned in this task; a verification failure returns to its owning Task 1–10 for a new tested commit before Task 11 restarts.
- Operational rename: `/Users/yespon/Documents/AgentOS/prism-platform` → `/Users/yespon/Documents/AgentOS/prism-os`.
- Preserve untracked `.superpowers/` without staging or deleting it.

**Interfaces:**
- Consumes all previous tasks.
- Produces a verified PrismOS-branded repository at the canonical local path, ready for `2026-08-08-prismos-governed-foundation-contract-baseline.md`.

- [ ] **Step 1: Run final old-name audit and inspect every allowlisted result**

Run:

```bash
uv run --offline python scripts/check_brand_identity.py
git grep -In -e 'OpsinTech' -e 'opsintech' -e 'OPSINTECH' -- \
  ':!docs/superpowers/**' ':!docs/releases/**' ':!docs/migrations/**'
```

Expected: the scanner passes. Manual grep matches only compatibility modules/tests, migration tools, frontend legacy-key reads, and ignored legacy-data rules represented in the allowlist.

- [ ] **Step 2: Run complete backend verification**

Run:

```bash
cd backend
uv run pytest --collect-only -q
uv run pytest -q
uv run ruff check app packages/harness/deerflow tests scripts
```

Expected: collection succeeds; all non-environmental tests pass; any pre-existing skip is reported, not converted into a pass. No failure may be waived as “branding-only.”

- [ ] **Step 3: Run complete frontend verification**

Run:

```bash
cd frontend
pnpm test:unit
pnpm typecheck
pnpm lint
pnpm build
```

Expected: all commands exit 0. Before execution begins, record baseline results for `pnpm lint` and `pnpm build`; if either already fails on the Task 1 commit, require the post-migration command to have exactly the same failures and attach both outputs to the handoff. Any new or changed failure returns to the task that touched the failing file; do not weaken CI or tests.

- [ ] **Step 4: Run deployment and repository verification**

Run:

```bash
cd ..
bash scripts/test-prismos-env.sh
bash scripts/test-prismos-product-identity.sh
bash -n scripts/*.sh
docker compose config --quiet
docker compose -f docker/docker-compose.yaml config --quiet
docker compose -f docker/docker-compose-dev.yaml config --quiet
git diff --check
git status --short --branch
```

Expected: all static/runtime configuration checks pass. `git status` shows no tracked changes; `.superpowers/` may remain untracked.

- [ ] **Step 5: Check for hard-coded old absolute workspace paths**

Run:

```bash
git grep -In '/Users/yespon/Documents/AgentOS/prism-platform\|/prism-platform/' -- .
```

Expected: matches occur only in exact `historical-document` allowlist entries. Any active code, migration guide, current roadmap, current implementation plan, IDE configuration, or automation match blocks the move and returns to Task 9.

- [ ] **Step 6: Rename the local directory from its parent**

Stop local dev servers and terminals whose working directory is inside the repository. From `/Users/yespon/Documents/AgentOS`, run:

```bash
mv /Users/yespon/Documents/AgentOS/prism-platform /Users/yespon/Documents/AgentOS/prism-os
```

This is a local workspace-shell operation, not a Git content change. First run `test ! -e /Users/yespon/Documents/AgentOS/prism-os`; a nonzero result blocks the move and must be reported for user resolution—do not merge, delete, or overwrite that path.

- [ ] **Step 7: Verify Git identity after the directory move**

Run from the new path:

```bash
cd /Users/yespon/Documents/AgentOS/prism-os
git status --short --branch
git remote -v
git log -5 --oneline
```

Expected: branch and commit history are unchanged; remote is `https://github.com/yespon/prism-os.git`; only the previously known `.superpowers/` remains untracked.

- [ ] **Step 8: Record the implementation handoff**

Report:

- exact commits for Tasks 1–10;
- backend/frontend/Compose verification outputs;
- final allowlist counts by classification and removal version;
- canonical new local path;
- bridge release `0.2.x` and removal release `0.3.0`;
- any real external blocker without claiming completion.
- read-only GitHub About/Topics/Release/Packages evidence, plus any separately authorized metadata correction.

After this handoff, execute `docs/superpowers/plans/2026-08-08-prismos-governed-foundation-contract-baseline.md`. Do not start M1/P0 before Tasks 1–11 are complete.

---

## Commit and Integration Sequence

1. `test: establish PrismOS brand identity gate`
2. Wave 1 parallel commits:
   - `refactor: establish PrismOS public brand identity`
   - `feat: add bounded PrismOS legacy input adapter`
   - `feat: add reversible PrismOS home migration`
   - `feat: migrate browser state to PrismOS keys`
   - `refactor: rename PrismOS internal protocol markers`
3. Wave 2 commits:
   - `refactor: normalize PrismOS runtime settings`
   - `refactor: isolate PrismOS deployment compatibility`
   - `docs: complete PrismOS brand migration guidance`
4. `ci: enforce PrismOS brand migration boundary`
5. Final verification and local directory rename; no commit is created solely for the filesystem move.

For Subagent-Driven execution, dispatch one implementation subagent per task and apply two review gates before merge: first check the task against this plan/spec, then review code quality and test evidence. Tasks 4 and 5 must wait for Task 3. Task 10 must wait for Tasks 2–9. Task 11 is strictly serial and last.
