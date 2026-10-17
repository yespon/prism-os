# Octop 全量能力与 PrismOS 原规划一致性复核

**日期：** 2026-10-08（Asia/Shanghai）  
**状态：** 全量覆盖核对与增量交付建议；保留已批准 Capability Roadmap，不是功能已实现声明，也不是新增日历承诺。  
**用户要求：** 完整覆盖 Octop 能力，保留 PrismOS 原规划，核对 Octop 后续规划与原规划的一致性。  
**PrismOS 代码基线：** 本次检查 HEAD `94528e6d5d0d9ac8d23ff141fb07a4955795ba12`。工作区另有正在实施的工单 SecretRef 改动，不计作完成证据。  
**Octop 源码基线：** `main` @ `0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda`，提交时间 2026-10-08 12:04:38（北京时间）。  
**Octop 发布基线：** 本次查询最新发布 `v1.0.2b6`；GitHub published_at 为 2026-10-04 23:59:40 UTC，即北京时间 2026-10-05 07:59:40。CHANGELOG 标题使用 2026-10-04；源码 main 与发布 tag 分别判断。

**后续交付建议：** 用户进一步允许批量复用源码后，另见 [优先级与实施节奏调整](./2026-10-08-octop-integration-priority-and-delivery-plan.md)。该建议保留本文能力清单和原平台最终门，提出调整串行排期、提前必要契约切片；本文原阶段落点不再作为新建议唯一的功能上线时点，原批准路线尚未改写。

## 1. 复核结论

PrismOS 应以“原有受治理执行平台能力 + Octop 完整产品能力”形成目标全集。此前采纳计划只给部分能力安排了阶段，且明确把桌面、远程桌面、MBTI、多渠道和公共市场放在默认 Backlog 之外，不能据此宣称已经满足完整覆盖要求。本次为这些能力以及语音、多模态、主动推送、SSO、桥接、自进化、托管和 Project 建立显式映射及验收目标。

两者在 Agent 管理、协作、知识、连接器、扩展和自然语言操作方面高度相交；**不能判定两条路线完全一致**。Octop 的原生客户端、自动技能沉淀、平台托管、云边端调度和公共生态包含原 PrismOS 批准路线之外的产品或基础设施范围。PrismOS 的确定性 Policy、持久 Task/Run/Attempt/Action、不可变版本、质量晋级和专项安全门也不能从 Octop 的功能名称推定已存在。

原路线依赖仍为：**M1 治理 → M2 执行生命周期 → M3 Runtime/质量证据 → M4 Agent 资产 → M5 Workflow → M6 数据/知识 → M7 扩展供应链**。完整覆盖通过这些阶段和依赖它们的配套产品工作包实现；新增客户端、设备和生态不另建执行、权限或审计内核。

“完整覆盖”在本文指：当前公开功能表面和官方未来方向均进入有编号的能力清单，没有因原先裁剪而遗漏；最终应有对应用户路径及验收证据。它不表示本次已经交付全部功能、与 Octop 内部实现相同，或已验证所有运行行为。功能等价、平台治理合格、发布日期是三个独立判断。

## 2. 证据和原规划的优先级

### 2.1 PrismOS 原规划

| 层次 | 依据 | 本次如何保留 |
| --- | --- | --- |
| 长期战略 | [正式白皮书](./agentos-whitepaper.md)，尤其 §7、§8、§13–§16 | 企业定位、六层职责、模型/Runtime 中立、工作区、治理、质量与长期演进保留 |
| 批准实施路线 | [Capability Roadmap](../superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md)，状态 Approved | M1–M3 承诺范围、M4–M7 候选门、C1/C2 条件投资、兼容和验收门保持原义 |
| 实现事实 | [差距审计](./agentos-prismos-gap-roadmap-review.md)、[平台契约](../../backend/docs/PLATFORM_CONTRACTS.md)、[M1 门禁证据](./2026-09-25-m1-exit-gate-evidence.md) | 区分已有基础、纳管试点、未通过退出门和未来能力 |
| Octop 历史调研 | [2026-09-24 采纳计划](./2026-09-24-octop-research-adoption-plan.md) | 保留固定提交调研、架构不变量和原阶段映射；完整覆盖及最新外部状态以本复核补充 |
| 旧版本化愿景 | [旧 Governed Agent Platform Roadmap](./governed-agent-platform-roadmap.md) | 保留为追溯素材；依批准路线 §16.1，不恢复旧版本序列、Native Runtime 或 Federation 的无条件承诺 |

用户现在要求完整覆盖，因而不能继续把桌面等能力从调研和目标全集删除。原批准路线 §4.5、§9.4 仍不包含公共 Marketplace、通用 RPA 等默认建设：公共发现分发作为额外产品范围记录，与 M7 企业私有目录分别验收；设备工具只实现 Octop 等价操作路径，不扩张为通用 RPA 平台。这样保留原核心范围，并明确新增工作，避免把“全部一致”作为范围变化的理由。

### 2.2 Octop 证据分层

