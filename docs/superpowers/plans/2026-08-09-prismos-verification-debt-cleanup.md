# PrismOS Verification Debt Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理 PrismOS 品牌根迁移分支中的前后端验证债务，使 Task 11 的全部严格质量门退出码为 `0`，然后安全完成本地目录命名迁移并合并到 `main`。

**Architecture:** 按验证层拆分为基线、前端类型/build、前端 unit/lint、后端 pytest、后端 Ruff 和最终 Task 11。每个阶段只修改其根因范围，使用独立提交、focused verification 和任务级审查；不通过放宽质量配置、跳过测试或修改持久化协议制造绿色。

**Tech Stack:** Next.js 16；React 19；TypeScript 5；Vitest；ESLint；Python 3.12；FastAPI；SQLModel/SQLAlchemy；pytest；Ruff；Docker Compose；Git worktree。

## Global Constraints

- 所有 Task 11 命令必须退出码为 `0`：前端 `pnpm test:unit`、`pnpm typecheck`、`pnpm lint`、`pnpm build`；后端 `uv run pytest --collect-only -q`、`uv run pytest -q`、`uv run ruff check app packages/harness/deerflow tests scripts`。
- 不得使用 `any`、`@ts-ignore`、`@ts-expect-error`、关闭 TypeScript strict、缩小 lint/pytest/Ruff 检查范围或修改 CI 规则来制造绿色。
- 不得删除有业务意义的测试、降低断言强度、把失败测试改成 skip、静默吞异常或扩大宽泛 fixture 以掩盖真实错误。
- 不得修改、重建、复制或迁移 `backend/opsintech.db`。
- 数据库 schema、Alembic 历史、持久化 ID、API path、`deerflow` import 和 LangGraph 接口保持不变。
- AI 运维只保留为验证场景，不得耦合进 PrismOS 核心；不做与当前失败没有因果关系的架构重构、依赖升级或大规模格式化。
- PrismOS 兼容边界保持不变：旧 `OPSINTECH_*` 输入仅为 `0.2.x` 兼容桥，`.opsintech` 数据只读、显式迁移、可回滚，`0.3.0` 删除运行时旧品牌兼容输入。
- 每个实现任务必须先复现根因，再写或修正能证明根因的测试，之后实施最小修复并运行 focused verification。
- 目录改名和本地合并只能在所有严格门禁通过、工作树干净且目标目录不存在之后执行。

---

### Task 1: 建立验证债务基线与失败清单

**Files:**
- Create: `.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/progress.md`
- Create: `.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/baseline/README.md`
- Create: `.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/baseline/*.log`

**Produces:** 可复现的前后端命令输出、失败节点清单和根因假设；本任务不修改生产代码。

- [ ] **Step 1: 记录隔离 workspace 与 base SHA**

```bash
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short --branch
```

Expected: 当前目录是 `/Users/yespon/Documents/AgentOS/prism-platform/.worktrees/prismos-brand-root-migration`，分支为 `codex/prismos-brand-root-migration`，且没有未记录的 tracked code changes。

- [ ] **Step 2: 捕获前端基线**

从 `frontend` 运行以下命令；使用 `PIPESTATUS` 或 `pipefail` 保留真实退出码：

```bash
pnpm typecheck 2>&1 | tee ../.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/baseline/frontend-typecheck.log
pnpm test:unit 2>&1 | tee ../.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/baseline/frontend-unit.log
pnpm lint 2>&1 | tee ../.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/baseline/frontend-lint.log
pnpm build 2>&1 | tee ../.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/baseline/frontend-build.log
```

记录每个失败文件、行号、诊断和测试失败簇；已知 TypeScript 错误至少包括 `src/app/workspace/files/page.tsx:108`、`:418`、`src/app/workspace/skills/[name]/page.tsx:73` 以及 `src/core/i18n/locales/en-US.ts` 的 extra-property diagnostics。

- [ ] **Step 3: 捕获后端基线**

从 `backend` 运行：

