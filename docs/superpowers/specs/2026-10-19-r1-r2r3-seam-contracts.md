# R2/R3 模块接缝契约草案（R1-B2）

**日期：** 2026-10-19
**状态：** 草案。R2/R3 编码的输入契约，不是已实现声明；冻结发生在各轮立项 Spec 中。
**依据：** [R0–R1 实施方案](../../superpowers/plans/2026-10-17-octop-r0-r1-implementation-plan.md) R1-B2；[R0-B 上游基线](../../../integrations/octop/2026-10-18-r0b-upstream-baseline.md) §4 模块映射；上游 b6 固定提交源码抽查
**上游证据：** `infra/knowledge/service.py`（owner/shared 可见性）、`infra/cron/manager.py`（进程内 APScheduler + RepoBundle）、`infra/connectors/service.py`（实例级凭据）

## 1. 五接缝总表（B 类迁入逐模块适配）

| 接缝 | PrismOS 侧承担者 | 通用不变量 |
| --- | --- | --- |
| 身份与资源 | `app.platform.contracts` IdentityRef/ResourceMetadata + Gateway 认证 | 上游 user/owner/shared → tenant/actor/scope；分享、复制、编辑、撤回分开授权 |
| 数据和文件 | SQLModel + Alembic 单链 + Storage Provider | 不引入第二套迁移链或 Repository 事务语义；同租户过滤贯穿缓存与后台任务 |
| 执行与恢复 | `RunFact` + M2 Run 生命周期（R1 先以事实记录） | Cron/Team/每次检索产生的执行都关联 run；重启、断线、unknown 有确定语义 |
| 凭据与副作用 | `SecretRef`（M1 工单专用）→ 通用 Secret Provider（M6） | 每个实际工具动作经 Policy/Approval/Audit；凭据不入日志/Prompt/普通 API |
| 客户端与协议 | Gateway API + v1 客户端契约 | 同一会话/租户；SSE/WS、附件、审批、重连复用既有入口 |

## 2. Knowledge（R2 主力，O20/O21/O23）

**上游事实：** `KnowledgeService` 以 `owner_user_id: int`（实例级整数 ID）+ `shared: bool`（实例级共享）做可见性；`list_visible(actor_user_id)` 返回 owner 或 shared。

**接缝适配（R2 立项时冻结为 Spec）：**
- 可见性模型：`owner_user_id` → `(tenant_id, user_id)`；`shared` → 租户内共享 + 显式成员 ACL（不继承实例级全局共享）
- Document/Chunk/IndexVersion 表全部带 tenant/owner；检索前后校验权限（隔离先于检索不变量）
- 索引任务：上游 `jobs.py` 的中断恢复保留；后台任务上下文必须携带 tenant 过滤
- 引用：`citations.py` 的引用锚点保留；引用指向"当前有权读取的版本"（撤权后引用失效）
- Secret 接缝：向量/嵌入服务凭据走 SecretRef 扩展的通用用途（M6 前先用环境配置，不提前泛化）

**预授权走向：** 上游 Repository 层重写为 SQLModel（数据接缝），Service 逻辑保留。

## 3. Cron / 主动推送（R3 主力，O13/O14）

**上游事实：** `CronManager` 是进程内单例：APScheduler + RepoBundle + Gateway 装配；`CronDeliveryService` 在会话锁内执行并投影历史。

**接缝适配（R3 立项时冻结）：**
- 调度器保留单实例（M2 幂等语义 + 单调度者约束，采纳计划 §6 不变量 4）；部署为独立能力 Worker 进程，不进 Gateway 主进程（依赖冲突预授权规则）
- 触发 → 创建 Run（R1 事实 → M2 完整状态机）：Occurrence 幂等键、重启后状态可解释
- 会话映射：上游 session_key → `SessionBinding`（tenant + channel + external conversation ↔ 内部 thread）
- 投递：`DeliveryAttempt`（destination、Run 引用、状态、重试、provider message ID）；投递失败重试不重执行业务
- 主动推送（O14）复用 cron 骨架；用户配置、暂停、频率窗入租户数据

**预授权走向：** 调度与锁逻辑保留，身份/会话/Run/投递接缝全部替换。

## 4. Team / 通道（R3，O09/O12）

- Team 服务依赖 RepoBundle + 作业追踪 → 每次派工创建子 Run（父子关联、预算、取消）；上游"主持人只调度、停止主持人不等于停止成员"的语义保留并在验收清单
- 通道：`octop-gateway` 包的通道处理保留协议逻辑；身份接缝走 M1 已验证的"入口不决定租户"不变量（签名/token 验证 → 管理员配置的通道绑定映射 tenant/user）
- PrismOS 保留 Slack 通道（既有能力不回退），新增通道逐项适配

## 5. 依赖冲突预授权预判（承接 R0-B §3）

- `langchain` 1.x 全家桶（Knowledge 嵌入链可能引入）→ **隔离能力 Worker** 首选
- `fastapi` 0.138 vs ≥0.141（Cron API 面）→ 先实测兼容，不通融则 Worker
- APScheduler：无版本冲突预期，但进程模型（独立 Worker）已定

## 6. R2/R3 启动门（沿用排期修订）

- R2 启动：R1 退出证据（试用闭环演示 + Run 事实重启不丢）+ 本草案冻结为 Spec
- R3 启动：R2 退出（知识撤权反例 + 双场景评价）+ M2 Run 幂等语义设计完成