- **发布证据：** release/tag 及 CHANGELOG；可证明发行声明和制品存在，不证明本地运行验收。
- **源码证据：** 固定 main 提交中的接口和实现；只表示存在可读实现，不自动归入已发布 tag。
- **路线声明：** 英文及中文 README Roadmap；官方明确会调整，没有统一交付日期或 SLA。
- **推断与建议：** 本文的 PrismOS 阶段映射、工作包和产品设计，不是 Octop 官方承诺。

本次读取 README 中英文、CHANGELOG、release 列表、架构、API、CLI、用户手册、团队和 Bridge 文档；用完整 Git tree 盘点 `api/routers` 下 **77 个非 `__init__.py` Python 模块**，补读插件市场、浏览器录制、主动推送、设备状态、角色模板和 Langfuse 配置等实现。路由模块盘点不等于每个 endpoint 已逐条运行。未部署 Octop，未做性能、故障、安全或跨平台运行验证。

## 3. Octop 当前能力全集与 PrismOS 映射

证据编号见 §9。下表的阶段表示依赖位置，不增加该阶段原退出门；“配套”表示原路线未单独承诺的产品工作包，仍须共用平台契约。PrismOS 的“基础/缺口”以本次本地路线、已记录实现和少量源码核对为准，未经专项验证的不标为不存在或完成。

