# N08：通用执行生命周期增量设计

2026-10-12，基线 `fddc307`。状态：设计候选；M1 未退出，未创建/启用 M2 持久模型、迁移、Worker 或写入 API。承接 [原 M2/M3 路线](2026-08-08-prismos-capability-roadmap-design.md)、[N01–N15](../plans/2026-10-09-octop-next-iterations.md)、[N07 证据](../evidence/2026-10-12-octop-n07-reproducibility/README.md)。本设计冻结 N08 必需接缝；M3 质量、M4 发布、M5 DAG、M6 数据/通用 Secret、M7 供应链与 C1/C2 原门继续单独退出。

## 1. 现状与启动条件

现有 ExecutionEnvelope 是 M1 稳定关联标识，ThreadBinding/ExecutionCapability 是服务端身份与单次执行能力，均不是持久 Run 生命周期。Gateway 代理具备线程所有权、Agent 固定和身份清洗；宿主 Runtime 回调仍读取可变 CustomAgent。N07 验证了真实认证、线程创建/状态及数据库恢复，没有调用真实模型和受控工单，也没有证明 Run 恢复/取消。

锁定 SDK 0.4.2 的 create/stream/wait 支持 command、metadata、config/context，create 签名没有 run_id；cancel 有 wait 与 interrupt/rollback，get/list 与 Thread get_state 可查询。任意活跃 pause RPC 未发现。签名不是真实取消/恢复能力证明，`if_not_exists` 不作为 Run 业务幂等证据。N07 的 PostgreSQL checkpointer 明确缺少 adelete_for_runs/aprune；未知 dispatch、取消回退和修剪不得假定成功。见 [能力发现](../evidence/2026-10-12-octop-n08-design/runtime-discovery.json)。

实施前必须同时具备：N04 原五道门的 M1 退出记录；本增量 Spec/ADR/状态与兼容审查；唯一 Alembic 当前 head 的备份/演练；SQLite/PostgreSQL 并发与故障验证环境；可用模型及可核对外部事实的接收端。没有环境期间只能推进设计与不写入生命周期的资源声明/预检。

## 2. 事实对象和边界

| 对象 | 必需事实 / 所有权 |
| --- | --- |
| Task | tenant、发起 actor/workload、意图类型、受 ACL 保护 InputRef、请求键范围、创建时间；领域参数作为有界 payload/ref，内核不强制 alert/incident/host/command |
| Run | 唯一服务端 ID、task_id、入口幂等键、不可变 ExecutionSnapshotRef、状态/版本、有效 deadline、预算、当前 attempt、取消意图、终态/不确定证据 |
| Attempt | run_id、递增 ordinal、重试/恢复原因、worker lease/fencing generation、起止时间、运行观察及错误；重试创建新 Attempt，历史不覆盖 |
| RuntimeSegment | attempt 内一段已派发执行，adapter、thread/run/checkpoint opaque refs、dispatch nonce 与观察游标；审批恢复可能创建新 Native Run，不能冒充同一个 Native ID |
| Action | attempt、已评估 Policy/Approval/Audit refs、目的/目标/业务幂等键、M1 SubmissionRef、结果/unknown；外部提交事实仍由已有 M1 Provider 边界记录 |
| Event | tenant/run/attempt、单调 sequence、event_id、command_id/source cursor、UTC、schema、类型与有界引用；附加事实不可覆盖；消息 token 不是副作用或终态事实 |
| Snapshot | tenant-owned Agent 配置、有效 base/persona prompt digest、公开模型配置、Skill/MCP/资源内容引用与 digest、Policy/Definition refs、公开预算/环境；禁止保存解密凭据、认证头、会话 token、MCP env 明文 |

所有关系以 tenant+ID 查询/约束；global 目录的 commit/member digest 是来源证据，不能充当跨租户的授权 DefinitionRef。复制后形成租户自己的资源，源目录不会携带私有会话或凭据。

平台 ID 与 Native Run ID 分开。一个 Attempt 可以有多个审批恢复 Segment；Segment 切换保留同一 Run/Snapshot/Action 关联。旧 M1 task/run 字符串保留为历史关联，不回填虚构状态或自动建立生命周期外键。

## 3. 快照与当前授权

