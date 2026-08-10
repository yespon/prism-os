# PrismOS 分支合并与主线整合实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不把旧分支基线差异和过时的 `OPSINTECH_*` 配置重新带回主线的前提下，将战略资料和 setup/runtime 修复安全整合到本地 `main`，完成可审计、可回滚、经过验证的 PrismOS 主线合并。

**Architecture:** 先把纯文档分支以一次独立的 `--no-ff` 合并纳入主线，再从更新后的 `main` 创建临时集成分支，仅 cherry-pick setup 修复提交 `0e447b0`。Docker Compose 冲突以当前 `main` 的 PrismOS 运行时架构为权威，只补入 setup 修复所需的公开 API build args、动态端口 CORS 和前端 public-origin fallback；旧 `OPSINTECH_*` 变量只有在当前代码仍存在实际消费者时才作为显式兼容层保留。

**Tech Stack:** Git、Docker Compose、Next.js 16、pnpm、TypeScript、Python/pytest、uv、Ruff、PrismOS gateway/LangGraph runtime。

## Global Constraints

- 当前工作区 `/Users/yespon/Documents/AgentOS/prism-os` 的未提交用户数据必须保持不变；执行前必须确认工作树只有已知的 `.superpowers/` 与 `backend/.prismos/` 忽略目录。
- 当前本地 `main` 的 PrismOS 品牌迁移、运行时适配和验证债务修复历史不可被旧分支覆盖。
- 不将 `fix/prismos-runtime-safe` 从 `origin/main` 的旧基线直接 merge 到本地 `main`；该分支只贡献提交 `0e447b0` 的六个文件变更。
- 不使用 `git reset --hard`、`git checkout --` 或强制推送；所有回滚使用未合并分支、备份引用或 `git merge --abort`。
- `OPSINTECH_*` 不得因冲突解决而无条件复活；它们只能在验证存在运行时消费者后，以兼容层形式保留，并必须记录移除条件。
- 主线推送不是本计划的默认动作；只有本地合并、验证和差异审阅完成，并得到用户明确授权后才能执行 `git push origin main`。
- 已知前端基线债务（I18nProvider/QueryClient、旧 locale key、`frontend/src/app/workspace/files/page.tsx:108` 等）必须与本次合并引入的问题分开记录，不得把基线失败误报为合并回归。

## 当前分支事实与合并策略

共同基线为 `a58d461 ci: unblock PrismOS alpha publishing`。

- 本地 `main`：`6b452de fix: make PrismOS deployment runtime-safe`，相对 `origin/main` 包含 21 个 PrismOS 品牌、运行时、验证债务和 Docker/setup 历史提交。
- `docs/organize-agentos-materials`：`e8e9dcb docs: archive AgentOS strategy materials`，只新增 `docs/strategy/` 资料并调整忽略规则；已通过 `git merge-tree --write-tree main docs/organize-agentos-materials` 预演，无真实内容冲突。
- `fix/prismos-runtime-safe`：`0e447b0 fix: keep frontend API requests on public origin`，从旧 `origin/main` 派生；直接 merge 会把旧基线差异带入主线，且 `docker/docker-compose.yaml` 与当前主线存在真实冲突。
- setup 分支与主线的 Docker 冲突集中在 gateway/LangGraph 环境变量段：主线使用 `PRISMOS_*` 和 `PRISMOS_RUNTIME_ADAPTER_MODULE`，setup 分支包含旧 `OPSINTECH_*` 兼容变量。

推荐顺序：

```text
docs/organize-agentos-materials --(no-ff)--> main
                                      |
                                      +--> codex/prismos-runtime-safe-integration
                                             --(cherry-pick 0e447b0)--> main
```

这样可以分别审查文档归档和 runtime/setup 修复，也可以在任一阶段失败时只回退该阶段。

## 文件与职责映射

### Task 1: 合并前基线与安全检查

**Files:**
- Read: `.gitignore`
- Read: `docs/strategy/README.md`
- Read: `docker/docker-compose.yaml`
- Read: `frontend/Dockerfile`
- Read: `frontend/src/core/config/index.ts`
- Read: `backend/tests/test_frontend_docker_config.py`

