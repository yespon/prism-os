# PrismOS 验证债务清理设计

**日期：** 2026-08-09  
**适用分支：** `codex/prismos-brand-root-migration`  
**目标分支：** `main`

## 1. 背景与目标

PrismOS 品牌根迁移已经完成品牌、运行时兼容、部署边界、文档和发布门禁建设，但原项目在全量验证上仍存在历史债务。当前阻塞集中在：

- 前端 TypeScript 类型检查和 production build；
- 前端 unit test fixture/provider、mock 与 lint；
- 后端 pytest 失败簇；
- 后端 Ruff 全仓规则债务。

本任务的目标是把这些验证债务拆成可追踪、可回滚、可独立审查的阶段，并恢复 Task 11 的严格绿门。只有 Task 11 所要求的全部命令退出码为 `0`，才执行本地目录改名为 `prism-os`，随后将迁移分支合并到 `main`。

本任务不改变 PrismOS 的产品路线，不引入 AI 运维核心耦合，也不借修复验证债务之机做无关架构重构。

## 2. 完成定义

验证债务清理只有在以下条件全部满足时才算完成：

1. 后端测试可收集并全量通过：

   ```bash
   cd backend
   uv run pytest --collect-only -q
   uv run pytest -q
   ```

2. 后端 Ruff 全量通过：

   ```bash
   cd backend
   uv run ruff check app packages/harness/deerflow tests scripts
   ```

3. 前端 unit test、TypeScript、lint 和 production build 全部通过：

   ```bash
   cd frontend
   pnpm test:unit
   pnpm typecheck
   pnpm lint
   pnpm build
   ```

4. PrismOS 品牌迁移已有门禁仍然通过，包括品牌扫描、allowlist、环境兼容、产品身份、Shell syntax、Compose 配置和迁移专项测试。
5. `backend/opsintech.db` 未被修改、重建、复制或迁移；数据库 schema、API path、Alembic 历史、持久化 ID、`deerflow` import 和 LangGraph 接口保持稳定。
6. 没有通过放宽 TypeScript、lint、pytest、Ruff、CI 或测试断言来制造绿色。
7. 目录改名前，工作树、远端配置和路径引用均完成只读检查；目录目标不存在时才执行：

   ```text
   /Users/yespon/Documents/AgentOS/prism-platform
   → /Users/yespon/Documents/AgentOS/prism-os
   ```

## 3. 分层实施策略

### 阶段 A：前端 TypeScript 与 production build

先从失败日志和数据流定位根因，不先做批量类型断言或配置放宽。处理顺序为：

1. 复现当前 `pnpm typecheck` 和 `pnpm build`；
2. 对每个错误簇建立最小回归测试或可重复的类型验证；
3. 修复 `src/app/workspace/files/page.tsx` 的 folder stack 边界问题及其他真实类型错误；
4. 清理翻译类型字段、sandbox 类型和相关消费者之间的契约不一致；
5. 逐次运行 focused test、`pnpm typecheck` 和 `pnpm build`；
6. 只有错误归零后才进入阶段 B。

阶段 A 允许调整业务代码中的类型和边界处理，但不允许使用 `any`、`@ts-ignore`、关闭 strict mode、缩小检查范围或修改 build 脚本来绕过错误。

### 阶段 B：前端 unit test 与 lint

阶段 B 以现有失败基线为参照，按失败簇而不是按文件机械修改：

1. 先修复缺失 `I18nProvider`、`QueryClientProvider` 等测试运行时上下文；
2. 修复翻译 mock、`useTestModelConnection` 等与实际组件契约不一致的 fixture；
3. 每个失败簇先保留一个能够证明失败原因的测试，再以最小生产代码或测试工具修复；
4. 按 ESLint 规则类别和模块边界清理 lint；
5. 每个阶段性提交都运行相关 unit test、`pnpm typecheck` 和对应 lint 范围；
6. 阶段 B 结束时，`pnpm test:unit` 和 `pnpm lint` 必须退出码为 `0`。

不得删除有业务意义的测试、降低断言强度、全局禁用规则或仅通过修改 fixture 让错误测试“通过”。

