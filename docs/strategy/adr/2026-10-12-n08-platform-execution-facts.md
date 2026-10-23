# ADR：N08 平台执行事实与 Runtime Segment

2026-10-12，状态：设计候选；实施受 M1 退出门约束，基线 `fddc307`。

现有 ThreadBinding/ExecutionEnvelope 已提供 M1 身份与稳定关联，但 Runtime 线程和聊天内容不承担平台 Task/Run/Attempt 生命周期。N07 的真实部署暴露了 checkpoint 取消回退/修剪能力缺口；锁定 SDK 的 create 没有 run_id 参数，审批恢复可能创建新的 Native Run。

采用平台 Command/Transition、持久 Event/Outbox/lease 和不可变租户快照作为事实；平台 Run ID、逻辑 Attempt 与 Native Runtime Segment 分开。审批恢复属于同一逻辑 Attempt 的后续 Segment，有限重试创建新的 Attempt。副作用 Submission、Policy、Approval 与 Audit 继续复用已有 M1 边界。

不确定 start/外发/取消保留 Unknown/Orphaned 并对账，不能按“未发现”自动重发。权限和材料在每次实际执行前重新核验，快照固定公开配置和来源，不冻结永久授权或解密材料。上层接缝使用平台 DTO/opaque refs，unsupported 操作有明确错误。

这一选择需要单 Alembic 链的事实表、索引、CAS/fence 与真实 fault matrix，维护成本高于进程内 Job；它保留原 M2 的恢复/取消/幂等要求，并为 N09/N11 的资源引用与团队父子 Run 留下统一接缝。M3 质量证据、M4 AgentVersion/Deployment、M5 DAG 与 Runtime 独立路线继续单独判定，不由本 ADR 自动启动。

实施与验证详见 [N08 Spec](../../superpowers/specs/2026-10-12-octop-n08-execution-design.md)。本 ADR 不表示新表、Worker、状态机或真实取消已交付。
