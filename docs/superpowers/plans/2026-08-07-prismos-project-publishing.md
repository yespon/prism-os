# PrismOS Project Publishing Implementation Plan

> **Legacy / Historical:** This document records an earlier project state and may contain superseded product names or compatibility decisions.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 `prism-platform` 一致地发布为 PrismOS：完成项目身份、文档、运行时兼容边界、Docker/CI、GHCR 首个预发布版本及 GitHub 项目元数据的闭环，并保持现有 DeerFlow/LangGraph 能力、API 路径、数据库迁移和已有用户数据可用。

**Architecture:** PrismOS 是面向企业 Agent 的治理型操作系统/平台。当前实现继续以 DeerFlow/LangGraph 为 Agent 执行内核；本次工作只建立清晰的产品边界和发布基础，不把尚未实现的 Policy、Task/Run、Workflow、Evaluation、Connector、Federation 宣称为已完成能力。新身份采用 `prismos`、`prismos-frontend`、`ghcr.io/yespon/prism-os` 和 `PRISMOS_*`；旧的 `OPSINTECH_*` 作为兼容输入，解析优先级为 `PRISMOS_* → OPSINTECH_* → 默认值`。

**Tech Stack:** Python 3.12 + uv + FastAPI + LangGraph/DeerFlow harness；Next.js + React + TypeScript + pnpm；Docker Compose/Buildx；GitHub Actions；GitHub Container Registry (GHCR)。

## Global Constraints

- 不改名 `deerflow` Python import、DeerFlow/LangGraph adapter、API path、数据库表和 Alembic migration。
- 不删除历史 Git tag `b20c668`，不重写 Git 历史，不自动搬迁或删除 `backend/.opsintech` 等已有数据目录。
- 新部署使用 PrismOS 默认身份；若新目录不存在而旧 `.opsintech` 数据目录存在且未显式设置新路径，自动兼容读取旧目录，并允许显式 `PRISMOS_*` 覆盖。
- 不新增 PyPI/npm 发布；本次唯一包交付为 GHCR OCI 镜像。
- 不使用全局机械替换处理 `OpsinTech/opsintech`；展示文本、仓库链接、容器标识、脚本和配置分别处理，并保留必要的兼容键与历史目录。
- 首个版本固定为 `v0.1.0-alpha.1`，GitHub Release 标为 pre-release；不创建 `latest` tag。
- 每个任务完成后执行验收命令；最终只能基于实际命令输出声明完成。

## Target File Map

| Area | Primary files | Expected result |
| --- | --- | --- |
| Product identity | `backend/pyproject.toml`, `frontend/package.json`, `backend/app/gateway/app.py` | 新的 Python/frontend/API identity；保留运行时 import |
| Compatibility | `scripts/prismos-env.sh`, `config.example.yaml`, Compose files, deploy/start scripts | 新旧环境变量共存，明确优先级和旧数据目录策略 |
| Public docs | `README.md`, `README_zh.md`, `QUICKSTART*.md`, `CONTRIBUTING.md`, `SECURITY.md` | 双语、真实能力基线、路线图、发布说明入口 |
| Build and publish | `.github/workflows/docker-build.yml`, `.github/workflows/container-publish.yml` | CI 仅验证；release tag 才推送 GHCR，多架构且可追溯 |
| Release artifact | `docs/releases/v0.1.0-alpha.1.md` | 本地可审阅的正式 release notes |
| GitHub metadata | GitHub About/Topics/Release/Packages | `yespon/prism-os` 的项目页与首个预发布版本一致 |

---

## Task 1: Establish identity and compatibility boundary

**Files:** `scripts/prismos-env.sh` (new), `config.example.yaml`, `docker-compose.yml`, `docker/docker-compose.yaml`, `docker/docker-compose-dev.yaml`, scripts that resolve runtime/config paths, relevant Docker defaults.

- [ ] 新增唯一环境解析入口 `scripts/prismos-env.sh`，接受 `PRISMOS_*` 新变量并兼容 `OPSINTECH_*`；覆盖运行时 home、配置路径和 Compose 所需的应用/数据库默认标识。
- [ ] 实现优先级：显式 `PRISMOS_*` 最高；未设置时使用 `OPSINTECH_*`；两者都没有时使用 PrismOS 默认值。
- [ ] 对已有 `backend/.opsintech` 做非破坏性 fallback：新目录不存在而旧目录存在时继续使用旧目录；不复制、不删除、不改写旧目录。
- [ ] 将 Compose 项目名、容器名、网络名、镜像名和新部署默认数据库标识切换为 `prismos`；保留旧 env 输入兼容映射，API 与 database schema 不变。
- [ ] 让部署、启动、清理、重建镜像和配置升级脚本通过同一入口取值，避免不同脚本产生不同默认值。
- [ ] 在配置示例中写清新变量、旧变量兼容说明、数据迁移注意事项和安全提示。