```bash
uv run pytest --collect-only -q 2>&1 | tee ../.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/baseline/backend-collection.log
uv run pytest -q 2>&1 | tee ../.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/baseline/backend-pytest.log
uv run ruff check app packages/harness/deerflow tests scripts 2>&1 | tee ../.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/baseline/backend-ruff.log
```

记录 collection、passed/failed/skipped、每个 failed node 和 Ruff 规则/文件统计；完整 traceback 读取完毕后再按 tenant/auth、client/e2e client、model factory、task tool、schema/fixture 等域分类。

- [ ] **Step 4: 写入 README 与 ledger 并提交**

`baseline/README.md` 必须包含 base SHA、确切命令、退出码、版本、摘要和 `domain / failing nodes / root-cause hypothesis / owner task / verification command` 表格。`progress.md` 第一行必须是：

```markdown
# SDD ledger — plan: docs/superpowers/plans/2026-08-09-prismos-verification-debt-cleanup.md
```

然后追加 `Task 1: complete` 和 artifact 路径。提交：

```bash
git add .superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup
git commit -m "chore: record verification debt baseline"
```

---

### Task 2: 修复前端 TypeScript 类型契约与 production build

**Files:**
- Modify: `frontend/src/app/workspace/files/page.tsx`
- Modify: `frontend/src/app/workspace/skills/[name]/page.tsx`
- Modify: `frontend/src/core/i18n/locales/types.ts`
- Modify: `frontend/src/core/i18n/locales/en-US.ts` 及其余受类型契约影响的 locale 文件
- Test: 对应文件导航、skill、workspace/i18n 的现有测试；缺失时新增最小 focused test

**Produces:** `pnpm typecheck` 与 `pnpm build` 均退出 `0`。

- [ ] **Step 1: 逐项复现并追踪根因**

```bash
cd frontend
pnpm typecheck
```

检查 `folderStack.slice(0, -1)` 的空数组边界、`uploadingFiles` 的真实翻译 owner、skill 执行模式与 API 契约、以及 shared `Translations` shape 与 locale object 的差异。不得先加断言或放宽配置。

- [ ] **Step 2: 先写最小回归测试并确认 RED**

文件导航测试必须覆盖单元素 stack 向上导航回 root；翻译测试必须以真实 consumer key 做类型验证；skill 测试必须验证实际支持的 `cmd | agent` 合约。测试失败原因必须是当前契约错误，而不是测试拼写或 provider 缺失。

- [ ] **Step 3: 实施最小类型正确修复**

对空 stack 使用显式 root guard；只有真实消费的 key 才加入共享类型，并同步满足 locale 合约；skill 使用实际支持的 mode，只有已有 backend/API 支持时才扩展共享 mode 类型。禁止 `any`、非空断言掩盖可达状态、`@ts-ignore` 和把类型扩大为 `string`。

- [ ] **Step 4: 验证 focused tests、typecheck 和 build**

```bash
pnpm test:unit
pnpm typecheck
pnpm build
```

Expected: 三个命令均退出 `0`。若出现新诊断，记录到 ledger 并回到根因调查，不顺手混入 lint 重构。

- [ ] **Step 5: 提交**

```bash
git commit -m "fix: restore frontend type and build gates"
```

在提交前先运行 `git status --short`，逐项使用 `git add path/to/reviewed-file` staging 本任务审查过的文件；不得使用目录级 staging。

---

### Task 3: 修复前端 unit test provider、fixture 与 mock 契约

**Files:**
- Modify: Task 1 `frontend-unit.log` 中的失败测试文件
- Modify: 现有 Vitest setup/test utility（若存在）
- Modify: 受影响 production component（仅当失败证明 production contract 有误）
- Test: 每个 provider/fixture/mock failure cluster

**Produces:** `pnpm test:unit` 退出 `0`，不删除测试、不降低断言。

- [ ] **Step 1: 按失败簇复现**

```bash
cd frontend
pnpm vitest run path/to/the-failing-test-file.test.ts
```