启动事务固定服务端 actor/workload、Agent、公开模型目的/endpoint/config、最终 prompt、选择的资源内容版本和来源。运行中编辑 Agent 不改变已有 Snapshot。业务输入/输出通过受 ACL 保护的 InputRef/ArtifactRef；事件不复制消息正文或凭据。

模型/MCP 继续通过现有、租户有权访问的配置 Provider 解析材料，Snapshot 只持有可核对的配置/凭据引用；不得把 ticket.create 专用 Secret 仓库扩展为任意目的。目的、目标和公开配置必须与快照一致，材料在 Provider 局部变量即时注入。Provider 不能提供这些约束时启动明确失败，先补接缝。通用 Secret/OAuth 仍属 N10/M6。

每次派发、恢复、重试、工具提交与 Artifact 读取重新核验当前成员/资源/目的权限、禁用与撤回；快照和旧批准不是永久授权。轮换、禁用、撤权、旧批准依然执行 M1 规则。角色变化不能改写历史 actor，却可以阻止未来步骤。

## 4. 状态与 Command

主状态：Created / Queued / Running / Waiting / Succeeded / Failed / Cancelled / TimedOut / Unknown / Orphaned。Unknown/Orphaned 是必须检索、对账和人工处置的不确定状态，不能按成功或可重试的失败处理。

| Command / 观察 | 前置状态与必要证据 | 转换与原子事实 |
| --- | --- | --- |
| Submit | 已认证租户/actor，有权 Agent 与完整快照；唯一范围键 | Created→Queued，Task/Run/Snapshot/Attempt/提交 Event/dispatch outbox 同事务；重复相同请求返回同一 Run，异 payload 同键冲突 |
| DispatchAck | 有效 lease/fence，Native 身份确认 | Queued→Running，记录 Segment refs 与观察 Event；未确认不能宣称已运行 |
| Wait | 明确审批/interrupt/资源/人工等待原因与 checkpoint | Running→Waiting，持久 wait reason/ApprovalRef；不是进程内 future |
| Resume | Waiting，当前 ACL/Policy/批准/资源有效，匹配版本与 checkpoint | Waiting→Running，恢复 command 去重，创建恢复 Segment；逻辑 Attempt 不由 Native 新 Run ID 擅自重编号 |
| Complete / Fail | 当前 Segment/Attempt 的有序观察，必需 Audit 与 Action 结果可核对 | 产生终态 Event 后投影 Succeeded/Failed；模型文本和 HTTP 200 不证明外发成功，Action 拒绝/部分结果必须显式展示 |
| Retry | Failed/已对账 TimedOut，预算有界，旧副作用安全、当前授权有效 | 新 Attempt、递增 ordinal；复用业务 Action 幂等/提交记录，不能复制旧批准盲重发 |
| Cancel | 非终态，当前授权与版本匹配 | 先持久 cancel_requested Command/Event，再协作式下传；只有执行已停止且副作用事实确定才转 Cancelled；请求已接收不代表已取消 |
| Deadline | 有效 deadline 超时 | 持久取消/超时意图；确认停止后 TimedOut，无法确定外部事实则 Unknown；不自动 retry |
| LeaseLost / DispatchUncertain | 无法确认 Runtime 或外部提交事实 | Unknown/Orphaned，并附 observation gap/证据；旧 worker fence 失效，迟到事件不得覆盖新 generation |
| Reconcile | 权限明确，Native checkpoint/Action Submission/外部事实支持结论 | 持久 resolution Event 后合法终态/恢复；“未发现”与聊天文本不构成重发许可；人工说明有 actor/Audit |

终态不由 update row 或 UI toggle 改写；状态只由 Repository Command/Transition 提交。并发 resume/cancel 使用 expected_version/CAS 与 command_id 去重，取消意图一旦提交不得开启新的恢复派发。已经不能撤销的外部结果保持 committed，并展示 cancelled-after-effect，而非伪造撤销。

Task 的业务结果与 Runtime 技术完成分开显示：平台 Event/Action 事实决定投影，不能仅从 Native success 推断用户目标/受控副作用完成。领域结果通过受控结果引用扩展，不要求内核识别具体工单字段。

## 5. 幂等、事务与恢复

入口键范围至少 tenant+actor/workload+operation+intent target；Canonical payload/Snapshot 的请求指纹固定规则，键不可复用到不同意图。唯一约束由数据库保证，不能依赖进程字典。重试/恢复 Command、外部 Action 业务键与投递键各自明确，不混成一个全局键。

