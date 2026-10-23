# PrismOS

[English](./README.md) | 中文

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![Node.js](https://img.shields.io/badge/Node.js-22%2B-339933?logo=node.js&logoColor=white)](./Makefile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Built on DeerFlow](https://img.shields.io/badge/Built_on-DeerFlow-8A2BE2)](https://github.com/bytedance/deer-flow)

PrismOS 是面向企业团队的可治理 Agent 操作系统。当前版本提供多租户控制面、
RBAC、模型配置、Skill、MCP 集成、沙箱执行、产物管理以及可扩展的运行时基础。

项目目前处于早期 alpha 阶段。产品边界有意大于当前实现：本仓库先建立平台基础设施，
再逐步补齐治理、工作流、评测、连接器和联邦能力。

> AI 运维只是 PrismOS 的验证场景，不是核心架构前提。平台基础应当支持其他企业
> Agent 场景，而不与某一个 AI 运维闭环耦合。

## 平台契约状态

M1/P0 契约基线已实现；可治理执行闭环尚未完成。冻结的 v1 边界、迁移指引、
验证证据和明确的非能力范围见[平台契约基线](./backend/docs/PLATFORM_CONTRACTS.md)。

## 能力基线

| 领域 | 当前实现 |
| --- | --- |
| 多租户 | 用户、租户、全局作用域，以及租户感知的数据存储 |
| RBAC | 平台与租户管理角色，以及受保护的管理接口 |
| 模型配置 | 数据库驱动的模型/厂商配置和按租户分配 |
| Skills | 作用域 Skill 管理、编辑、导入和沙盒测试 |
| MCP | 按租户配置 MCP Server，并执行健康检查 |
| 沙箱执行 | 本地、Docker，以及可选的 Kubernetes provisioner 模式 |
| 产物与文件 | 上传、线程文件、生成产物、预览和下载 |
| 管理能力 | 用户/租户管理、公告、审计视图和管理后台 |
| 垂直插件 | 告警、终端、资产等可选能力插件 |

以下能力已有基础或局部实现，但还没有形成完整的平台契约：

- Agent 管理、插件 SPI、运行时抽象
- 覆盖所有执行和治理域的统一审计模型
- 生产级隔离、策略执行和完整生命周期控制

## 架构边界

```text
浏览器
  │
  ▼
Nginx :2026 ─────────────── 本地统一入口
  ├── Frontend :3000       Next.js / React 工作台与管理后台
  ├── Gateway :8001        PrismOS API、多租户、RBAC、模型、Skill、MCP、文件
  └── LangGraph :2024      Agent 执行服务
                                │
                                ├── DeerFlow 兼容 harness
                                ├── LangGraph 编排
                                └── sandbox、tools、memory 与 artifacts
```

当前 PrismOS 继续使用 DeerFlow 兼容 harness 和 LangGraph 作为执行基础。为保持兼容，
`deerflow` Python import 路径、既有 API 路由、数据库表、Alembic migration 以及已有
用户数据路径均保留。因此，alpha 版本应理解为围绕现有 Agent runtime 建立的治理型
平台层，而不是已经交付的独立 Agent runtime。

## 产品路线图

白皮书是长期 roadmap，后续平台原语将与单一垂直场景解耦推进：

1. **治理原语**：Policy 模型、授权决策、审批，以及一致的审计/事件契约。
2. **执行生命周期**：一等 Task/Run 对象、状态迁移、取消、重试、幂等和持久化执行历史。
3. **工作流生命周期**：版本化工作流、触发器、DAG、条件、审批和 Agent executor 节点。
4. **评测与可观测性**：可追踪评测、数据集、质量信号、成本归因和运行时指标。
5. **连接器与运行时独立性**：连接器契约、外部身份/集成边界，以及逐步摆脱当前
   DeerFlow/LangGraph 依赖的运行时抽象。
6. **联邦能力**：在上述基础稳定后，再建设跨组织发现、信任、授权和受策略约束的交换。

Policy、Task/Run 生命周期、Workflow 生命周期、Evaluation、Connector federation、
runtime independence 和 Federation 都是 roadmap 项目，不是当前版本已交付的完整平台能力。

## 快速开始

最短的本地启动路径见 [QUICKSTART_zh.md](./QUICKSTART_zh.md)：

```bash
git clone https://github.com/yespon/prism-os.git
cd prism-os
make config
make up
curl http://localhost:2026/health
```

打开 <http://localhost:2026>，完成首次管理员初始化，并在管理后台配置模型。更多模式请参考
[配置指南](./backend/docs/CONFIGURATION.md) 与 [贡献指南](./CONTRIBUTING.md)。

## 配置与兼容性

新部署使用 `PRISMOS_*` 环境变量，默认运行时数据目录为 `backend/.prismos`。
已有安装在变更数据目录前，应先阅读
[PrismOS 品牌迁移指南](./docs/migrations/prismos-brand-migration.md)。不要提交填充过的
`config.yaml`、`.env`、API key、模型凭据或数据库密码。

## 安全与 alpha 限制

PrismOS 已提供租户感知的访问控制、RBAC、审计视图和多种 sandbox adapter，但这些能力不等于
生产安全认证。默认本地 filesystem sandbox 会在宿主机上执行，不能作为生产隔离承诺。Docker
与 Kubernetes 模式也需要运维人员自行审查镜像来源、权限、网络策略、资源限制、密钥处理和
宿主机挂载。

本 alpha 不承诺完整的 Policy engine、Task/Run 生命周期、Workflow engine、Evaluation system、
Connector federation 或独立 Agent runtime。安全问题请按照 [SECURITY.md](./SECURITY.md) 的方式私下报告。

## Release 与容器

首个计划版本为 `v0.1.0-alpha.1`，以 GitHub pre-release 形式发布：

```text
ghcr.io/yespon/prism-os:v0.1.0-alpha.1
```

请使用不可变的版本 tag 进行审阅和部署。alpha 阶段不创建 `latest` 标签。本地 release notes
见 [docs/releases](./docs/releases)。

## 开发验证

```bash
make check
make install
cd backend && uv run pytest --collect-only -q
cd ../frontend && pnpm check && pnpm test:unit
```

必须分别报告 passed、skipped 和 failed。收集成功不等于全量测试通过。

## 文档

- [5 分钟快速开始](./QUICKSTART_zh.md) / [English](./QUICKSTART.md)
- [架构概览](./backend/docs/ARCHITECTURE.md)
- [配置指南](./backend/docs/CONFIGURATION.md)
- [API 参考](./backend/docs/API.md)
- [贡献指南](./CONTRIBUTING.md)
- [安全策略](./SECURITY.md)
- [项目发布设计](./docs/superpowers/specs/2026-08-07-prismos-project-publishing-design.md)

## 参与贡献

PrismOS 是独立维护的仓库。欢迎有项目访问权限的贡献者提交 Issue、设计讨论、文档改进和聚焦的
Pull Request。提交前请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 许可证与上游归属

PrismOS 使用 [MIT License](./LICENSE)。当前 Agent 执行基础包含
[DeerFlow](https://github.com/bytedance/deer-flow) 与 [LangGraph](https://github.com/langchain-ai/langgraph)，
因此保留其名称和链接用于准确归属及技术说明。其他主要组件包括
[LangChain](https://github.com/langchain-ai/langchain) 和 [Next.js](https://nextjs.org/)。
