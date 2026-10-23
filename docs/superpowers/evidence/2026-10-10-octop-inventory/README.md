# N05：固定来源的逐项能力与依赖盘点

日期：2026-10-10。固定来源 b6 / `eb28011249c02cafd389b2d424294c6c1b9cf422`。原 PrismOS 路线及 O01–O42/F01–F12 全范围保留；此批盘点与来源修正不能代替完整运行等价或 M1 真实环境验收。接续见 [滚动推进计划](../../plans/2026-10-10-octop-rolling-execution-plan.md)。

## 清单与证据范围

| 文件 | 覆盖 |
| --- | --- |
| `summary.json` | 原主仓 3,771 个 regular members；保留主仓 3,585、外部源码 653；实际迁入 849；主仓排除 186、外部排除 51 |
| `source-index.json` | 4,475 项：4,238 个保留源文件的来源/摘要/静态导入，以及 237 个排除成员的路径/摘要收据；排除项 content_retained=false，不声称其字节在离线验证中仍可重算 |
| `capability-items.json` | 18 专家、538 专家资源条目、92 Skill/替代实现条目、241 脚本目录/程序条目、489 子智能体模板、123 人格/欢迎/头像内容、31 插件、26 Connector、494 接口声明；包含资源缺口和脚本目录的配套数据，不能全部视为可执行文件 |
| `excluded-resources.json` | 全部 237 个排除资源，逐项保留原功能映射、摘要、权限/依赖/责任角色和待独立实现状态；没有保留原内容 |
| `capability-ledger.json` | 原 O01–O42、逐项 children 与完整等价 false；每项运行验收继续完成 |
| `future-ledger.json` | 原 F01–F12 与固定调研中的官方状态、关系和落点；未重新冒充最新路线核验 |
| `dependencies.json` | 四包精确版本、根许可证、来源、核心/extra 需求与宿主/上游锁定版本；按明确 Linux x86_64 / CPython 3.12 目标评估 markers，不表示 Windows/macOS 已验证 |
| `coupling-edges.json` | 1,609 条对 Octop 四 namespace、DeepAgents/LangGraph/LangChain/MCP Adapter 的静态导入边，未证明运行兼容 |
| `resolver-evidence.json` 与 `frozen-host-*` | 真实 uv 核心组合解析失败及精确输入；未安装四包，宿主锁不变 |
| `curated-upgrade-rollback.json` | b5→b6→b5 临时过滤能力包、来源校验与相同宿主目录契约结果；不涵盖尚未接入的耦合模块 |

每个条目有 archived/imported/adapted/verified、权限、依赖、责任角色、证据和 remaining。责任角色尚未指定实际人选。排除资源的 archived/imported/adapted/verified 均为 false；摘要收据不表示持有源码。目录 prompt materialization 与来源完整性有证据，专家完整资源执行/共享/委派仍待验。494 项是源码装饰器声明，不能推断已部署 API；开发 Skill 明确标记 development_only。

## 四包依赖与边界

| 精确包 | 根声明与独立资源 | 后续接缝 |
| --- | --- | --- |
| octop-harness 1.0.1 | MIT；双语 PowerPoint 独立资源已排除 | DeepAgents/LangGraph、模型、MCP、Workspace、ACP/设备，经宿主 Adapter 或版本化 Worker 接入；身份、执行事实、PEP、Secret 属于 PrismOS |
| octop-memory 1.0.0 | MIT | 存储/向量等 extras，N10/M6 补 ACL、来源、删除与索引版本 |
| octop-gateway 1.0.0 | MIT | N11/N14 渠道与投递适配，共用 tenant/actor/Run |
| octop-browser 1.0.0 | MIT | N12 CDP/MCP/录制、设备归属、权限、取消与 Artifact |

固定发行页：[Harness](https://pypi.org/project/octop-harness/1.0.1/)、[Memory](https://pypi.org/project/octop-memory/1.0.0/)、[Gateway](https://pypi.org/project/octop-gateway/1.0.0/)、[Browser](https://pypi.org/project/octop-browser/1.0.0/)。实际 Metadata、独立声明和摘要以 manifest 为准。

Harness 要求 langchain-mcp-adapters >=0.3.0，宿主锁定 0.2.1；保留全部宿主 registry 版本的真实解析结果为 unsatisfiable。[all] 包含同一核心要求，不能解决冲突。此结果证明约束冲突，不能代替行为/安全/设备测试；下一阶段选择性迁入或评估隔离 Worker，替换 Runtime 仍受原 C1 证据门约束。

## 来源修正与替代实现

主仓 Office DOCX/PDF/PPTX/XLSX 的四个子树共 186 文件，四份 LICENSE.txt 摘要均为 `79f6d8f5b427252fa3b1c11ecdbdb6bf610b944f7530b4de78f770f38741cfaa`。Harness 英文 PowerPoint 为相同条款，中文 Skill 声明 Proprietary；双语共 51 文件一并排除。已移除当前迁入数据和归档中的对应字节，保留允许文件的原样内容、根许可证与版权声明。

原始归档摘要与过滤归档摘要分开；成员摘要收据由独立固定摘要锚定。重新改写保留归档及收据不能伪造原来源，已知受限资源不能通过恢复文件、变更 exclusions 或打包额外文件进入候选。已有 Git 历史未重写，本文的交付范围为当前文件树与候选制品；历史发布另核对。

DOCX/PDF/PPTX/XLSX 和双语 PowerPoint 保留独立实现条目与 O05/O07 映射。Office 专家目录 API 响应继续提供原专家 prompt，同时列出缺失配套资源；资源未自动安装，不授予工具权限。功能目标没有随排除源码而删除。

## 重复验证

`make octop-inventory` 验证主仓、外部输入与全部生成清单，并纳入 `make octop-build`；后者还验证真实认证 Gateway、wheel/sdist 来源和资源排除、前端类型与生产构建。离线检查不运行上游插件或脚本，不下载或安装外部 Runtime。

显式重建：`uv run --project backend --locked python scripts/octop_inventory.py generate`。原锁下载并校验后重新过滤：`python3 scripts/octop_external.py fetch`，不是追最新版本。新来源需审查摘要锚点、许可证、依赖、权限和行为差异后才接受。

本批测试/构建摘要另见 `validation.json`（仅在实际运行取得结果后生成）。源码/目录证据与完整用户行为分开记录；M1/N04 目标数据库、真实模型/Tool/接收端、身份传播与部署回退仍待验。