| ID | Octop 能力及核对范围 | Octop 证据状态 | PrismOS 基础/缺口 | 保留原规划的落点与最终验收 |
| --- | --- | --- | --- | --- |
| O01 | 自托管、初始化、模型探测、首次成功对话 | README/CLI/向导公开；E1–E3 | 已有 Docker、setup、模型测试及首次引导 | M1 配套：管理员配置→用户执行→可解释结果；一键编排现有服务，保留进程边界 |
| O02 | 多用户、管理员、账号启停、邀请、角色模板、资源配额 | API/角色实现；E2/E8 | Tenant/User/RBAC 比 owner 更明确；完整模板/邀请/配额另验 | 身份底座配套：模板与实际权限分开；停用、撤权、跨租户和配额边界可验证 |
| O03 | 本地登录、OIDC、飞书/钉钉/企微 OAuth SSO、LDAP、验证码 | API/LDAP b6 发布；E2/E4 | 已有认证和 Membership；联合登录需专项接入 | 身份 Adapter 配套：身份绑定、去重、首次开通和撤销不绕过租户 Membership；登录 OAuth 与 Connector OAuth 分责 |
| O04 | 多 Agent 创建、启停、重载、独立配置及工作区 | README/API；E1/E2 | CustomAgent、子 Agent 已有；不可变版本未交付 | M4：Definition/Version/Deployment、发布、停用、回滚和历史还原 |
| O05 | 内置专家库、专家市场、共享专家、模板导入及复用 | README 已完成共享；E1/E2 | 现有 Agent 配置可复用；共享发布无完整资产闭环 | M4 配置快照与可见性；M7 分发：拥有、复制、使用、编辑、撤回分别授权 |
| O06 | 16 MBTI、人格测试、欢迎语、专家头像 | README/API；E1/E2 | 可复用 Prompt/Agent UI；人格产品需补 | M4 配套：人格只是版本化配置，不改变权限；模板/测试/自定义路径完整 |
| O07 | Skill 开关、技能包、共享池、复制策略、上传、分发 | README/API/CHANGELOG；E1/E2/E4 | 已有 Skill scope/install | M4 版本引用，M7 包生命周期：复制/锁定/拒绝及升级来源可追踪；权限同时约束 UI 和实际工具 |
| O08 | 子智能体库、绑定与资源共享池 | README/API；E1/E2 | 已有 subagent 执行基础 | M4 明确成员与版本；M5 子 Run；M7 共享包：保留来源、授权和撤回语义 |
| O09 | Agent 间问答/委派、AgentTeams 主持人、并行成员、成果回传 | 官方 Beta；团队已有代码与文档；E5 | 有 subagent，完整 Team 资产/治理待补 | M4 成员资产、M5 编排：父/子 Run、成员身份、有限递归、预算、超时、取消和 IM 回传；Beta 不等于稳定 Workflow |
| O10 | Web 工作台、CLI 对话、HTTP/SSE/WebSocket、斜杠命令 | README/API/CLI；E1–E3 | Web/流式执行已有；统一入口待 M2 | M2 Entry Adapter：身份、去重、会话与运行绑定；CLI/API 与 Web 使用同一受治理执行入口 |
| O11 | Ask/Plan/Craft、附件/文件提及、草稿、工具轨迹、通知、历史与重新加载 | API/指南/b1 记录；E2/E4 | 流式聊天、Artifact、Thread 已有 | M2 Run 事实/历史投影；M3 轨迹与来源：刷新、断线、失败、审批后的显示一致，模式不授予权限 |
| O12 | 飞书、钉钉、QQ、微信、Telegram、Discord、企业微信 | 英文 README 通道表；E1 | 当前注册 Feishu/Slack/Telegram；其他通道需逐项适配 | M2 统一绑定后逐通道配套；M5 主动投递；保留 PrismOS Slack，不以 Octop 列表替换现有入口 |
| O13 | 通用 cron/date、自然语言建任务、run-now、时区、执行结果及投递 | CLI/API/架构/修复记录；E2–E4 | 只有场景调度，不是通用产品 | M5 Schedule/Occurrence→Run：时区、重启、重叠、租约、去重、失败与投递重试；M2 不提前建通用调度 |
| O14 | 主动关怀/推送、活跃时间窗和最小/最大间隔 | 独立 API/调度实现；E8 | 无已验收通用主动推送产品 | M5 配套：用户配置、暂停、频率和目标；每次执行/外发可关联 Run/Action，避免另建状态机 |
| O15 | 模型供应商、模板、模型选择/连通性、上下文与运行参数 | API/README；E1/E2 | Model Provider/租户分配已有 | 复用底座，M3 Adapter 能力映射与成本/错误；不重写模型调用层 |
| O16 | Ollama 本地模型发现/下载、目录/服务；本地 ONNX embedding 管理 | API/README；E1/E2 | 本地模型可通过 Provider 接入；完整下载器未验收 | 配套模型管理：明确推理/embedding用途与缓存；下载任务、失败重试、删除和配额，不把“模型已下载”判作可执行 |
| O17 | 图片/视频生成供应商、独立路由、预览/投递 | API/指南/CHANGELOG；E2/E4 | 有 text2image 能力标志/工具，不等于完整生成模型产品 | M3 工具/Artifact契约后配套：两类模型、任务状态、费用和输出来源；执行权限与付费副作用纳管 |
| O18 | STT/TTS、录音、语音供应商配置与测试 | API/指南/历史修复；E2/E4 | 无本次已验收的等价语音闭环 | M3 后配套输入输出 Adapter：语音→同一任务，文本→音频；失败、取消、格式和访问控制可验证 |
| O19 | 层级记忆、召回、压缩、便携迁移、memory slim/维护 | README/API/CLI；E1–E3 | Memory/上下文压缩基础已有 | M3 召回证据、M4 资产绑定、M6 数据 ACL：导出/迁移/删除/维护保留身份与来源；不能把摘要当通用自进化 |
| O20 | 知识库、共享语料、文件夹/文档、解析/索引/检索、引用、重建及删除 | API/知识实现；E2/E7 | File/Storage/Memory基础；通用 RAG产品待补 | M3 研究来源切片；M6 Document/Chunk/IndexVersion/ACL：撤权、索引失败、来源引用与检索审计 |
| O21 | Agent 文件、workspace、上传下载、预览、文件搜索、导入导出 | API/指南；E2/E7 | FileObject、Artifact、文件预览已有 | M2/M3 执行关联，M6 数据治理；路径、版本、跨租户、删除和大文件行为可验 |
| O22 | 工作区 Local/Docker/PostgreSQL/COS-S3、宿主文件系统浏览 | README/API；E1/E2 | Local/Docker/Kubernetes Sandbox、对象存储已有 | Storage Adapter 配套：文件存储与控制面 DB 分开；按后端验 CRUD、权限、迁移和失联；保留现有 K8s 能力 |
| O23 | 环境变量 preset、Agent 工具 env 注入 | API；E2 | 模型/MCP配置及加密种子已有 | M1 限定工单 SecretRef，M6 通用 Secret Provider：普通 env 和 Secret 分开，作用域/用途绑定与运行前注入 |
| O24 | Connector 目录、实例、OAuth/API Key、刷新、健康及 MCP 装配 | API/Connector实现；E2/E7 | 租户 MCP/健康/OAuth已有基础 | M6：两个参考 Connector；标准错误、限流、续期、SecretRef、同步状态与授权撤销 |
| O25 | 腾讯服务、企查查、OpenAlex、Agent Mail 等具体连接器 | README/CHANGELOG；E1/E4 | 原路线只要求两个参考，未覆盖全部目录 | M6 先两类参考验证原退出门，之后逐目录完成等价集成；不是用两个 Connector 宣称全量完成 |
| O26 | 内部 MCP、工具发现/启停、Agent 工具与插件开关 | API/工具路由；E2/E7 | Skill/MCP/Tool装配已有 | M1 纳管动作范围，M3 Adapter能力，M7扩展工具：显示开关、实际装配、权限撤销一致 |
| O27 | ACP 入站服务、外部 IDE 使用 Agent | ACP 文档/CLI；E3/E6 | 外部协议产品未验收 | M3 协议预研，M4 后配套入站：会话、取消、输出和认证范围；不改 Runtime核心 |
| O28 | ACP 出站 OpenCode、CodeBuddy、Claude Code、Codex、Kimi Code、Cursor CLI、Pi，及自定义 Runner | 固定 ACP 文档列出七种内置 Runner，比 README 示例更完整；E1/E6 | Terminal/沙箱可复用；等价 runner 待补 | M3 适配/隔离及 M4版本绑定后配套：逐 Runner 验证启用/会话/委派/取消与自定义配置；委派为受控 Action/子 Run，凭据、文件、网络和进程范围独立约束 |
| O29 | 交互式终端、AI 辅助命令与排障 | README/API；E1/E2 | 已有 Terminal及局部审批，不能算通用 Policy 已完成 | M1 先有界治理试点；M2 Run；M3后配套终端：实际命令、审批、取消、结果和多主机身份一致 |
| O30 | 浏览器会话、持久 profile、截图、远程操控与自动化 | README/API；E1/E2 | 可复用 Sandbox/工具；完整浏览器产品未验 | M3 后配套浏览器 Provider，M5多步骤：隔离profile、下载/外发、取消和审计；插件不得绕开策略 |
| O31 | 浏览器录制、回放、停止后生成 Skill 草稿 | README仍规划；固定main已有API；E1/E8 | 采纳计划未安排完整闭环 | M3设备适配，M4草稿版本，M5受控回放，M7技能分发：敏感输入处理、失败/中断和发布前评价；不计为全局自进化完成 |
| O32 | 远程桌面：屏幕、键鼠、安装/卸载、隔离桌面、跨平台 | README/desktop路由；E1/E8 | 原采纳计划默认排除，当前需纳入 | M3后设备配套：明确设备/会话Owner、查看与控制权限、撤销、输入副作用和断线；不扩成通用RPA |
| O33 | Remote Phone：手机设备状态、绑定、看屏/操控、shell | 固定tree/mobile路由；E8 | 原计划未明确盘点 | 设备配套：手机是被操作目标，与原生移动客户端分开；绑定、可控动作、断开、授权和审计各自验收 |
| O34 | Windows/macOS/Linux 桌面客户端及 FnOS/NAS 制品 | 官方已完成，b6有制品；E1/E4 | 原采纳计划默认排除 | M2稳定API后预研，M3后客户端/打包配套：登录、聊天、审批、断线重连、更新与卸载；复用服务内核 |
| O35 | 移动 Web/PWA、原生移动客户端 | PWA已有修复，原生客户端官方内测；E1/E4 | 响应式UI可复用，原生app未验 | 客户端配套：分别验证PWA和原生移动，不以可在手机浏览网页替代原生App |
| O36 | 插件安装/启停/重载/卸载、ZIP/URL、插件UI与工具 | 固定实现/API；E2/E7 | 静态内置运维插件，缺通用包生命周期 | M7 Manifest/SDK/隔离/兼容/权限/升级回滚：完整用户路径，第三方代码不默认在Gateway主进程运行 |
| O37 | 插件市场发现与安装 | README仍规划；b1发布与当前in-tree市场代码；E4/E8 | M7原目标为私有目录，无公共生态承诺 | M7 企业目录先验；额外公共发现分发纳入全集、单独容量/运营门；当前Octop是仓库目录，不能推定已有完整远程市场 |
| O38 | Shell守卫、HITL审批、PII处理、权限和配额配置 | README/API/安全实现；E1/E2/E7 | RBAC/Terminal/Guardrail基础；M1试点尚未正式退出 | M1→后续逐工具纳管：读/写风险、确定性Decision、审批期限、撤权与关键Audit故障拒绝副作用；不从宣传推定安全等价 |
| O39 | 用量、Token配额、指标、Audit、轨迹及Langfuse配置 | API/observability实现；E2/E8 | 用量/审计视图已有；统一评测待M3 | M2运行观测、M3质量/成本，配套Langfuse：租户过滤、关联ID和脱敏；Trace不替代Audit/Run事实 |
| O40 | 备份/恢复、升级/重启、系统服务、TLS自动签发/续期、健康、i18n/偏好 | CLI/API/CHANGELOG；E2–E4 | 有Docker、迁移及多语言；完整等价运维路径待验 | 贯穿各阶段的交付配套：备份恢复/升级回退、当前多服务健康；TLS优先成熟反代组件，保留等价用户体验 |
| O41 | Octop↔Octop Bridge、多节点远程专家、聊天/工作区代理 | b5已发布；Bridge文档；E4/E9 | 原采纳计划未覆盖新增桥接 | M3远程Adapter预研，凭据依赖Secret边界；配套远程执行：源/目标身份、请求取消、断线、限流与审计；不把HTTP隧道等同C2 Federation |
| O42 | 内置产品助手、自然语言操作管理界面/生成插件 | b5产品问答已发布；全控制面官方规划；E1/E4 | 无本次已验收全控制面操作闭环 | 各阶段仅暴露其已治理API；读路径先行，写入复用审批；M4专家、M5通道/任务、M6知识、M7插件开发逐步覆盖 |