**Interfaces:**
- Consumes: 当前 `main`、`docs/organize-agentos-materials`、`fix/prismos-runtime-safe` 三个本地 ref 及对应远端 ref。
- Produces: 可复现的基线记录、已确认的干净工作树和集成前验证结果；后续任务不得在未满足该门槛时执行写操作。

- [ ] **Step 1: 确认工作树和当前 ref**

```bash
cd /Users/yespon/Documents/AgentOS/prism-os
git status --short --branch
git branch --show-current
git log --oneline --decorate --graph --all -30
```

Expected: 当前分支为 `docs/organize-agentos-materials`，工作树无未提交 tracked changes；只允许看到已知忽略目录 `.superpowers/`、`backend/.prismos/`。

- [ ] **Step 2: 确认远端分支未发生漂移**

```bash
git fetch origin --prune
git rev-parse main docs/organize-agentos-materials fix/prismos-runtime-safe
git rev-parse origin/main origin/docs/organize-agentos-materials origin/fix/prismos-runtime-safe
```

Expected: 已推送的文档分支和 setup 修复分支仍分别指向 `e8e9dcb`、`0e447b0`；如果远端发生漂移，暂停并重新做 `merge-tree` 审计，不直接套用本计划。

- [ ] **Step 3: 记录主线验证基线**

```bash
cd frontend
pnpm typecheck
pnpm build
pnpm test:unit -- --run
cd ../backend
PYTHONPATH=. uv run pytest tests/test_frontend_docker_config.py -q
cd ..
docker compose -f docker/docker-compose.yaml -p prismos config --quiet
```

Expected: 记录每条命令的退出码和已知基线失败；特别标出 frontend 全量 typecheck/unit 的既有债务。Docker Compose 配置检查应通过；若 Docker daemon 不可用，至少完成静态 YAML 解析并把 daemon 缺失列为环境限制。

## Task 2: 将战略资料独立合并到本地 `main`

**Files:**
- Merge: `.gitignore`
- Merge: `docs/strategy/README.md`
- Merge: `docs/strategy/agentos-whitepaper.md`
- Merge: `docs/strategy/agentos-whitepaper-original.md`
- Merge: `docs/strategy/agentos-prismos-gap-roadmap-review.md`
- Merge: `docs/strategy/governed-agent-platform-roadmap.md`

**Interfaces:**
- Consumes: Task 1 的干净工作树和 `git merge-tree` 无冲突结论。
- Produces: `main` 上一个独立的文档合并提交；后续 setup 集成可以从该提交建立。

- [ ] **Step 1: 在不改变工作内容的前提下切换到 `main`**

```bash
git switch main
git status --short --branch
```

Expected: `main` 工作树干净，且 HEAD 为 `6b452de` 或 Task 1 记录的最新本地主线提交。

- [ ] **Step 2: 再次执行文档合并预演**

```bash
git merge-tree --write-tree main docs/organize-agentos-materials
```

Expected: exit code `0`，没有 `CONFLICT`；`.gitignore` 的 PrismOS runtime 忽略项和文档分支的 `.superpowers/`、`backend/.prismos/` 忽略项均可共同存在。

- [ ] **Step 3: 执行独立的非快进合并**

```bash
git merge --no-ff docs/organize-agentos-materials \
  -m "docs: archive AgentOS strategy materials"
```

Expected: 生成一个新的 merge commit；不得 squash 或 rebase，使文档来源和主线整合点可审计。

- [ ] **Step 4: 检查文档归档内容和合并边界**

```bash
git diff --check HEAD^1 HEAD
git diff --name-status HEAD^1 HEAD
git status --short --branch
test -f docs/strategy/README.md
test -f docs/strategy/agentos-whitepaper.md
test -f docs/strategy/agentos-whitepaper-original.md
test -f docs/strategy/agentos-prismos-gap-roadmap-review.md
test -f docs/strategy/governed-agent-platform-roadmap.md
```

