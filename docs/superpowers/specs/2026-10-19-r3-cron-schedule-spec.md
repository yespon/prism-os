# R3 Spec：定时任务、主动推送与多通道（cron 切片）

**日期：** 2026-10-19
**状态：** 已批准（承接 [R1-B2 接缝草案](./2026-10-19-r1-r2r3-seam-contracts.md) §3/§4 冻结为 R3 立项 Spec）
**范围：** O13（cron/date/run-now/时区）、O14（主动推送）的 R3 切片；O12 通道按依赖逐项；O09 Team 按子 Run 模式预研
**上游基线：** Octop b6 `eb280112`：`infra/cron/`（manager/delivery/job/trigger/task_type/tools）
**非目标：** 完整 Workflow DAG（M5/R5）；分布式多实例调度（单调度者约束）；全部 IM 通道（逐项适配）；AgentTeams 完整产品（本轮只做子 Run 关联预研）

## 1. 交付目标：一条可演示闭环

**管理员创建 cron 任务（自然语言或 cron 表达式）→ 到点触发 → 受治理执行（Run fact + Policy 纳管动作）→ 结果投递回通道/会话 → 重启后任务恢复且无重复副作用**

验收场景（对应九组对标场景之 2）：
1. 创建"每分钟检查"任务（date/cron 两种触发各一）→ 触发产生 Run fact（R1 事实模型）
2. 重启 gateway/langgraph/cron Worker → 任务从 DB 恢复调度，不重复执行已完成的 occurrence
3. run-now 立即触发一次，与定时触发共用幂等键去重
4. 触发的执行若含纳管动作（如建单），走 Policy/Approval/Audit 链——审批等待期间 occurrence 挂起，批准后单次提交
5. 投递失败重试不重执行业务（DeliveryAttempt 记录，重试只重投递）
6. 时区正确（Asia/Shanghai 配置）

## 2. 架构（接缝草案 §3 落地）

```text
PrismOS Gateway (API: 任务 CRUD / run-now / 状态查询)
      │ DB（调度定义与 occurrence 事实）
Cron Worker（独立容器/进程，单实例）
  APScheduler（上游调度语义保留）+ CronManager（boot/reload_from_db 恢复）
      │ 触发 → 创建 Run（RunFact + occurrence 幂等键 tenant+job+scheduled_at）
      ▼
LangGraph 执行（经 Gateway 可信入口，与 Web 同一治理链）
      ▼
投递（DeliveryAttempt：目的地/Run 引用/状态/重试次数/provider message ID）
```

**部署边界**：cron Worker 独立容器（依赖冲突预授权规则：APScheduler 与主进程隔离）；**单调度者**——多实例部署前必须有租约机制（采纳计划不变量 4，本轮不做租约）。

## 3. 数据模型（Alembic 单链延伸）

```
ScheduleDefinitionRecord   tenant_id, id, owner_user_id, name, trigger_kind(cron|date|interval),
                           cron_expr / run_at, timezone, agent_name, agent_id, prompt,
                           delivery_channel(web|im), delivery_target, enabled, created_at, updated_at
ScheduleOccurrenceRecord   tenant_id, id, schedule_id, scheduled_at, idempotency_key(tenant+schedule+scheduled_at 唯一),
                           run_id, state(pending|running|completed|failed|skipped), started_at, finished_at
DeliveryAttemptRecord      tenant_id, id, occurrence_id, destination, status(pending|delivered|failed),
                            attempts, last_error, provider_message_id, created_at
```

不变量：
- occurrence 幂等键唯一约束——重复触发（重启/时钟偏移/手动 run-now 撞同一 scheduled_at）只产生一个业务执行
- 投递重试只更新 DeliveryAttempt，绝不重触发 occurrence
- 所有行 tenant 过滤；调度 Worker 恢复时按 tenant+enabled 重建

## 4. 迁入策略

| 上游模块 | 策略 | 处理 |
| --- | --- | --- |
| `cron/manager.py` 调度/恢复/锁 | B | APScheduler 语义保留；RepoBundle → SQLModel 仓库；Gateway 装配 → PrismOS 执行入口（经 Gateway API 而非进程内 Gateway 对象） |
| `cron/trigger.py`/`task_type.py` | A | 纯逻辑原样 |
| `cron/job.py` 状态记录 | B | CronJobRow → ScheduleOccurrenceRecord |
| `cron/delivery.py` 会话锁投递 | B | 会话键 → SessionBinding（thread 绑定）；投递经 DeliveryAttempt |
| `cron/tools.py`（自然语言建任务） | B | 工具接 PrismOS 治理：创建任务本身是纳管动作（`schedule.create` 走 Policy） |
| `proactive/`（主动推送） | 暂缓 | 复用 cron 骨架，R3 末按剩余容量决定是否纳入 |

## 5. 治理接入

- `schedule.create/update/delete`：管理员 API 直达；Agent 工具路径走 Policy（风险类别 side_effect）
- 触发的执行与 Web 诊断同一可信链路：Gateway 签发执行能力 → LangGraph 严格模式消费 → RunFact 记录
- occurrence 状态机：pending → running → completed/failed/skipped；审批等待 = running 下的子状态（Approval 恢复语义沿用 M1）

## 6. 测试与验收门

1. 契约：幂等（同 scheduled_at 重复触发单执行）、重启恢复（重建调度无重复）、run-now 与定时去重、投递重试不重执行、时区
2. 迁移升降级 + 非空降级保护
3. 真实部署：N04 栈加 cron Worker 容器 → 六场景演练（§1）
4. 单调度者约束写入部署文档（多实例=未支持，明确红线）

## 7. 节奏（3–4 周，R2 实测成本校准）

| 周 | 交付 |
| --- | --- |
| 1 | 数据模型 + 迁移 + 调度 Worker 骨架（boot/恢复/单实例）+ Gateway 任务 CRUD API |
| 2 | 触发→Run 链路（幂等/时区/run-now）+ 投递（web 会话）+ 治理接入 |
| 3 | 自然语言建任务工具 + 真实部署演练（六场景）+ Team 子 Run 关联预研 |
| 4（缓冲） | 主动推送切片（若容量允许）/ O12 首个新通道适配 |