核心事务保存事实与 outbox，Worker 在 commit 后领 lease；网络调用不放进长期数据库事务。Native create 没有已验证的客户端 Run 幂等能力：dispatch 请求送达后丢 ACK 时转 Unknown，按 thread/metadata/已记录 Segment 查询；未取得“未执行”的可靠事实不再次 start。跨 Worker 通过持久 lease/fence 抑制旧派发与迟到状态。外部 exactly-once 不作为承诺，保证去重、unknown 保留与可核对提交事实。

Event 采用每 Run sequence、command/source-cursor 去重。没有稳定 Native event id/cursor 的流片段不能以内容 hash 去重正常重复 token；它们是受保护消息投影。状态由持久 Commands/Observations 重建，浏览器断开不结束 Run，Last-Event-ID 只在已验证游标模型内重放。重启恢复读 Run/Attempt/lease/checkpoint/Submission，不能从聊天历史猜测。

## 6. Runtime 与兼容

Adapter 的 start/stream/pause/resume/cancel/get_state 输入输出使用平台 DTO 与 opaque refs。上层不 import LangGraph 私有类型。能力必须带 supported/unsupported 与真实证据；pause 只允许已验证 interrupt 场景，不能用 cancel 改名伪装。cancel 不默认用 rollback，缺 adelete_for_runs 时禁止把 Native rollback 当作已清理；没有 aprune 不启用自动历史修剪，保留容量/运维限制。

先将 Web/API 用户发起运行桥接到同一 Command 入口；GET/历史线程继续兼容。老线程按已有 owner metadata 与 ThreadBinding 有界认领，禁止认领无 owner 或其他租户；历史消息标记 legacy_unmanaged，首次新执行建立真实 Snapshot/Run，不编造旧 Attempt。AIOps/Terminal 原路径保持可用，转换到内核时用插件适配；禁用 AIOps 后通用执行不依赖其表或字段。M1 既有 Approval/Audit/Submission 不覆盖或删除。

## 7. 数据与迁移候选

拟新增平台 Task/Run/Snapshot/Attempt/Segment/Event/CommandDedup/Outbox/lease 事实结构，具体字段与约束在 M1 退出后的迁移审查固定；仅接入已有 Alembic 单链，当前 head 仍是 n8h9i0j1k2l3。UTC、JSON 校验、tenant 复合关系、请求/命令唯一键、Run version/CAS、事件序列与待对账索引必须在 SQLite/PostgreSQL 实测。

旧数据不回填虚构终态。新事实保留后，制品回退关闭新入口/Worker并保留只读运营视图，数据库不自动降级；非空表破坏性 downgrade 拒绝。SQLite 与 PostgreSQL 的在线备份/恢复、旧客户端、M1 审批/明文迁移拒绝条件都纳入新 head 演练。

## 8. 必须完成的验证

| 门 | 实际证据 |
| --- | --- |
| Contract | 状态转换全矩阵、租户引用、快照秘密拒绝、Adapter 独立 contract；unsupported 操作明确失败；内核无私有 Runtime/AIOps 强制字段 |
| Golden | Web/API 单入口；AIOps 等待审批/恢复/重复告警；研究任务的相同事实路径；原聊天/Terminal可用，禁用 AIOps 通用执行可用 |
| Quality | 快照固定、Actor/资源撤权、当前 Policy、输入/事件/命令重复；有限 retry；技术完成与真实 Action outcome 分开 |
| Migration | SQLite/PostgreSQL 单 head、备份、重复 apply、重启、旧线程认领、并发 CAS/lease、非空拒绝降级与制品开关回退 |
| Security | 跨租户/无 owner/伪造身份与 capability、资源撤回、秘密不入 API/Prompt/Event/Audit/Snapshot、关键 Audit 故障封闭，真实目标外发计数 |

关键故障注入位置：commit 前后；Native start 前/后但 ACK 丢失；流断开/游标缺失；审批恢复与 cancel 竞争；Provider 请求到达后超时；lease 过期旧 Worker 迟到；进程/数据库重启；checkpoint 部分缺失；撤权/轮换/资源变化；Critical Audit 写入失败。每个结果记录 run/attempt/segment/command/request 与外部核对事实，不能以 mock 替代全部真实路径。