Expected: 只有策略资料和忽略规则变化；没有源码、Docker、依赖或运行时配置变化。

## Task 3: 在更新后的主线重放 setup/runtime 修复

**Files:**
- Create branch: `codex/prismos-runtime-safe-integration`
- Cherry-pick source: `0e447b0`
- Resolve: `docker/docker-compose.yaml`
- Preserve from source commit: `.dockerignore`
- Preserve from source commit: `frontend/Dockerfile`
- Preserve from source commit: `frontend/.env.example`
- Preserve from source commit: `frontend/src/core/config/index.ts`
- Preserve from source commit: `backend/tests/test_frontend_docker_config.py`

**Interfaces:**
- Consumes: Task 2 合并后的 `main` 和 `0e447b0` 的六文件最小修复提交。
- Produces: `codex/prismos-runtime-safe-integration` 上一个只包含 setup/runtime 修复的集成提交；其 Docker Compose 使用当前 PrismOS canonical 变量。

- [ ] **Step 1: 从已更新的 `main` 创建临时集成分支**

```bash
git switch main
git switch -c codex/prismos-runtime-safe-integration
git status --short --branch
```

Expected: 新分支直接基于 Task 2 的 `main` merge commit，工作树干净。

- [ ] **Step 2: 只 cherry-pick setup 修复提交**

```bash
git cherry-pick 0e447b0
```

Expected: 可能在 `docker/docker-compose.yaml` 停止于冲突；不得 cherry-pick `6b452de` 或其 21 个历史祖先，也不得使用整个旧分支 merge。

- [ ] **Step 3: 解决 Docker Compose 冲突前检查旧变量消费者**

```bash
rg -n "OPSINTECH_|opsintech" \
  backend frontend docker scripts config.example.yaml \
  --glob '!**/*.lock' --glob '!**/node_modules/**' || true
```

Expected: 以当前工作树中实际代码消费者为准。如果只剩历史文档或迁移记录，禁止把旧变量重新写入 Compose；如果存在运行时读取点，记录具体文件和变量，并只保留满足该读取点所需的最小兼容映射。

- [ ] **Step 4: 以当前 `main` 为基础手动合并 `docker/docker-compose.yaml`**

保留当前 `main` 的以下内容：

```yaml
PRISMOS_HOST_BASE_DIR=${PRISMOS_HOME:-../backend/.prismos}
PRISMOS_HOST_SKILLS_PATH=${PRISMOS_REPO_ROOT:-..}/skills
PRISMOS_SANDBOX_HOST=host.docker.internal
PRISMOS_RUNTIME_ADAPTER_MODULE=${PRISMOS_RUNTIME_ADAPTER_MODULE:-app.runtime_adapters}
```

从 `0e447b0` 补入以下内容：

```yaml
NEXT_PUBLIC_BACKEND_BASE_URL: ${NEXT_PUBLIC_BACKEND_BASE_URL:-}
NEXT_PUBLIC_LANGGRAPH_BASE_URL: ${NEXT_PUBLIC_LANGGRAPH_BASE_URL:-}
CORS_ORIGINS=http://localhost:${PORT:-2026},http://frontend:3000
```

同时保留主线已有的 `PRISMOS_CONFIG_PATH`、`PRISMOS_HOME`、`PRISMOS_DOCKER_SOCKET` 默认值。没有实际消费者时删除冲突块中的 `OPSINTECH_HOME`、`OPSINTECH_CONFIG_PATH`、`OPSINTECH_HOST_BASE_DIR`、`OPSINTECH_HOST_SKILLS_PATH`、`OPSINTECH_SANDBOX_HOST`；如 Task 3 Step 3 证明存在消费者，则只在对应 service 添加带注释的兼容 alias，并在提交说明中写明移除条件。

- [ ] **Step 5: 完成 cherry-pick 并检查提交范围**