逐项确认是 `I18nProvider`、`QueryClientProvider`、router、browser API 还是不完整 module mock，并将契约记入 ledger。

- [ ] **Step 2: 写 failing provider/fixture regression**

使用真实 `I18nProvider` 渲染 i18n consumer，使用真实 query provider 渲染 React Query consumer；model connection mock 必须包含完整导出形状（包括 `useTestModelConnection`）并断言真实渲染行为。

- [ ] **Step 3: 修复最窄边界**

优先建立一个共享 provider helper，避免每个测试重复 partial mock。必要 mock 必须镜像 production exports。禁止 mock 被测组件、改成 snapshot-only 或用全局 fallback 隐藏 provider 缺失。

- [ ] **Step 4: 验证并提交**

```bash
pnpm test:unit
```

先运行 `pnpm vitest run` 并把实际修复的测试文件路径写入命令；再用 `git status --short` 确认范围，逐项 staging 后提交：`test: restore frontend provider and fixture contracts`。

---

### Task 4: 清理前端 ESLint 债务并锁定前端绿门

**Files:**
- Modify: Task 1 `baseline/frontend-lint.log` 中列出的源文件和测试文件
- Modify: `frontend/eslint.config.js` 仅在证明规则配置错误时
- Test: affected tests plus all frontend gates

**Produces:** `pnpm test:unit`、`pnpm typecheck`、`pnpm lint`、`pnpm build` 全部退出 `0`。

- [ ] **Step 1: 按 rule/module 建立 lint inventory**

```bash
cd frontend
pnpm lint
```

先区分 mechanical fixes 和 behavior-sensitive fixes；禁止先对全树运行未经审查的 `lint:fix`。

- [ ] **Step 2: 对行为敏感修复先写 regression**

涉及 hook dependency、control flow、accessibility 或 rendered output 的修复必须先有 focused test；纯 import ordering/unused-local 使用现有测试作为保护。

- [ ] **Step 3: 分模块实施最小修复**

修复 imports、unused values、hooks、a11y 和 unsafe patterns；保留 API/行为。禁止 blanket disable、删除断言或修改检查范围。

- [ ] **Step 4: 验证与提交**

```bash
pnpm test:unit
pnpm typecheck
pnpm lint
pnpm build
```

使用 `git status --short` 确认范围后，逐项 staging 本任务审查过的 frontend 文件，再提交：`chore: clear frontend verification debt`。

---

### Task 5: 修复后端测试环境与基础设施失败簇

**Files:**
- Modify: Task 1 backend inventory 中 tenant/auth、client/e2e client、database session/schema/fixture、storage 边界的 exact files
- Test: 对应 failing nodes 和相邻模块测试
- Never modify: `backend/opsintech.db`、Alembic history、public API paths

**Produces:** assigned infrastructure/test-environment clusters pass without reducing scope.

- [ ] **Step 1: 用完整 traceback 复现第一个失败簇**

```bash
cd backend
uv run pytest tests/test_authorization_tenant_context.py::<node> -vv --tb=long
```

从 fixture setup、dependency injection、environment、database lifecycle 和 request/client boundary 向上追踪到第一个错误值，并将单一 root-cause hypothesis 写入 ledger。

- [ ] **Step 2: 在最小边界写 failing regression**

tenant/auth 测试必须断言 tenant context 和 authorization dependency 接收同一 tenant identity；client/e2e client 测试必须断言 auth 与 async lifecycle；database fixture 测试必须使用临时数据库或既有 test fixture 验证 isolation/schema initialization，绝不使用 tracked `backend/opsintech.db`。

- [ ] **Step 3: 实施根因修复**

只修复 fixture、dependency wiring、client lifecycle、schema setup 或 test-only configuration 的 owner。禁止 broad exception swallowing、global state、生产数据和 public persistence contract 变更。

- [ ] **Step 4: 运行 focused、adjacent 和 domain tests**

```bash
uv run pytest -q
```

先用实际 failed node 路径运行 focused pytest，再运行相邻测试文件；命令中的路径必须来自 Task 1 ledger，不能使用未解析的示例路径。

