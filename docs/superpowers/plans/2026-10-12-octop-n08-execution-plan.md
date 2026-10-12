# N08 实施队列

2026-10-12。设计候选，基线 `fddc307`；M1 未退出，本文件不是启动持久执行的许可。保留完整原 M2/M3 与 N08，见 [Spec](../specs/2026-10-12-octop-n08-execution-design.md) 和 [ADR](../../strategy/adr/2026-10-12-n08-platform-execution-facts.md)。预算从前置门通过后按 1–2 名持续开发者估算。

| 顺序 | 修改接缝 / 交付 | 验证与退出条件 |
| --- | --- | --- |
| 前置 | N04 原五道门、目标 head/备份、Spec/ADR/兼容审查、模型/接收端 | 明确 M1 退出证据；未具备不创建/启用新生命周期 |
| 1 / 2–3 天 | platform.lifecycle DTO、状态/Command 矩阵、Snapshot/资源/秘密引用边界 | Transition 全矩阵、同租户、秘密拒绝、无 AIOps 必填与私有 Runtime 类型；独立 Adapter contract |
| 2 / 3–4 天 | 平台持久模型/Repository、单链 migration、CAS/幂等/Event/outbox/lease | SQLite/PostgreSQL 并发/重复/回滚/重启，旧 M1 数据不虚构回填；非空拒绝破坏性降级 |
| 3 / 2–3 天 | Native Run/Segment Adapter 与入口桥接；host provider 消费不可变快照 | start/stream/get_state 真路径；编辑 Agent 不改变运行；Secret 材料不进快照与输出 |
| 4 / 3–4 天 | 审批恢复、协作取消、deadline、有限 retry、Unknown/Orphaned 对账 | 同一逻辑 Attempt 的恢复 Segment；ACK 丢失不盲 start；真实接收端计数、并发 cancel/resume、撤权/轮换、Critical Audit 故障 |
| 5 / 2–3 天 | 只读执行投影/SSE游标/运营处置、原聊天/AIOps/Terminal 兼容 | 刷新/流断开/重启后事实可读；受控人工处置；禁用 AIOps 通用执行仍可用；真实五道门分别裁定 |

一次只推进一个核心写入接缝。每批来源/依赖差异、契约测试、完整回归、干净构建、唯一 head、fault 证据及制品回退办法随提交保存；不能把 N07 空线程请求或仅 mock Adapter 记成 N08 完成。

等待前置条件期间可推进 N09 的最小资源声明/来源 digest/原格式预检，保持只读；安装后的授权使用、执行快照绑定、子 Agent 委派与实际脚本 PEP/隔离遵守各自依赖，不将预检代替完整资源行为。