```bash
git add .dockerignore docker/docker-compose.yaml frontend/.env.example \
  frontend/Dockerfile frontend/src/core/config/index.ts \
  backend/tests/test_frontend_docker_config.py
git cherry-pick --continue
git show --stat --oneline HEAD
git diff --stat main..HEAD
```

Expected: 集成分支相对更新后的 `main` 只包含 setup 修复的六个文件，且 `docker/docker-compose.yaml` 没有把旧主线历史批量带入。

- [ ] **Step 6: 失败时使用可恢复回滚**

```bash
git cherry-pick --abort
git switch main
git branch -D codex/prismos-runtime-safe-integration
```

仅在 cherry-pick 无法按本计划解决或验证证明方案不安全时执行；执行前记录失败输出，不能删除 `main` 或任一已推送分支。

## Task 4: 验证集成分支并审阅回归边界

**Files:**
- Verify: `docker/docker-compose.yaml`
- Verify: `.dockerignore`
- Verify: `frontend/Dockerfile`
- Verify: `frontend/.env.example`
- Verify: `frontend/src/core/config/index.ts`
- Verify: `backend/tests/test_frontend_docker_config.py`

**Interfaces:**
- Consumes: Task 3 的集成分支。
- Produces: 可供合并回 `main` 的验证证据；任何失败都必须归类为本次回归、既有基线债务或环境限制。

- [ ] **Step 1: 做静态差异和 YAML 配置检查**

```bash
git diff --check main...HEAD
git diff --name-status main...HEAD
docker compose -f docker/docker-compose.yaml -p prismos config --quiet
```

Expected: 无 whitespace 错误；变更文件仅限六个修复文件；Compose 配置解析成功，不出现未定义变量导致的语法错误。

- [ ] **Step 2: 运行 setup/Docker 回归测试**

```bash
cd backend
PYTHONPATH=. uv run pytest tests/test_frontend_docker_config.py -q
cd ..
```

Expected: 两个配置断言通过，尤其确认生产前端 Dockerfile 接收公开 API URL build args，且 `.dockerignore` 排除本地 frontend `.env`。

- [ ] **Step 3: 运行前端直接相关检查**

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
pnpm test:unit -- --run
cd ..
```

Expected: 记录四条命令的退出码。若失败，必须与 Task 1 的 `main` 基线逐条比较；只有新增于 `0e447b0` 或冲突解决的错误才阻断合并。`frontend/src/core/config/index.ts` 的 public-origin fallback 必须通过 TypeScript 编译或有明确的基线/环境解释。

- [ ] **Step 4: 做最小 Compose smoke test（Docker daemon 可用时）**

```bash
docker compose -f docker/docker-compose.yaml -p prismos-merge-smoke up -d --build
curl --fail --silent --show-error http://localhost:${PORT:-2026}/setup >/dev/null
curl --fail --silent --show-error http://localhost:${PORT:-2026}/api/auth/bootstrap-status >/dev/null
docker compose -f docker/docker-compose.yaml -p prismos-merge-smoke ps
docker compose -f docker/docker-compose.yaml -p prismos-merge-smoke down
```

Expected: `/setup` 返回 HTTP 200，bootstrap status endpoint 返回 HTTP 200，核心服务进入 healthy；无论通过或失败都执行最后的 `down`，避免留下测试容器。若当前环境无 Docker daemon、镜像拉取或外部依赖不可用，保留 `config --quiet` 和静态/单元测试证据，并把 smoke test 标记为环境限制。

- [ ] **Step 5: 检查运行时变量和品牌边界**

```bash
rg -n "OPSINTECH_|opsintech" docker/docker-compose.yaml frontend/Dockerfile \
  frontend/src/core/config/index.ts backend/tests/test_frontend_docker_config.py || true
rg -n "PRISMOS_RUNTIME_ADAPTER_MODULE|NEXT_PUBLIC_BACKEND_BASE_URL|NEXT_PUBLIC_LANGGRAPH_BASE_URL|CORS_ORIGINS" \
  docker/docker-compose.yaml frontend/Dockerfile frontend/src/core/config/index.ts
