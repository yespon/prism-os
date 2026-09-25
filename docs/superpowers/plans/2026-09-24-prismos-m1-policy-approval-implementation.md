# PrismOS M1 Policy/Approval 治理链实施计划

**状态：** 执行中；P0 已通过，M1 未通过退出门。
**设计：** [M1 增量 Spec](../specs/2026-09-24-prismos-m1-governed-action-design.md)、[ADR](../../strategy/adr/2026-09-24-m1-governed-action-boundary.md)、[真实调用图](../../strategy/2026-09-24-m1-entry-action-call-map.md)
**依据：** [批准的能力路线](../specs/2026-08-08-prismos-capability-roadmap-design.md)

## 已完成的起点

- P0 九个公开契约、AuditEvent 表与 JSONL dry-run 兼容工具已通过[契约基线门](../../../backend/docs/PLATFORM_CONTRACTS.md)。
- M1 已公开 `ActionContextInput`、`hash_action_context`、`PolicyRequest`、三分支 `PolicyDecision` 与 `Approval` 契约；Decision/Approval 与提交事实已持久化。决策、关键 Audit 与待审批事实同事务提交；内部 Policy、Approval API 与默认关闭的工单 Adapter 已实现；诊断 Agent Tool 已通过服务端签发的 Incident 范围接入。试点开关仍默认关闭，目标部署尚未放量。
- AIOps 诊断 Gateway 已拒绝停用、跨租户 Agent；Lead Agent 已拒绝显式不可用 Agent 的默认回退。浏览器 LangGraph 请求现经 Gateway 代理及一次性能力核验。
- 当前 Golden fixture 的 `terminal.execute` 是 Schema 示例，未证明诊断 Agent 可以调用 SSH Terminal。DB 自定义 Agent 的 `tool_groups` 现已在 MCP 服务器发现前强制过滤；内置/社区工具还需独立治理。

## 顺序和工作包

