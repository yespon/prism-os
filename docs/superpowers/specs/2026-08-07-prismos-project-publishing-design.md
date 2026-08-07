# PrismOS 项目品牌与发布一致性迁移设计

## 1. 背景

GitHub 仓库已经从 `prism-platform` 脱离上游 Fork、改为私有，并重命名为 `prism-os`。但代码仓库仍存在大量 `OpsinTech`、`opsintech-platform` 和 `deer-flow-frontend` 标识，README、Quickstart、Contributing、Docker、Python/前端包元数据以及 GitHub 展示信息尚未形成统一的 PrismOS 项目身份。

本设计将完成一次项目级品牌与发布基线迁移，使以下信息保持一致：

```text
产品名称       PrismOS
GitHub 仓库    yespon/prism-os
Python 项目    prismos
Frontend 包    prismos-frontend
容器镜像       ghcr.io/yespon/prism-os
首个版本       v0.1.0-alpha.1
```

本次工作只改变项目表达、发布元数据和兼容性配置，不改变 Agent Runtime、Gateway、数据库模型和业务功能。

## 2. 目标

### 2.1 项目叙事

PrismOS 定位为面向企业 Agent 的治理与执行基础设施：

> PrismOS is a governed Agent operating system for building, running, and operating enterprise Agents with explicit boundaries, auditable execution, and a path toward runtime independence.

中文表述为：

> PrismOS 是面向企业 Agent 的治理与执行操作系统，为 Agent 提供多租户控制、权限边界、沙盒执行、工具与 Skill 管理、审计和可演进的运行时基础。

README 必须把能力分为：

- 当前已实现：多租户、RBAC、模型配置、Skill、MCP、沙盒、Artifact、管理后台和垂直插件；
- 当前部分实现：通用 Agent 管理、插件 SPI、运行时抽象、统一审计；
- 路线图能力：通用 PolicyEnforcer、Task/Run、Workflow、Evaluation、Connector、独立运行时和 Federation；
- 已知限制：当前仍依赖 DeerFlow/LangGraph，默认存储以本地文件系统为主，尚未形成完整企业 Agent 生命周期。

### 2.2 GitHub 展示

GitHub About 信息采用以下内容：

- Description：`PrismOS is a governed Agent operating system for enterprise teams, with multi-tenant control, RBAC, sandboxed execution, Skills, MCP, artifacts, and an extensible runtime foundation.`
- Homepage：`https://github.com/yespon/prism-os`
- Topics：`agentos`、`ai-agents`、`agent-platform`、`agent-governance`、`agent-runtime`、`mcp`、`langgraph`、`multi-tenant`、`sandboxed-execution`、`enterprise-ai`、`agentops`、`python`、`nextjs`、`docker`

不使用旧的 `http://www.prism.ai` Homepage，避免把项目指向未验证的外部站点。

### 2.3 发布和 Packages

PrismOS 当前是完整应用，不是稳定的 Python SDK 或 npm 组件。因此只发布 OCI 容器镜像，不发布 PyPI/npm 包。

GHCR 目标：

```text
ghcr.io/yespon/prism-os
```

镜像标签：

- Git tag：`v0.1.0-alpha.1`；
- SemVer 版本标签：`0.1.0-alpha.1`；
- Git commit SHA；
- `edge` 指向默认分支最新可构建版本；
- 不发布 `latest`，避免预发布版本被误当成稳定版本。

首个 GitHub Release 使用 `v0.1.0-alpha.1`，标记为 pre-release，明确说明这是治理平台基础版本，不代表白皮书中的全部 Agent OS 能力已经实现。

## 3. 文档范围

### 3.1 主要文档

- `README.md`：英文产品入口、能力基线、路线图、部署和开发入口；
- `README_zh.md`：中文产品入口，与英文版结构对应；
- `QUICKSTART.md`、`QUICKSTART_zh.md`：统一新仓库地址、项目名和命令说明；
- `CONTRIBUTING.md`：统一项目名、仓库地址、贡献流程和本地目录示例；
- `SECURITY.md`：统一安全报告地址和支持版本表；
- `.github/ISSUE_TEMPLATE/config.yml`：更新 Discussions 和 Security Advisory 链接。

### 3.2 配置和工程标识

