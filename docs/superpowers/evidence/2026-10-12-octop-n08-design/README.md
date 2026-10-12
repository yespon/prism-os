# N08 设计准备记录

2026-10-12，基线 `fddc307`。本批仅形成 [Spec](../../specs/2026-10-12-octop-n08-execution-design.md)、[ADR](../../../strategy/adr/2026-10-12-n08-platform-execution-facts.md) 与 [实施队列](../../plans/2026-10-12-octop-n08-execution-plan.md)，没有创建/启用持久 Task/Run/Attempt/Event、Worker、迁移或写入入口。M1 未退出。

[runtime-discovery.json](runtime-discovery.json) 来自当前锁定 public SDK 的方法签名，版本为 SDK 0.4.2 / API 0.12.2。create 不包含 run_id；未发现 active pause RPC；支持的参数与方法分别列出。该发现不证明 Native endpoint 的真实去重/恢复/取消语义，设计要求真实 contract 与 fault 证据。

N07 已观测 PostgreSQL checkpointer 缺少 adelete_for_runs/aprune；设计禁止以 rollback/修剪假定成功。平台 Run、逻辑 Attempt、Native RuntimeSegment 分开；未知派发、外部 unknown、协作取消、current ACL/Policy、immutable 公开快照与 Secret 引用、单 Alembic 链、旧线程和 AIOps/Terminal 兼容均纳入启动前设计。

原 M2/M3、N08 和其后各阶段完整门继续保留。后续要先取得 N04 的 M1 五道门退出，再审查/freeze 实际迁移和实施；文档不表示真实生命周期已交付。