| 序号 | 交付与修改面 | 验收及故障测试 | 启动依赖 |
| --- | --- | --- | --- |
| 1 | 已选只读 `read_file` 与首个副作用 Agent→AIOps 工单 webhook Adapter。沙箱写入存在 `bash`/`str_replace` 绕过，不能只治理 `write_file`。内部 Adapter 已建立；后续 Agent Tool 必须独占该受控提交入口，并与规则触发的 `auto_ticket` 区分。 | 已新增已认证诊断请求→签发范围→LangGraph 模拟流→Tool/Provider 的可执行集成测试；目标部署的真实模型调用与 webhook 仍待复核。 | 本计划与调用图 |
| 2 | 已实现 MCP 服务器精确选择：DB Agent 空数组保留为空且不加载 MCP，非空选择在 SDK 发现和 OAuth 前按服务器名过滤；缓存按 tenant/user/服务器集合分开，deferred tool_search 只含所选工具。默认 Agent/未指定组仍走旧行为；内置/社区工具不受 MCP 选择约束。 | 空配置、未知服务器、同名前缀服务器、缓存刷新、Agent 传参和内置工具兼容测试通过；旧 DB 空数组失去此前隐式 MCP 权限，需在试点放量前核对现有 Agent。 | 1 |
| 3 | M1 契约已增加 canonical Action context hash 和拒绝敏感键的临时输入 DTO，公开 Policy/Approval 事实模型及五个增量符号；原 P0 九符号保持兼容。首个受控 Action 命名为 `ticket.create`，供内部有界 Adapter 使用。 | 三分支、tenant、UTC、过期、上下文变化、非规范 JSON、敏感键及公开导出测试通过；内部持久服务见工作包 4–8。 | 1–2 |
| 4 | 已新增唯一 Alembic 迁移、Decision/Approval SQLModel 投影、tenant 范围查询、Decision 幂等与 Approval 版本 CAS；Approval 创建须绑定已持久化的 `require_approval` Decision。 | 临时 SQLite 升级/降级/再升级、重复写入、跨租户和并发 approve/reject 测试通过；目标部署数据库及服务重启场景在集成门复核。 | 3 |
| 5 | 已新增 AuditEvent 事务内 append 和 `PolicyFactWriter`：Decision、`action.policy_evaluated` AuditEvent、必要时的 pending Approval 同 session 提交；只返回完成信号，不生成可执行 token。 | 三分支和重复写入通过；Decision、Audit、Approval 写入冲突均回滚，孤立 Decision fail closed；目标数据库并发唯一键竞争仍需在集成门复核。 | 4 |
| 6 | 已实现内部确定性 Policy 服务：按可信配置显式匹配 Action/风险类别，旧 Guardrail/Terminal 结果仅能收紧规则，结果经原子写入单元持久化；尚未接入实际 PEP，因此 Prompt 与旧 `fail_closed=False` 的绕过问题留在受控入口处理。 | 三分支、版本、无配置、Provider 超时/异常、风险类别错误、缺失 actor、重复请求及已批准审批不重开均通过；副作用未配置默认拒绝。 | 3、5 |
| 7 | 已新增 Approval 服务和 Gateway read/approve/reject API：tenant 与审批人取自认证会话，操作时重查租户启用状态、成员角色与原请求者有效身份；内部 consume 在恢复时重查 Decision、context/version、权限与期限，并以 CAS 持久化。pending 由 Policy 服务创建，内部恢复提交已接入工作包 8；可信 Agent Tool 尚未接入。 | 授权、自审批、撤权、停用租户、跨租户、过期、reject、重复审阅、上下文变更与状态冲突测试通过；浏览器身份字段无法覆写会话。实际 Action 恢复/资源授权及部署数据库并发仍待工作包 8/集成门。 | 4–6 |
| 8 | 已新增提交事实表与唯一迁移、本地稳定 idempotency key、`not_submitted→unknown→submitted` CAS，以及默认关闭的 Agent→AIOps 工单内部 Adapter。Adapter 重查租户 Incident、启用的来源配置、请求者权限和 payload/目标摘要；审批恢复先消费，再占位并调用现有 webhook。Provider 可传幂等键，但接收端未承诺去重；超时或结果写入失败保留 unknown，不自动重发。人工工单与规则 `auto_ticket` 仍是独立旧路径。 | 并发占位只有一个成功；allow、deny、审批等待/恢复、撤权、上下文变化、Audit 故障和超时反例通过；真实 Incident→AlertSource 解析及迁移升降级通过。Agent Tool 注册与已认证诊断请求集成测试已在工作包 11 完成；结果审计和兼容双写已在工作包 9 完成。 | 1、5–7 |
| 9 | 已完成当前 `ticket.create` 的兼容投递：提交事实、`action.submitted` 关键 Audit 与无 payload 投递引用同事务落库；再投递 Gateway JSONL 和 IncidentAction。失败保留原事件 ID、目的地、次数和错误类别，可按租户重放及查看计数，不重放外部建单。Provider 超时另记 `action.submission_unknown`，提交状态仍为 unknown。Terminal 当前未纳管，原有 `terminal_audit_logs` 路径保持可读写，不生成虚假的工单命令记录。 | 受控工单的旧时间线仍可读；JSONL 失败不回滚提交事实，重放成功且不重复建单；跨租户重放隔离、Secret 不入 Audit/投递表；迁移升降级及禁用 Adapter 不触发外部调用验证通过。实际 Gateway JSONL 文件锁与目标部署数据库并发仍在集成门复核。 | 5、8 |
| 10 | 已实现浏览器 LangGraph 的 Gateway 代理：会话身份、tenant、Agent 可见性/启用和线程 Agent 由服务端绑定；新线程归属写入独立事实表，旧线程仅在已有 owner 元数据匹配时认领。Run 身份由 Gateway 重写，并可签发数据库一次性能力；LangGraph 严格模式在工具装配前消费能力，裸身份、字段冲突和重放均拒绝。生产与本地 Nginx 均改经 Gateway，SSE 原样透传。严格图上下文开关 `PRISMOS_TRUSTED_GRAPH_CONTEXT` 默认 `off`，M1 放量前须在 Gateway/LangGraph 同时设为 `required` 并做真实部署验证；未认证 IM 身份不签发能力。 | 新线程归属、跨租户/跨用户、停用 Agent、伪造身份和 bootstrap、线程换 Agent、非法 Run 端点、能力过期/重放、SSE、Nginx 路由及迁移升降级测试通过。旧无 owner 元数据且无其他可信归属的线程不自动认领；目标部署的真实流式 Tool/Provider、严格模式下后台调用与回退演练仍在工作包 11 集成门复核。 | 1、7–8 |
| 11 | 已接入诊断 Agent 的 `ticket.create` Tool：一次性图能力仅由服务端诊断请求绑定 Incident，浏览器代理清除伪造范围；Policy、Approval、提交和 Audit 沿既有 Adapter 执行。诊断页从持久化 Decision/Approval/Submission 读取状态，提供管理员审批及请求者恢复。Gateway 与 LangGraph 同步使用默认关闭的单租户、单 Action 开关。 | 已认证诊断请求→模拟 LangGraph 流→Tool/Provider Golden 通过；allow、deny、审批等待/恢复、reject/expire、撤权、Policy/Audit 故障、幂等、跨租户与开关回退有自动化覆盖。真实模型触发、目标数据库及外部 webhook 演练留在工作包 12；未据此宣布 M1 退出。 | 2–10 |
| 12 | 已完成[离线退出门复核](../../strategy/2026-09-25-m1-exit-gate-evidence.md)：Contract、Quality 和隔离 Migration 通过；自动化 Golden 通过；记录全量后端 `1382 passed/18 skipped/0 failed`、前端质量、首次 8 项失败的修复及 PostgreSQL 升降级证据。 | 真实模型/webhook、目标数据库及部署回退未验；内联工单凭据和只读 Action PEP 仍需处理。专项 Security Gate 未通过，M1 不宣布完成，M2 不启动。 | 1–11 |