**Verification:** `bash -n` 检查相关脚本；用 `bash -c` 分别验证新变量优先、旧变量 fallback 和默认值；用 `docker compose config` 检查根目录及 `docker/docker-compose.yaml`。

## Task 2: Rename package metadata and safe product-facing strings

**Files:** `backend/pyproject.toml`, `frontend/package.json`, `backend/app/gateway/app.py`, targeted frontend components/locales and tests found by `rg`.

- [ ] 将 Python project/distribution name 改为 `prismos`，更新 description/readme metadata；保留 workspace 中 `deerflow-harness` 依赖和 source 名称。
- [ ] 将 frontend package name 改为 `prismos-frontend`；不修改依赖锁定版本，除非包管理器验证证明 lockfile 需要同步。
- [ ] 将 FastAPI title、description、健康检查 service identity 和公开 UI 文案改为 PrismOS；保留 API routes 与已有响应字段兼容性。
- [ ] 更新 landing/header/footer/about/auth/workspace/terminal 等用户可见文本、语言包和仓库链接；保留 localStorage/storage keys，避免已有浏览器设置失效。
- [ ] 第一方链接统一为 `https://github.com/yespon/prism-os`；用于上游归属的 DeerFlow 链接继续指向真实上游。
- [ ] 为保留的 `OPSINTECH_*`、`.opsintech`、`deerflow` 字符串建立可解释的兼容性/内核/历史数据/license allowlist。

**Verification:** `uv run --offline python` 读取 TOML 断言项目名；Node 读取 package.json 断言 frontend 名称；运行 `cd frontend && pnpm check && pnpm test:unit`。

## Task 3: Make the backend test baseline publishable

**Files:** `backend/tests/test_client_e2e.py`, `backend/packages/harness/deerflow/client.py` 或实现中确认的最窄兼容测试位置，以及直接相关测试。

- [ ] 修复已知 collection 阻断：`test_client_e2e.py` 从 `deerflow.client` 导入当前不存在的 `StreamEvent`。
- [ ] 以当前 `DeerFlowClient` 实际公开接口为准调整测试契约，或补充最小、向后兼容的事件类型/stream API；不得借机重命名 DeerFlow 内核。
- [ ] 保证不需要 LLM key 的文件管理测试可运行，需要真实 LLM 的测试在 CI 中明确 skip；不把 skip 伪装成 pass。
- [ ] 若 identity/config 改造触发其他 collection/import 问题，一并修复并增加回归断言。

**Verification:** 在 `backend` 执行 `uv run --offline pytest --collect-only -q` 和 `uv run --offline pytest -q`；collection 必须成功，结果清楚区分 passed/skipped/failed。

## Task 4: Rewrite public project documentation

**Files:** `README.md`, `README_zh.md`, `QUICKSTART.md`, `QUICKSTART_zh.md`, `CONTRIBUTING.md`, `SECURITY.md`, `.github/ISSUE_TEMPLATE/config.yml`, `docker/provisioner/README.md`, relevant `Makefile` help and service docs.

- [ ] 以 PrismOS 为标题和产品名重写中英文 README，包含定位、架构边界、当前能力、部分实现、未实现能力、快速启动、配置/安全、开发验证、版本/GHCR、贡献和安全入口。
- [ ] 建立能力基线表：已实现 multi-tenancy/RBAC/model config/Skill/MCP/sandbox/artifact/admin/vertical plugin；部分实现 Agent management/plugin SPI/runtime abstraction/unified audit；路线图 Policy/Task/Run/Workflow/Evaluation/Connector/runtime independence/Federation。
- [ ] 明确 AI 运维只是验证场景，不与系统内核耦合；不把 AI 运维闭环写成平台架构前提。
- [ ] 重写 Quickstart，使 clone、配置、Compose、健康检查、首个请求和 GHCR 镜像全部指向 `yespon/prism-os`/PrismOS，同时保留实际 API path 和命令。
- [ ] 重写 CONTRIBUTING，删除上游 fork 依赖和错误的 OpsinTech upstream 操作，说明独立私有仓库的分支、提交、本地检查和提交流程。
- [ ] 更新 SECURITY、issue template、provisioner 文档、Makefile 帮助和服务内说明；不承诺尚未实现的企业级安全能力。
- [ ] 保留 DeerFlow/LangGraph 的真实上游归属与 license attribution，不把上游代码包装成原创实现。

**Verification:** 对 public docs 执行 `rg` 检查旧第一方名称/URL；确认中英文 README 都明确 alpha 限制、当前基线和 roadmap。

## Task 5: Align Docker validation and add GHCR publishing

**Files:** `.github/workflows/docker-build.yml`, `.github/workflows/container-publish.yml` (new), Dockerfiles, Compose files and image-name references.