以下标识改为 PrismOS 默认值：

- Python `project.name`：`prismos`；
- Frontend `package.json.name`：`prismos-frontend`；
- Docker Compose 项目名、容器名和网络名：`prismos`；
- 新环境变量前缀：`PRISMOS_*`；
- 默认数据库和运行目录名称：`prismos`。

为避免破坏已有部署，配置读取层继续兼容 `OPSINTECH_*`，优先级为：

```text
PRISMOS_* → OPSINTECH_* → 默认值
```

旧变量只作为兼容入口，不再出现在新文档的首选示例中。

不重命名以下内容：

- `deerflow` Python import path；
- DeerFlow/LangGraph 上游适配目录；
- 数据库表名和既有迁移标识；
- 既有用户数据目录；
- 现有 API 路径。

这些内容属于运行时兼容边界，贸然重命名会扩大本次工作的风险。

## 4. 发布工作流

新增 `.github/workflows/container-publish.yml`：

1. 仅在 `v*` tag 或手动触发时发布版本镜像；
2. 默认分支只构建验证，不推送 `latest`；
3. 使用 GitHub Actions 内置 `GITHUB_TOKEN` 写入 GHCR；
4. 构建多架构镜像时优先支持 `linux/amd64` 和 `linux/arm64`；
5. 镜像元数据写入版本、commit SHA 和 source label；
6. Release 发布前必须通过配置检查、后端测试收集、前端静态检查和 Docker 配置校验；
7. 当前测试基线若仍有阻断错误，Release Notes 必须明确列出，不得标注为稳定版。

本阶段不新增独立 Python build artifact，也不把 `backend/packages/harness` 作为公开 PyPI 包发布。

## 5. 首个 Release 内容

`v0.1.0-alpha.1` 的 Release Notes 采用以下结构：

1. PrismOS 产品定位；
2. 当前可用能力；
3. Docker 启动方式；
4. GHCR 镜像地址和标签；
5. 已知限制；
6. 与 DeerFlow/LangGraph 的关系；
7. 下一阶段路线：Governed Foundation → Managed Agent Runtime → Reliable Execution。

Release 不宣称：

- 已经完成通用 PolicyEnforcer；
- 已经完成通用 Workflow Engine；
- 已经完成 Agent 生命周期和 Evaluation；
- 已经摆脱 DeerFlow/LangGraph；
- 已经适合所有企业生产环境。

## 6. 验收标准

### 文档

- README 中不再出现旧仓库地址；
- README、Quickstart、Contributing、Security 的项目名统一为 PrismOS；
- 所有当前能力、部分能力和规划能力有明确区分；
- README 中的部署命令与 Makefile/Docker Compose 实际命令一致；
- 中英文 README 章节结构和核心事实一致。

### 工程标识

- 新安装路径默认使用 PrismOS 标识；
- `OPSINTECH_*` 兼容路径仍可读取；
- 不改变数据库表名、API 路径和 DeerFlow 适配导入；
- `git diff --check` 通过；
- 文档和配置中不存在未解释的旧仓库链接。

### GitHub

- About Description、Homepage、Topics 已更新；
- 仓库显示为私有、非 Fork；
- `v0.1.0-alpha.1` Release 为 pre-release；
- GHCR 中存在对应版本镜像；
- Packages 页面不出现未经设计的 PyPI/npm 发布物。

## 7. 非目标

本次不包含：

- Agent Runtime 重构；
- Workflow、Policy、Evaluation 等白皮书核心能力实现；
- 业务插件逻辑改造；
- 数据库 schema 重命名；
- 公开 Marketplace、Federation 或 SDK 生态；
- 修改许可证或上游依赖授权关系。

## 8. 风险和回滚

- Docker 项目名和环境变量变化可能影响已有部署；通过旧变量兼容和保留旧数据路径降低风险；
- GitHub Release 和 GHCR 发布会形成外部版本记录，首版使用 alpha 预发布降低承诺；
- 仓库为私有，GHCR 默认保持私有；公开镜像必须另行决策；
- README 改写不会删除历史文档，所有变更可通过 Git 回滚；
- 如果容器构建或测试未通过，只发布文档和元数据更新，不创建误导性的版本镜像。