```

Expected: canonical runtime 路径只使用 `PRISMOS_*`；旧变量若存在，必须与 Task 3 的实际消费者记录一致；公开 API build args、public-origin fallback、动态 `PORT` CORS 和 runtime adapter 配置都存在。

## Task 5: 合并集成分支回本地 `main` 并形成审计记录

**Files:**
- Merge: `codex/prismos-runtime-safe-integration` into `main`
- Record: Git merge commit and verification outputs in task notes/PR description

**Interfaces:**
- Consumes: Task 4 全部必需验证通过或已获得明确的基线/环境限制分类。
- Produces: 本地 `main` 同时包含战略资料和 runtime/setup 修复，且保留两个独立的可审计合并边界。

- [ ] **Step 1: 在集成分支完成后切换回 `main`**

```bash
git switch main
git status --short --branch
git log --oneline --decorate -5
```

Expected: `main` 工作树干净，HEAD 仍是 Task 2 的文档 merge commit；集成分支包含 Task 3 修复提交。

- [ ] **Step 2: 合并集成分支并保留显式 merge 节点**

```bash
git merge --no-ff codex/prismos-runtime-safe-integration \
  -m "fix: integrate PrismOS runtime-safe setup fix"
```

Expected: 生成第二个独立 merge commit；不 squash、不 rebase、不覆盖文档 merge commit。

- [ ] **Step 3: 复核主线最终差异**

```bash
git diff --check origin/main..main
git log --oneline --decorate origin/main..main
git diff --stat origin/main..main
git status --short --branch
```

Expected: 主线包含预期的 PrismOS 历史、文档归档和 setup 修复；不应出现来自 `fix/prismos-runtime-safe` 的旧基线删除/恢复大批量变更。工作树干净。

- [ ] **Step 4: 删除临时集成分支（仅在所有验证通过后）**

```bash
git branch -d codex/prismos-runtime-safe-integration
```

Expected: 因为分支已被 merge，Git 安全删除；远端已推送的 `docs/organize-agentos-materials` 和 `fix/prismos-runtime-safe` 不删除，保留为审计和回滚来源。

## Task 6: 推送门槛与回滚方案

**Files:**
- Remote ref: `origin/main`
- Optional release/PR metadata: only if separately requested

**Interfaces:**
- Consumes: Task 5 的干净本地 `main` 和完整验证记录。
- Produces: 用户批准后更新的远端 `main`；未批准时保持本地合并结果，不产生远端主线变化。

- [ ] **Step 1: 推送前检查分支状态**

```bash
git status --short --branch
git log --oneline --decorate origin/main..main
git diff --check origin/main..main
```

Expected: 只显示待推送的本地提交，没有未提交文件；提交历史和验证结果已在交付说明中列明。

- [ ] **Step 2: 获得用户明确授权后推送主线**

```bash
git push origin main
```

Expected: `origin/main` 快进到本地 `main` 的 merge commit；不得使用 `--force`。

- [ ] **Step 3: 如果推送前发现方案问题，回滚本地合并**

优先保留现状并创建备份引用，然后使用可逆的 revert；不要 reset 已推送的主线。若问题只发生在未推送的本地合并阶段，可删除临时集成分支并重新从 `origin/main` 建立干净集成分支。若已经推送，则为对应 merge commit 创建单独的 revert PR，并重新运行 Task 4 全套验证。

## 自审清单

- [x] 已覆盖文档分支：预演无冲突，独立 `--no-ff` 合并。
- [x] 已覆盖 setup 分支：只 cherry-pick `0e447b0`，避免旧基线整体 merge。
- [x] 已明确 Docker Compose 冲突的 canonical 变量、待保留修复和旧变量处理规则。
- [x] 已包含 Docker Compose、后端配置测试、前端 lint/typecheck/build/unit 和 `/setup` smoke test。
- [x] 已区分已知基线债务与本次合并回归。
- [x] 已定义本地回滚、临时分支删除和远端推送门槛。
- [x] 计划中没有 `TBD`、`TODO` 或“自行补充测试”等不可执行占位语句。