### 阶段 C：后端 pytest

后端失败按根因簇分批处理，每批都必须先完成证据收集和回归测试：

- tenant/auth 测试环境与依赖注入；
- client / e2e client 的请求、认证和异步边界；
- model factory 与模型配置契约；
- task tool 的输入输出和错误边界；
- 数据库 schema、fixture、事务和迁移状态；
- 其他可由完整 traceback 证明的独立失败簇。

每一簇的流程是：复现 → 追踪数据流 → 写最小失败测试或修正失真的既有测试 → 最小实现修复 → focused pytest → 相邻测试 → 全量 pytest。不得以跳过测试、增加宽泛 fixture、静默吞异常或修改持久化协议的方式消除失败。

### 阶段 D：后端 Ruff

后端 Ruff 在 pytest 稳定后处理，按模块和规则类别分批：

1. 先处理未定义名称、错误 import、可能改变运行时行为的规则；
2. 再处理 import 排序、未使用 import、类型现代化等机械规则；
3. 每批修改只覆盖明确的模块边界；
4. 每批执行对应 pytest 和 `ruff check`；
5. 最终执行全仓 Ruff，确保没有通过扩大 ignore、修改选中的规则或隐藏目录来制造绿色。

### 阶段 E：重新执行 Task 11、目录改名与本地合并

阶段 A–D 完成后，重新运行原品牌迁移计划的 Task 11 全量验证，并保存命令、commit SHA、摘要和失败输出（若有）。所有命令均为 `0` 且品牌门禁仍通过时：

1. 检查没有未提交的代码变更，确认目标目录不存在；
2. 检查脚本、IDE 配置和自动化任务没有硬编码旧绝对路径；
3. 将本地目录从 `prism-platform` 改为 `prism-os`；
4. 在新路径复核分支、remote、HEAD、工作树和关键命令；
5. 将迁移分支合并到本地 `main`；
6. 输出最终验证证据和合并结果。

如果任一 Task 11 命令失败，目录改名和合并均不执行；失败必须回到所属阶段，以新的测试证据和提交重新处理。

## 4. 不变边界

以下内容不是本任务的修复对象：

- AI 运维闭环及其产品化；
- AgentOS/PrismOS 的新业务能力；
- `backend/opsintech.db`；
- 数据库 schema、Alembic 历史和持久化 ID；
- `deerflow` import 和 LangGraph 接口；
- 远端 GitHub 仓库设置、Release、Packages 和外部协作状态；
- 与当前失败没有因果关系的架构重构、依赖升级或大规模格式化。

品牌迁移中的兼容边界保持不变：旧 `OPSINTECH_*` 输入只作为 `0.2.x` 兼容桥，`.opsintech` 数据只读、显式迁移、可回滚，`0.3.0` 删除运行时旧品牌兼容输入。

## 5. 提交与审查策略

每个阶段拆为独立提交或一组职责单一的提交：

- A：前端类型/build 根因修复；
- B：前端测试上下文、fixture/mock 与 lint；
- C：后端 pytest 失败簇；
- D：后端 Ruff 规则债务；
- E：验证证据、目录改名和本地合并操作记录。

每个任务使用 Subagent-Driven 流程：独立 implementer、任务级规格/质量 review、必要时 scoped re-review；最终在 Task 11 前进行整分支 review。所有测试失败修复遵循系统化调试和 TDD：先复现根因，再写能够证明失败的测试，之后实施最小修复。

## 6. 风险与停止条件

以下情况必须停止当前阶段并重新评估，而不是继续堆补丁：

- 同一根因连续三次修复仍失败；
- 修复要求修改上述不变边界；
- 测试通过依赖网络、外部服务或不可复现的本地状态；
- 只能通过放宽质量门禁才能变绿；
- 发现品牌迁移提交引入了新的失败，且无法在当前阶段隔离；
- 目录目标已存在、路径引用无法安全迁移或工作树存在非本任务变更。

任何停止都必须记录在本任务 ledger 中，包含复现命令、证据、假设、已尝试修复和下一步决策。