每个 coherent domain batch 后记录相对 Task 1 的失败 delta。

- [ ] **Step 5: 提交**

```bash
git commit -m "test: restore backend test infrastructure contracts"
```

使用 `git status --short` 确认范围后，逐项 staging 本任务审查过的 backend 文件。

---

### Task 6: 修复后端模型、任务工具与业务失败簇

**Files:**
- Modify: Task 1 inventory 中 model factory/config、task tool、router/service、middleware 和其他 proven domains 的 exact files
- Test: 每个 assigned failing node 及邻近测试
- Never modify: `backend/opsintech.db`、schema history、public route paths、persisted IDs、LangGraph/deerflow interfaces

**Produces:** all remaining backend behavior failures pass with regression coverage.

- [ ] **Step 1: 复现并分类一个 domain cluster**

运行 exact nodes 的 long traceback，与同模块 passing implementation 比较，定位第一个错误 input/output，并把单一 hypothesis 写入 ledger。

- [ ] **Step 2: 写 failing behavioral regression**

model factory 必须断言 supported provider 的 model/config/capability contract；task tool 必须覆盖 valid input、invalid input 和 error boundary；router/service 必须断言 public response 与 tenant scope。测试真实 production code，不只断言 mock 调用次数。

- [ ] **Step 3: 实施一个最小修复**

修复错误 contract 的 owner，保持 public signatures 和 serialized values 稳定。若同一架构连续三次修复仍失败，停止并记录 load-bearing issue，不再尝试第四个补丁。

- [ ] **Step 4: 运行 focused 与全量 backend tests**

```bash
uv run pytest -q
```

先用 Task 1 ledger 中的实际 repaired node 运行 focused pytest，再运行全量测试。

Expected: full suite failure count is `0`; collection remains successful; skips remain explicit and justified。

- [ ] **Step 5: 提交**

```bash
git commit -m "fix: restore backend behavior verification"
```

使用 `git status --short` 确认范围后，逐项 staging 本任务审查过的 backend 文件。

---

### Task 7: 清理后端 Ruff 债务并保持测试全绿

**Files:**
- Modify: current Ruff output named backend files
- Modify: Ruff config only for a proven incorrect existing rule; no broad ignores
- Test: affected pytest and full pytest/Ruff gates

**Produces:** full backend pytest and Ruff both exit `0`。

- [ ] **Step 1: 生成 fresh Ruff inventory**

```bash
cd backend
uv run ruff check app packages/harness/deerflow tests scripts
```

按 module/rule 分组；先处理 undefined names、import errors 和 behavior-sensitive diagnostics，再处理机械 import ordering/type modernization。

- [ ] **Step 2: 为行为敏感修复保留 regression**

任何改变 branch、import source、exception path 或 type conversion 的 Ruff 修复，编辑前必须有 focused pytest；纯格式/import ordering 可依赖现有 domain tests。

- [ ] **Step 3: 分批实施 Ruff 修复**

一次只改一个 module/rule batch，保持 runtime behavior 与 public interfaces。禁止扩大 ignore、修改 selected rule set 或用 `# noqa` 藏住真实问题；只有明确、窄范围且已记录的 false positive 才可使用局部 `# noqa`。

- [ ] **Step 4: 验证 backend gates**

```bash
uv run pytest --collect-only -q
uv run pytest -q
uv run ruff check app packages/harness/deerflow tests scripts
```

三个命令都必须退出 `0`，记录精确 summary。

- [ ] **Step 5: 提交**

```bash
git commit -m "chore: clear backend verification debt"
```

使用 `git status --short` 确认范围后，逐项 staging 本任务审查过的 backend 文件。

---

### Task 8: 重新执行 PrismOS Task 11 全量门禁

**Files:**
- Modify: `.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/progress.md`
- Create: `.superpowers/sdd/2026-08-09-prismos-verification-debt-cleanup/final-verification/` logs
- No production-code edits are allowed

**Produces:** strict all-green verification record；any failure returns to its owning repair task。