## 工作包 9 运维核对

- 旧审计投递按 `tenant_id` 查询 `platform_legacy_audit_deliveries`，关注 `pending`/`failed` 数量、`attempts`、`error_category`；投递行只存原平台事件引用，不存 webhook 配置、Header 或响应正文。
- 在 `backend` 目录执行 `uv run python -m scripts.replay_legacy_audit --tenant <tenant-id>` 可重放最多 100 条；可用 `--limit` 调整上限。重放只更新 Gateway JSONL 与 IncidentAction，不再次调用工单 Provider。
- `unknown` 提交状态不能用该命令补发工单，应先人工核对外部 Provider；结果 Audit 写失败时也保持 unknown。当前 Agent Tool 已注册，但单租户 Action 开关默认关闭。


## 工作包 10 放量与回退

- 浏览器请求经 `/api/langgraph/` 进入 Gateway；Gateway 只转发明确列出的 Thread、Run 和只读 Assistant 操作，不把浏览器 Authorization、Cookie 或声称的身份字段交给 LangGraph。新对话由 Gateway 写入 owner 元数据及绑定；已有线程首次访问只在 owner 元数据匹配认证身份时认领，缺少可信归属的历史线程暂不自动认领。
- `PRISMOS_TRUSTED_GRAPH_CONTEXT=required` 必须同时设置在 Gateway 和 LangGraph，且先确认后台 AIOps 诊断运行可以签发凭据；默认 `off` 保持受控 Action 未放量。IM 的外部用户 ID 尚无平台身份映射，严格模式下不获得凭据。
- 回退时先关闭受控 Action 的租户开关，再将严格图上下文开关设为 `off`；若须恢复历史直通代理，回退 Nginx 的 `/api/langgraph/` 路由配置。线程绑定与能力事实保留供审计，不反向改写已执行 Run。

## 工作包 11 试点与回退

- 先完成数据库迁移 `m7g8h9i0j1k2`，在 Gateway 与 LangGraph 同时设置 `PRISMOS_TRUSTED_GRAPH_CONTEXT=required`；确认诊断后台流可签发、消费一次性能力。浏览器 Run 不获得 Incident Action 范围。
- 仅在选定的一个租户设置 `PRISMOS_GOVERNED_TICKET_TENANT=<tenant-id>` 与 `PRISMOS_GOVERNED_TICKET_ACTION=ticket.create`。`PRISMOS_GOVERNED_TICKET_VERDICT` 默认 `deny`，可显式选 `allow` 或 `require_approval`；变更规则时同步设置 `PRISMOS_GOVERNED_TICKET_POLICY_VERSION`。Gateway 和 LangGraph 应使用相同配置。
- 诊断页轮询 `/api/incidents/{id}/governed-ticket`，只显示当前诊断线程的 Decision、Approval、Submission 事实；审批沿既有 `/api/approvals/{id}` 接口，只有原请求者能恢复。`unknown` 需人工核对外部 Provider，不能自动补发。平台 `run_id` 由诊断线程稳定派生，仅作 M1 关联标识；LangGraph 原生 Run 映射留待 M2 生命周期契约。
- 回退时将 `PRISMOS_GOVERNED_TICKET_ACTION=off` 同时下发到 Gateway 和 LangGraph；界面返回原有诊断视图，已落库的 Decision、Approval、Audit 和提交事实保留供追溯。严格图上下文的单独回退步骤见工作包 10。
- 自动化 Golden 使用模拟 LangGraph 流及模拟 webhook Provider；目标部署的真实模型 Tool 调用、真实 webhook、服务重启与回退证据属于工作包 12 的退出门。

## 实施规则

- 每项先添加能失败的测试，修复后跑目标测试、相邻回归和 `scripts/test-platform-contracts.sh`；Schema/迁移由一个 Owner 串行提交。每两周给出可运行演示和失败基线。
- P0 `task_id`/`run_id` 只作关联，不建状态机。Approval 状态不等于 Run 状态；LangGraph checkpoint 不等于审批事实。
- 功能开关默认关闭。关闭后不删除平台审计；新路径的关键决策/审计失败时 fail closed，不能偷偷退回旧副作用路径。
- 不把 `terminal.execute` fixture、独立 Terminal graph 或规则触发 `auto_ticket` 单独计作 AIOps Agent Golden Scenario。真实路径无法验证时维持开关关闭并先补有界 Action Adapter。
