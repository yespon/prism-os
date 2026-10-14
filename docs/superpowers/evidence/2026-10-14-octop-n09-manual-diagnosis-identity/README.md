# 人工诊断 Native 身份与原 Action 事实：候选验收

基线 `3afdde4`。人工 SSE 的真实 HTTP/DB/受控 SDK 先重现八项同名、异步快照与撤权故障，再接入原 capability 的 Native ID/事件绑定；当前请求、线程创建后、原归属登记后及发行/消费核对当前成员、租户、可见启用的实例与事件。人工不使用自动来源严重性条件，普通成员继续使用共享 Agent。事件消息等待后重读，graph 按受保护 ID 装配当前角色/Skill，不在消息重复保留旧配置。

原 ThreadBinding 表先建立当前 actor/tenant/name 归属，再发布线程指针。原任务管理的内存参数区分 active tenant/actor/native-ID，另一 actor 或同名另一实例不能附着缓冲；新任务清除旧指针，不读取旧会话 checkpoint。已知他人线程或 SDK 返回已有他人线程不覆盖；原表或原 owner 元数据能证明自身旧线程时保留原清理能力。不确定归属/取消不记为已终止。

原 ExecutionEnvelope 保留 workload 命名，在既有 attributes 中写入 Native ID；同名另一实例不能借用原工单或读取决定。读取 Runtime ID 也与 scope 一致；原 Policy/Approval、单次发送、unknown、审计与 canary 开关不变，无新 schema、资源注册表或 Run 事实。初始人工身份不证明普通聊天续接、完整不可变 AgentVersion 或全部文件工具授权。

| 验证 | 最终结果 |
| --- | --- |
| 完整后端 | 1816 passed / 18 skipped |
| 原人工/自动/Action/读取/图/架构相邻门 | 95 passed |
| 隔离 PostgreSQL | 195 passed，自有容器已清理 |
| 当前与独立统一门 | 各 546 后端 / 162 前端，严格类型 |
| 独立完整前端 | 57 files / 249 passed |
| 当前与独立真实 Gateway | 实际 AuthSession/成员表、原人工 SSE、同名个人/共享选择与普通成员使用 |
| 当前与独立默认生产构建 | typegen、严格 tsc、Webpack，观察退出 0 |
| 固定宿主 b5→b6→b5 | 52 输入固定，每阶段 360 passed |
| 静态/来源/制品 | CI 54 路径 Ruff、902 原样来源、4 外部固定包/7 制品、锁与离线重建 wheel/sdist 一致 |

12 个修改源码/测试/门与独立检出逐字节一致。499 个前端源码未改动且两份一致，当前完整前端 249 项保留基线历史适用范围，不当作本批新运行；独立完整前端为本批新运行。两份生产追踪各 50 文件未越出各自 frontend；独立检出仅排除两个宿主绝对元数据链接，不读目标，见[输入收据](independent-inputs.json)。完整原始日志摘要与范围见[validation.json](validation.json)。

首次原 Action 端到端夹具缺少 Native 宿主验证回调而失败，已接实际回调并保留原 actor/workload/单次发送/审计断言。初始缺少验证回调、错误测试路径的诊断及八项真实失败保留；两处格式错误已修正，没有新增豁免或关闭检查。制品使用当前已验证缓存离线构建，锁和 TLS 策略不更改。

Gateway SDK/模型流及选择记录仅在自有临时测试应用受控，不进入生产路由，不能代替 N04 真实模型/工具/可核对次数接收端。[范围审查](scope-audit.md)保留普通聊天与人工线程续接的具体实例持久绑定，旧名称/default/terminal，graph 并发变化、运行中撤权/实际取消与 unknown，所有成员文件工具与结果/历史访问、真正删除进程恢复和完整复制/分享目标重授权。

完整 C2/N09/M1 未退出，N04/N07-B 为 P0；N08 持久执行/委派不启动。完整 N01–N15/O01–O42/F01–F12、33 非 Skill、18 专家/子 Agent、独立 Office、外部运行/MCP 接缝和 PrismOS 原规划/能力/门保持，继续[后续队列](../../plans/2026-10-14-octop-n09-manual-diagnosis-identity.md)。