- [ ] **Step 1: Run final brand/deployment gates**

```bash
uv run --offline python scripts/check_brand_identity.py
git grep -In -e 'OpsinTech' -e 'opsintech' -e 'OPSINTECH' -- ':!docs/superpowers/**' ':!docs/releases/**' ':!docs/migrations/**'
bash scripts/test-prismos-env.sh
bash scripts/test-prismos-product-identity.sh
bash -n scripts/*.sh
docker compose config --quiet
docker compose -f docker/docker-compose.yaml config --quiet
docker compose -f docker/docker-compose-dev.yaml config --quiet
git diff --check
```

Expected: scanner/allowlist and deployment checks pass；remaining old-name matches are documented compatibility/migration/historical matches only。

- [ ] **Step 2: Run final backend gates and save output**

```bash
cd backend
uv run pytest --collect-only -q
uv run pytest -q
uv run ruff check app packages/harness/deerflow tests scripts
```

保存 stdout、exit code、counts 和 Ruff summary 到 `final-verification/`。

- [ ] **Step 3: Run final frontend gates and save output**

```bash
cd frontend
pnpm test:unit
pnpm typecheck
pnpm lint
pnpm build
```

四个命令均必须为 `0`；不能用旧的非绿色 baseline 作为例外。

- [ ] **Step 4: Verify protected boundaries and repository state**

```bash
cd ..
git diff -- backend/opsintech.db
git grep -In '/Users/yespon/Documents/AgentOS/prism-platform\|/prism-platform/' -- . || true
git status --short --branch
git log --oneline --decorate -12
```

逐项审查 path matches。active code、current docs、IDE settings 或 automation 中的旧绝对路径会阻塞改名；`.superpowers/` 仅作为本地 audit evidence，不能进入产品 commit。

- [ ] **Step 5: Record strict completion**

仅在全部命令成功后追加：

```text
Task 8: complete (all strict Task 11 commands exit 0; evidence under final-verification/)
```

---

### Task 9: 完成本地目录命名迁移并合并到 main

**Files:**
- Operational move: `/Users/yespon/Documents/AgentOS/prism-platform` → `/Users/yespon/Documents/AgentOS/prism-os`
- No Git content change solely for filesystem move

**Produces:** local repository at `/Users/yespon/Documents/AgentOS/prism-os`, migration branch merged into local `main`。

- [ ] **Step 1: Confirm preconditions from parent directory**

确认目标目录不存在、迁移分支没有 tracked modifications、remote 指向 `https://github.com/yespon/prism-os.git`。任一条件失败都停止，不删除、不覆盖、不合并。

- [ ] **Step 2: Move local directory**

停止 repository 内部路径上的 dev servers/terminals，然后从 `/Users/yespon/Documents/AgentOS` 执行：

```bash
test ! -e /Users/yespon/Documents/AgentOS/prism-os
mv /Users/yespon/Documents/AgentOS/prism-platform /Users/yespon/Documents/AgentOS/prism-os
```

- [ ] **Step 3: Verify Git identity from new path**

在新路径检查 `git status --short --branch`、`git remote -v`、`git log -5 --oneline` 和 `git worktree list`；branch、HEAD、remote、history 必须保持不变。

- [ ] **Step 4: Fast-forward merge into local main**

```bash
git switch main
git merge --ff-only codex/prismos-brand-root-migration
```

若无法 fast-forward，停止并报告，不创建未经审查的 merge commit。

- [ ] **Step 5: Record final handoff**

在 verification ledger 中记录 final path、branch、HEAD、merge result、strict summaries、protected-boundary check 和所有 repair commits；不要额外修改产品代码。

---

## Execution order and review gates

Tasks strictly serial: `1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9`。每个 implementation task 使用 fresh implementer、task reviewer、必要时 scoped re-review；Task 7 后进行 whole-branch review。Task 8 是 no-code verification gate，Task 9 是最终 filesystem/Git 操作，任何 review finding 或 command failure 未关闭时不得开始。
