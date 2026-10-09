# Octop 迁入首批交付与后续实施入口

日期：2026-10-09。分支：`codex/octop-integration`；宿主起点 `d7ef525`；独立工作区 `/root/.codex/worktrees/octop-integration/prism-os`。本记录是已实现的 R0/R1 有界增量，承接全量迁入方案；不是完整 Octop 等价交付或原 M1–M7 退出声明。

## 已交付

- 固定 Octop `v1.0.2b6` / `eb28011249c02cafd389b2d424294c6c1b9cf422` 完整主仓归档，3,771 个源文件、许可证和逐文件哈希。1,035 个原样文件纳入独立能力包；源码与 PrismOS Adapter 分离；Git 忽略规则为这批固定资源目录添加明确例外，仍排除 Python 缓存，确保全新检出不会漏文件。
- 原新建 Agent 页面可搜索、预览和编辑专家/子智能体提示词，选择 16 MBTI 人格；中文目录 18 专家 + 272 子智能体，英文目录 18 专家 + 217 子智能体。语言目录包含重复概念，不能把两种语言之和当作独立 Agent 数。
- 目录 API 复用现有认证和租户；创建、共享授权、模型、MCP、Skill 和数据库继续走原 CustomAgent 路径，保存模板来源和创建时 prompt 摘要。没有引入第二套身份、数据库迁移或执行事实。
- 通过真实数据库与原 host provider 验证配置加载及 DeerFlow `<soul>` 提示词组装。该检查发现并修复既有 `runtime_adapters` 查询取值错误：SQLAlchemy `select` 的结果需 `.scalars()` 才是模型对象；加载和列表均修复。
- `octop_sync.py` 支持 import/verify/compare；原始库脚本和插件只作为资源保存。`octop_upgrade_probe.py` 在临时目录使用相同宿主测试演练旧→新来源，不修改运行目录。安装包检查验证所有迁入字节、目录清单及实际 wheel 解包导入。
- 新增本地构建入口和 GitHub Actions 构建/回归工作流。现有依赖版本与哈希保持不变，锁文件仅增加本地能力包及生成器 metadata revision；本地包不交给公共 PyPI 漏洞审计，全部外部依赖仍按原流程审计。

## 实测证据

| 验证 | 本地结果 |
| --- | --- |
| 后端全量 pytest | 1,422 通过、18 跳过、30 个警告 |
| 前端全量 Vitest | 40 文件、94 用例通过 |
| 前端类型与生产构建 | 通过；42 页构建完成 |
| `make octop-build` | 来源、回归、类型、真实 Gateway 冒烟、wheel 和 Next 构建全部通过 |
| wheel 安装资源 | 1,035 文件哈希通过；安装位置导入得到中文 290 / 英文 235 模板与 16 人格 |
| 真实 Gateway | 完整 Alembic 启动、真实 Better Auth session、租户 Membership、模板创建和重新读取通过；使用临时 SQLite |
| b5 → b6 试验 | 相同宿主分别 9 项契约通过；迁入目录仅 1 个配套脚本变化，纯模块无变化 |

b5→b6 检查发现上游依赖声明变化；四个外部 Octop 包尚未接入，因此不能由本次目录升级试验推导完整运行时兼容。变化的微信公众号脚本没有被执行或安装。原模板与来源记录保持固定，新导入不覆盖已创建 Agent 的配置。

证据：[汇总](../superpowers/evidence/2026-10-09-octop-source-import/summary.json)、[Gateway](../superpowers/evidence/2026-10-09-octop-source-import/gateway-smoke.json)、[升级演练](../superpowers/evidence/2026-10-09-octop-source-import/upgrade.json)、[42 项能力进度](../superpowers/evidence/2026-10-09-octop-source-import/capability-ledger.json)。

## 日常运行和每批验证

在该独立工作区根目录执行，使用 Python 3.12+、uv、Node 22+ 与声明的 pnpm 10.26.2：

```bash
make config
make install
make octop-verify
make octop-check
make octop-smoke
make octop-build
make dev
```

`make config`/`make install`/`make dev` 为既有启动路径，需要按原方式配置模型和数据库。`make octop-smoke` 自动创建并销毁测试数据库与临时 session，无需现网凭据。`make octop-build` 包含该冒烟；本地依赖包可从 `backend/dist/` 获取。构建不代表服务已部署。

本机已安装独立 backend 环境，并复用既有前端 node_modules 进行验证；pnpm 的独立缓存位于 `/tmp/prismos-octop-corepack`，避免损坏的共享 Windows Corepack 缓存。CI 使用冻结锁文件重新安装。CI 文件已落盘，但未推送或运行远端 CI。前端构建存在既有 mock artifact 路由 tracing/root 警告，新增界面静态检查只有既有 unused-import 警告，无错误。

完整回归入口保持 `cd backend && uv run --locked pytest tests/ -q` 与 `cd frontend && pnpm test:unit`。来源检查失败、撤权失败、兼容回归失败或升级迁移失败时停止该批进入主线。

## 持续融入上游

下载指定 commit 的来源归档后，先比较，不自动追 main：

```bash
python3 scripts/octop_sync.py compare --archive /path/to/candidate.tar.gz --revision COMMIT --release TAG --output /tmp/octop-candidate.json
```

在候选分支 import，再跑上述验证，逐项审查 `dependency_changed`、`runtime_module_changes` 和能力缺口。仅在新的包、前端、宿主契约和所需迁移通过后替换制品并重启；禁止向正在运行的安装目录原地写入。旧→当前的同宿主验证入口：

```bash
backend/.venv/bin/python scripts/octop_upgrade_probe.py --previous-archive /path/to/previous.tar.gz --previous-revision PREVIOUS_COMMIT --previous-release PREVIOUS_TAG --output /tmp/octop-upgrade.json
```

本切片未增加数据库 schema，可回退本次代码和构建制品；创建的 Agent 仍使用旧结构。后续知识、调度、团队引入 schema 或副作用时，必须同时实现迁移/恢复和执行治理门，不能沿用本切片的无迁移结论。

## 接下来按方案推进的边界

1. P0：与原 SecretRef 分支收口 M1；本分支不覆盖未提交的其他任务，不把目录迁入当成 M1 退出。
2. P1：最小持久 Run/配置快照、完整专家共享与子智能体绑定、配套资源安装；保持原执行入口和权限，补齐编辑/撤回/恢复证据。
3. P2：迁入知识业务模块，接 PrismOS Repository、文档/索引 ACL 与通用 Secret 接缝；实现检索、引用、撤权后不可召回及两类参考 Connector。
4. P3 及后续：Cron/Teams、设备与多模态、目录生命周期和多端，继续按全量账本及原里程碑退出门收口。

完整源码归档没有包含 `octop-harness`、`octop-memory`、`octop-gateway`、`octop-browser` 独立包源码与环境；也没有启用所有配套 Skill/scripts。人格测验、知识库、Cron/Teams、设备、多端、完整 42 组能力仍未完成。当前没有真实外部模型/工具调用、PostgreSQL、容器部署和跨端制品的验收证据。