- [ ] 将现有 build-only workflow 的 image/tag/cache/artifact names 改为 `prismos-*`，保持 PR/main 的验证性质，不向 registry 推送。
- [ ] 新增 publish workflow：仅 release SemVer tag（首个 `v0.1.0-alpha.1`）或手动 dispatch 推送；默认分支只 build/validate，不产生 `latest`。
- [ ] 使用 `GITHUB_TOKEN` packages write 发布单一 `ghcr.io/yespon/prism-os` OCI image，支持 `linux/amd64` 和 `linux/arm64`。
- [ ] 写入版本、commit SHA、source revision 等 OCI labels，生成 Git tag、SemVer、SHA 和默认分支 `edge` 标签；禁止 `latest`。
- [ ] publish 前 gates 包含配置解析、backend test collection、frontend static check、Docker Compose config validation；任一失败不得推送。
- [ ] 验证 Dockerfile 的命令、健康检查、前端代理和 provisioner 路径没有因改名断裂；不替换 DeerFlow runtime 依赖。

**Verification:** `docker compose config`、`docker compose -f docker/docker-compose.yaml config`、workflow YAML parser/linter 和 `git diff --check`；若本机无 Buildx，至少完成静态验证并在 GitHub Actions 首次运行检查实际矩阵。

## Task 6: Prepare the first formal release artifact

**Files:** `docs/releases/v0.1.0-alpha.1.md` (new), and only an existing authoritative version source if one is found.

- [ ] 创建 release notes，准确描述 PrismOS 身份、当前能力、GHCR 安装、兼容变量、测试状态、反馈方式和配置迁移提示。
- [ ] 明确 alpha 限制：仍依赖 DeerFlow/LangGraph；Policy/Workflow/Task lifecycle/Evaluation/Federation 未作为完整平台能力交付；默认本地 filesystem sandbox 不是生产隔离承诺。
- [ ] 记录 `ghcr.io/yespon/prism-os:v0.1.0-alpha.1`、commit SHA、支持架构和安全注意事项；不写不可验证的性能/稳定性数字。
- [ ] 完成验证后创建 annotated tag `v0.1.0-alpha.1`；不删除或移动历史 tag。

**Verification:** `git tag -n`、`git show --stat --oneline v0.1.0-alpha.1`，并确认 tag 指向包含全部发布文件的提交。

## Task 7: Synchronize GitHub metadata, Release and Packages

**Scope:** private repository `https://github.com/yespon/prism-os`。

- [ ] About description 设置为：`PrismOS is a governed Agent operating system for enterprise teams, with multi-tenant control, RBAC, sandboxed execution, Skills, MCP, artifacts, and an extensible runtime foundation.`
- [ ] Homepage 设置为 `https://github.com/yespon/prism-os`；topics 为 `agentos`, `ai-agents`, `agent-platform`, `agent-governance`, `agent-runtime`, `mcp`, `langgraph`, `multi-tenant`, `sandboxed-execution`, `enterprise-ai`, `agentops`, `python`, `nextjs`, `docker`。
- [ ] 从 `v0.1.0-alpha.1` 创建 GitHub pre-release，正文使用本地 release notes，并附 GHCR 拉取方式；不标为 stable/latest。
- [ ] 确认 Packages 出现 GHCR OCI 包，包名/可见性符合私有仓库策略；若 Actions 未完成，记录真实外部阻塞，不伪造发布成功。
- [ ] 页面复核 private、非 fork、仓库名 `prism-os`、About/README/Release/Packages 无第一方 OpsinTech 叙述。

**Verification:** `git status --short --branch`、`git log -1 --oneline`、`git ls-remote --tags origin v0.1.0-alpha.1`，并补充 GitHub 页面和 workflow run 的实际证据。

## Task 8: Final consistency audit and handoff

- [ ] 对全仓库执行品牌、仓库 URL、旧 env、路径、镜像和包名审计；每个剩余旧标识都归入兼容性、上游归属、历史数据或 license attribution。
- [ ] 运行 backend collection/tests、frontend checks/tests、shell syntax、Compose config 和 `git diff --check`。
- [ ] 检查 `git status` 干净，列出最终提交、tag、GHCR image、GitHub Release 和已知限制。
- [ ] 若设计文档与代码事实冲突，先更新设计/计划/release notes，再继续；不通过 README 掩盖差异。

## Commit and integration sequence

按以下逻辑提交，便于审阅和回滚：

1. `docs: define PrismOS project publishing design`（已完成）
2. `docs: add PrismOS publishing implementation plan`（本计划）
3. `refactor: establish PrismOS identity and compatibility`（Task 1–2）
4. `test: restore backend collection baseline`（Task 3）
5. `docs: rewrite PrismOS project documentation`（Task 4）
6. `ci: publish PrismOS images to GHCR`（Task 5）
7. `release: prepare PrismOS v0.1.0-alpha.1`（Task 6）
8. GitHub metadata/release synchronization and final verification（Task 7–8）

实施时推荐使用 `superpowers:subagent-driven-development`：每个相互独立的任务先实现、再跑验收命令、再审阅 diff；涉及同一组配置/文档文件的任务必须串行，避免并行写入冲突。若选择 inline execution，则严格按上述顺序在当前任务中执行。