O01–O42 覆盖当前公开主要能力表面；同组包含的子能力必须逐项验收。目录类能力如专家、子Agent、连接器及插件应在立项时从固定上游目录生成条目清单，记录版本、权限、依赖、等价实现和缺失原因；不能用“框架已有”代替所有目录内容已具备。本次没有对庞大内置库逐个运行，也不宣称所有专家内容已经复刻。

## 4. Octop 后续规划与 PrismOS 原规划的逐项一致性

以下严格区分官方路线状态与实现范围。官方路线更新PR [#1212](https://github.com/TencentCloud/Octop/pull/1212)于2026-09-27合并，解释了2026-09-24调研之后的清单扩展；未来日期未在本次读取资料中确认。

| ID | 官方未来方向/状态 | 代码或发布证据补充 | 与原PrismOS的关系 | 完整覆盖的增量落点 |
| --- | --- | --- | --- | --- |
| F01 | 共享资源池：已完成 | Skill/子Agent共享池；O07/O08 | M4版本引用、M7私有分发方向一致，租户边界更严格 | 复用原阶段；补全创建专家时取用/来源/撤回/复制权限 |
| F02 | 专家共享：已完成 | O05；普通共享专家可成为Team成员 | 与Agent资产和企业复用一致，当前PrismOS不等价已交付 | M4资产权限、M7分发；共享使用不自动共享全部会话与凭据 |
| F03 | PC客户端：已完成 | 跨平台制品存在；O34 | 符合白皮书体验层，批准路线未承诺原生客户端 | 明确客户端配套工作包，不替换Web/CLI或新增Runtime |
| F04 | AgentTeams：进行中/Beta | 有主持人派工、成员/IM回传；E5 | 协作目标一致；自主协调与确定性Workflow语义不同 | M4成员/版本、M5治理编排；自主派工也是有权限/预算/失败状态的Action |
| F05 | 原生移动客户端：内测 | PWA/Remote Phone不证明原生App完成 | 体验层一致；具体产品新增 | 与O35同一客户端包，保留原生App独立验收 |
| F06 | 浏览器与终端补全：规划中 | 浏览器录制/回放/技能草稿接口已有；完整体验未运行验证 | 原有Skill/Terminal/Sandbox基础可复用；通用RPA仍非目标 | O29–O33配套，复用M3契约、M4版本、M5执行与M7分发 |
| F07 | 自进化：规划中 | 本次未确认“日常对话自动沉淀→评价→正式发布”全链；录制/摘要不等价 | M3 Evaluation、M4Version提供条件，但自动学习产品未被原路线承诺 | 增量技能候选管线：来源/授权→草稿→评测→审阅→发布→回滚；不能自动改变生产权限/Policy |
| F08 | Managed Agents：规划中 | CRUD/本机start-stop不证明平台开通、弹性与代运维已交付 | M2运行、M4Deployment是基础；托管服务与弹性运维新增 | 增量托管Provider：开通、隔离、配额、扩缩容、暂停、销毁、观测；部署资产与服务托管分责 |
| F09 | Project：规划中 | 工作区、团队房间与Project一等资源并不等价 | 白皮书§8.2Workspace与M2执行/M4资产/M6数据目标相交；Project聚合未单独冻结 | M2关联视图可预研；正式Project拥有稳定资源引用、成员ACL和生命周期，完整切片依赖M4/M6 |
| F10 | 云边端一体：规划中 | b5 Bridge已可远程专家聊天；文档明确跨实例ask_agent/Team不在该桥范围 | 分布式部署可复用；任务选择/路由/离线/驻留和配额新增；不必自研Runtime | 先受控remoteAdapter/Bridge等价，再冻结本地/远程执行路由、数据驻留、费用和失联语义；跨独立组织才评估C2 |
| F11 | 插件市场：规划中 | b1与当前代码有in-tree发现/安装；远程公共目录不等价已完成 | M7私有目录一致；公共生态超出原默认范围 | 私有目录、公共发现分发分别验收；公共渠道也须走M7签名/权限/兼容/回滚，交易分成不因“市场”名称自动引入 |
| F12 | 对话式控制面：规划中 | 内置产品问答不等价管理所有资源；O42 | 与统一治理和控制面API一致；覆盖所有管理入口是新增体验范围 | 对现有API做受治理管理Action，分别覆盖专家、通道、知识库和插件；模型不能绕过PDP直接写DB |

**一致性判定：** F01/F02以及F04/F06/F12的基础目标明显一致；F09有长期战略基础但需新增聚合契约；F03/F05/F07/F08/F10/F11含新增产品、运维或生态范围。上述是架构和范围分析，没有计算无统一权重的“相似度百分比”。

## 5. 保留原路线的交付组织

### 5.1 平台主线及原门禁

| 原阶段 | 保留的目标 | Octop能力在这一阶段的合法接入 | 不得据此提前宣布 |
| --- | --- | --- | --- |
| M1（原窗口2026.08–11） | 最小AIOps治理、Policy/Approval/Audit、只读/副作用与故障门 | 有界首次执行体验与身份预研；工单SecretRef是既有Secret不变量的收口 | 全工具纳管、持久Run、通用调度或M1退出 |
| M2（2026.12–2027.03） | Task/Run/Attempt/Action生命周期与恢复、取消、幂等 | Web/API/CLI/已有IM统一入口、历史/通知/结果投影 | 通用Schedule、完整Team/Workflow或全部客户端已完成 |
| M3（2027.04–07） | Runtime Adapter、Evaluation、AIOps+企业研究两场景 | 来源、成本、轨迹与受控工具适配；客户端/设备协议开始具备可靠依赖 | 已替换Runtime、AgentVersion/完整Connector完成 |
| M4（候选2027.08–11） | 不可变AgentVersion、Deployment、评价后发布与回滚 | 专家/人格/Team成员配置、共享资源引用；客户端/ACP/Project依赖开始落定 | 通用包市场、自动自进化生产发布或弹性托管完成 |
| M5（候选2027.12–2028.03） | 最小版本化DAG及等待恢复、Event/Schedule入口 | Team多步协作、cron、主动推送、录制回放与结果投递 | 另建调度/团队第二执行状态机、通用RPA |
| M6（候选2028.04–07） | Connector/Secret/Knowledge、ACL/来源、两个参考Connector | 连接器/知识完整治理，记忆/Project数据关联；其余目录按需逐项跟进 | 两个参考即覆盖全部连接器；托管/云边所有安全问题自动解决 |
| M7（候选2028.08–11） | 扩展包、SDK、签名/权限、企业私有目录和回滚 | Skill/专家/插件分发，技能候选发布，自进化的供应链边界 | 公共生态已通过企业目录退出门、全部扩展已运行验收 |

M4–M7原启动条件保持：上一阶段证据、真实重复需求、Owner/容量、迁移/停止条件。M6仍需两个不同参考Connector；M7仍需至少三类真实扩展由不同边界独立维护。Runtime Independence和Federation继续按C1/C2硬证据触发。

### 5.2 完整覆盖所需的配套工作包

这些是用户完整覆盖目标的显式工作，不作为可忽略的“建议看看”。只有在依赖就绪且形成独立Spec/Owner/预算后进入交付；不承诺在原主线不增资源的情况下同步完成。

| 工作包 | 对应全集 | 前置依赖 | 完整完成的用户路径与证据 |
| --- | --- | --- | --- |
| D1 交付和多端入口 | O01/O10–O12/O34/O35/O40，F03/F05 | 可信身份、稳定运行/审批API；发布/恢复门 | Web、CLI、各IM、Windows/macOS/Linux、PWA、原生移动、NAS分别完成安装/登录/任务/审批/恢复/升级回退 |
| D2 多模态与模型体验 | O15–O18 | 既有Provider；M3Tool/Artifact/错误/成本契约 | 本地模型发现下载、语音转写/播报、图片/视频生成与结果预览；取消/失败/配额清楚 |
| D3 浏览器、终端及设备 | O29–O33，F06 | M3Adapter/隔离/纳管动作；M5多步骤与恢复 | Terminal/Browser/Desktop/Phone分别可连接、授权、操作、停止/撤销、审计；录制→草稿→受控回放有证据 |
| D4 专家与协作资源 | O04–O09/O19/O27/O28 | M4版本与成员授权、M5协作执行、M7包分发 | 专家库/人格/共享池/Teams/ACP所有权与使用路径完整；不丢现有PrismOS能力 |
| D5 技能自进化 | O31/F07 | M3Evaluation、M4版本/审批、M7分发及数据权限 | 对话或录制产生可追溯草稿→测试→审阅→发布→回滚；用户可停用/删除，生产权限不由模型提升 |
| D6 托管与Project | F08/F09 | M2运行/M4Deployment；完整数据依赖M6；另需基础设施与运维容量 | Project组织Agent/文件/会话/任务；托管完成开通、容量、隔离、停用、销毁、故障和运维闭环 |
| D7 远程桥接与云边端 | O41/F10 | 远程Runtime契约、Secret范围、运行幂等和驻留策略 | 远程专家等价桥接先行；显式选择/调度本地或云端、取消/断线/未知提交、预算和数据边界可验证 |
| D8 全控制面与公共发现分发 | O37/O42，F11/F12 | 对应资源管理API已纳管；M7供应链；公共运营容量另计 | 自然语言管理专家/渠道/知识/插件；发现→审核→安装→更新→回滚完整，公共与私有目录分别验收 |

上表依赖表示“该能力达到完整产品等价的最晚必要条件”，不是要求所有工作包同时启动。框架和协议可预研、界面可做只读切片，但不绕过正式发布门。现有1–2人主线容量不能直接加总这些产品范围；在每包Spec中记录开发/回归/跨平台维护/运营容量、Owner及尾部交付窗口。增加人力提高有界配套吞吐，不能跳过平台依赖。

## 6. 保留PrismOS独有规划的反向检查

| 原能力/原则 | 本次保留方式 | Octop对标不能替代的证据 |
| --- | --- | --- |
| 企业Tenant、Membership、RBAC、平台/租户/用户scope | 所有入口和共享对象贯穿tenant与actor，保留现有Slack/K8s等能力 | 实例级owner/shared或管理员可见不等于租户隔离 |
| Resource/Identity/ExecutionEnvelope | 继续使用既有app.platform契约和稳定关联，新增对象通过Ref接入 | 会话键、聊天消息或Bridge ID不等于平台Resource契约 |
| 决策/审批/审计先于副作用 | 新终端/设备/插件/Connector/ACP/管理Action逐项纳管 | 有HITL按钮、warn规则或“更安全”不能替代执行门 |
| Task/Run/Attempt/Action事实来源 | M2统一持久生命周期，UI、cron和Team均为适配或投影 | 单进程可恢复、checkpoint和聊天历史不等价业务状态机 |
| 不可变资产、评价后晋级、回滚 | M3评价、M4版本、M7供应链顺序保留 | 专家配置CRUD、人格模板和可安装插件不等价受控版本 |
| 双Golden Scenario、AIOps解耦 | M3仍验证AIOps与企业研究共用内核，禁用AIOps后核心可用 | 更丰富的聊天产品无法证明跨领域内核复用 |
| 兼容和渐进迁移 | 保留DeerFlow/LangGraph、已有API/DB历史和PRISMOS品牌迁移既有窗口 | 换到Octop单进程或直接移植不构成兼容方案 |
| 数据/Secret边界 | M1有界修复；M6通用Secret/Knowledge治理，不把明文回退当安全完成 | 本地保存、加密字段或OAuth存在不等于全过程不泄密 |
| Runtime中立与条件投资 | 保留Adapter，C1有实证才替换，C2有独立组织需求才联邦 | OctopBridge不是完整Federation；云边端不强制自研Runtime |
| 四道基本门、M3Evaluation门、专项Security门 | 每个新增产品包有成功/拒绝/恢复/故障/升级回退证据 | 功能清单覆盖率和路由数量不等价生产就绪 |

## 7. 全量验收与差距记录规则

每个O/F编号及其子能力维护以下字段：目标版本、PrismOS现状（已有/部分/未验/待实施）、上游文档/代码/发布状态、目标用户路径、资源/身份/权限、依赖阶段、Owner、容量、迁移/开关/回退、测试及真实部署证据、缺口和下一步。无Owner或只有设计，状态保持“待实施”；没有运行证据不能写“完整等价”。

至少准备九组对标场景，既验证Octop体验，也验证PrismOS治理：

1. 安装和配置模型→创建专家→Web/CLI/IM发起任务→重载后结果/身份一致。
2. 定时任务与主动推送→时区/重复/重启→仅一次受控副作用→投递失败重试不重做业务。
3. 多Agent/Team→并行成员→人工审批/取消→父子执行和成果可追踪。
4. 私有知识上传/索引→带来源研究报告→撤权/删文档→后续检索无越权结果。
5. Connector OAuth/APIKey授权→工具调用→令牌续期/撤销→Secret不进普通API/日志/Prompt。
6. Browser/Terminal/Desktop/Phone→授权操作→录制/回放→断线/拒绝/撤销后动作不继续。
7. Skill/专家/插件发现→安装→启停→权限变更→升级失败回滚；公共/私有分别记录。
8. Desktop/PWA/原生Mobile/NAS→登录和任务→审批→后台/断线恢复→升级/卸载；语音/图像/视频与文本进入同一执行链。
9. Project/托管/远程执行→成员权限/版本→云边选择→失联/未知提交→自进化草稿评价后发布→对话式管理留Decision/Audit。

完整目标达成需要：O01–O42全部子能力及F01–F12目标都有实现或经用户明确调整的范围，有成功/拒绝/恢复/故障证据，原路线不变量通过，跨端制品和运维验收通过。仅做本次矩阵、拥有一个Adapter、满足原M6两个Connector或通过M7私有目录，均不足以宣布完整Octop产品能力已交付。

## 8. 当前行动与晋级判断

1. 本次先修正文档范围与外部状态，保留原批准路线文件；不扩建运行时或新增未经阶段设计的核心表/API。
2. 继续现有M1收口：严格加密/持久工单SecretRef、旧明文配置迁移、Provider最小注入及真实模型/webhook/目标数据库演练。当前工作区相关未提交代码不算验收，仍以[M1门禁记录](./2026-09-25-m1-exit-gate-evidence.md)裁定退出。
3. M1通过后按原计划进入M2；冻结统一入口/执行生命周期时同步检查O10–O12，形成后续客户端复用契约。通用Schedule仍在M5，不移到M2。
4. 为D1–D8分别形成受原门约束的产品范围和容量记录；先拆最短纵向路径，再补全部子能力。不要把新完整产品目标误写为“1–2人原日历自动可达”。
5. 每次启动下一包时复核上游固定提交、发布与路线状态，更新差距；本次只做一次调查，没有创建周期监控。

## 9. 固定证据索引

### 9.1 官方产品、接口与发布

- E1：[英文README](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/README.md)、[中文README](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/README_CN.md)。用于产品表面和12项官方路线状态。
- E2：[API](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/docs/api.md)、[用户手册](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/docs/user-guide.md)。用于模型、语音、身份、工作区、知识、用量、运维等接口表面；部分新路由以代码为补充。
- E3：[CLI](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/docs/cli.md)、[架构](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/docs/architecture.md)。用于入口、会话、cron与运行边界。
- E4：[CHANGELOG](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/CHANGELOG.md)、[b6发布](https://github.com/TencentCloud/Octop/releases/tag/v1.0.2b6)、[b5发布](https://github.com/TencentCloud/Octop/releases/tag/v1.0.2b5)、[b1发布](https://github.com/TencentCloud/Octop/releases/tag/v1.0.2b1)。用于LDAP/邮件、Bridge/问答助手、市场/模式等实际发布声明。
- E5：[专家团队](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/docs/expert-teams.md)。主持人只调度、共享专家可派工、停止主持人不等于停止成员、第一版团队不共享等限制应保留在等价设计审查中。
- E6：[ACP](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/docs/acp.md)。入站/出站分别设计和验收。

### 9.2 代码与状态差异证据

- E7：[infra实现](https://github.com/TencentCloud/Octop/tree/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/src/octop/infra)、[固定路由树](https://github.com/TencentCloud/Octop/tree/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/src/octop/api/routers)。完整路径盘点用于补充README/API遗漏，不能作为运行合格证明。
- E8：[插件市场](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/src/octop/api/routers/plugins.py)、[浏览器录制](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/src/octop/api/routers/browser/record_replay.py)、[主动推送](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/src/octop/api/routers/proactive_care.py)、[手机设备](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/src/octop/api/routers/mobile/status.py)、[角色模板](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/src/octop/api/routers/user_roles.py)、[Langfuse](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/src/octop/api/routers/observability.py)。本次直接阅读这些代码；插件市场实现明确为in-tree目录，浏览器API生成的是Skill草稿。
- E9：[Bridge设计](https://github.com/TencentCloud/Octop/blob/0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda/docs/bridge.md)。本地浏览器只访问本机、执行在专家所属侧、通用HTTP隧道、跨实例Team/ask_agent非目标；不能替代云边调度或完整Federation。

对公开Issue/PR补查没有得到可核验的Managed Agents、自进化或Project正式交付排期，因此不推断日期。社区诉求、未合并PR或搜索无结果也不能证明官方承诺或能力不存在；明确未来方向以固定README为准，已交付范围以固定代码与release分别确认。

### 9.3 路由模块覆盖盘点

以下是固定提交的77个非初始化Python模块与能力编号的映射。包含序列化/模型/store辅助模块；不是77个独立接口或77项已运行测试。原生客户端源码/制品与配套运行库由E1/E4补充，不能仅从服务端路由推断完整能力。

| 模块组 | 对应能力 | `src/octop/api/routers/`下路径 |
| --- | --- | --- |
| 身份与初始化 | O01–O03 | `setup.py`、`auth.py`、`auth_oidc.py`、`auth_oauth.py`、`auth_ldap.py`、`users.py`、`user_roles.py`、`invites.py` |
| 专家/团队/人格 | O04–O09 | `agents.py`、`experts.py`、`teams.py`、`mbti.py`、`subagents.py` |
| 工具与技能 | O07/O08/O26 | `agent_tools.py`、`skills.py`、`skill_packages.py`、`internal_mcp.py` |
| 会话与投影 | O10/O11 | `chat/history.py`、`chat/models.py`、`chat/notify_ws.py`、`chat/routes.py`、`chat/serialize.py`、`chat/sse.py`、`chat/trajectory.py`、`chat/turn.py`、`chat/ws.py`、`slash.py` |
| 通道及主动执行 | O12–O14 | `channels.py`、`cron.py`、`proactive_care.py` |
| 模型/多模态 | O15–O18 | `providers.py`、`media_generation.py`、`ollama_models.py`、`ollama_download_store.py`、`onnx_models.py`、`voice.py` |
| 记忆/知识 | O19/O20 | `memory.py`、`memory_portable.py`、`knowledge_bases.py` |
| 文件/存储/环境 | O21–O23 | `workspace.py`、`agent_files.py`、`filesystem.py`、`search.py`、`uploads.py`、`storage_backends.py`、`envs.py` |
| 集成协议 | O24/O25/O27/O28 | `connectors.py`、`acp.py` |
| 浏览器与终端 | O29–O31 | `terminal.py`、`browser/env.py`、`browser/harness.py`、`browser/record_replay.py`、`browser/stream.py`、`browser/uninstall.py` |
| 桌面设备 | O32 | `desktop/install.py`、`desktop/settings.py`、`desktop/status.py`、`desktop/stream.py`、`desktop/uninstall.py` |
| 手机设备 | O33 | `mobile/install.py`、`mobile/shell_ws.py`、`mobile/status.py`、`mobile/stream.py` |
| 插件 | O36/O37 | `plugins.py` |
| 安全/观测/用量 | O38/O39 | `security.py`、`observability.py`、`usage.py`、`admin.py` |
| 运维及体验设置 | O01/O34/O35/O40 | `backup.py`、`update.py`、`update_store.py`、`tls.py`、`health.py`、`i18n.py`、`preferences.py`、`settings.py` |
| 桥接 | O41 | `bridge.py` |
