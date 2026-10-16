# N04 目标部署故障与真实到期验收

沿用 codex/octop-integration / 1c11dbb。本块在已部署的独立 WSL 栈上，通过原 HTTP 登录、用户配置模型、原受控 Tool 和 PostgreSQL/HTTPS 接收端验证；不改应用源码，不绕过原 Policy/Approval/Action/Audit，也不进入 N08。

## 实际执行范围

- wall_clock_expiry.py 使用真实模型建立待审批动作，读取原数据库记录的 300 秒有效期，自然等待到期；不改时钟、TTL、审批或决策事实。到期投影、迟到批准、恢复/重复恢复与接收端次数均有断言。
- database_faults.py 只允许操作标签为 prismos-n04-wsl 的自有 PostgreSQL 容器及预建测试租户。临时 SQL 触发器分别在 Policy、Policy 关键 Audit、提交结果 Audit 和旧 IncidentAction 投递 INSERT 抛出 SQLSTATE 55000；序列的真实命中次数跨事务回滚保留，避免把未到达故障点当通过。
- run_database_faults.py 经真实模型/HTTP 触发这些写入。前两类故障须同事务回滚、无提交事实且无网络调用；结果 Audit 写失败须保留 unknown，恢复不重发；旧投递失败须保留成功提交事实，恢复后调用原 LegacyAuditDeliveryService 两次，只补齐一条旧时间线记录，不重发工单。
- finally 删除本探针的三处触发器与临时 schema，并核对目录清理；Gateway/LangGraph 测试开关恢复 off。最终运行检查及三库备份/恢复另有实际退出码。

脚本存在不代表验收通过。各 *-result.json 的 complete/returncode、业务 JSON 的 complete、最终 validation.json 共同确定结果；未闭合或失败证据完整保留。模型原始回复/SSE、服务日志、凭据和数据库转储仍只在忽略的私有 runtime。

## 复用与边界

historical-reuse.json 固定 1c11dbb 的 2058 个当前输入逐字节 SHA。应用/依赖/镜像未变，按该提交已经明确的完整后端快照、后续函数/镜像/实际 PG 与升级回退范围复用，不另跑 unchanged 全量，不改写历史数量。新证据证明的是独立 WSL 测试目标；自建 HTTPS 接收端不等价企业 Jira，尚不能宣布全部 M1/N04 或外部业务能力完成。

验收中另外真实发现原测试栈将 /app/skills 整体只读挂载，原租户 Skill 创建返回 503。未把这个缺口算作成功；后续连续修复部署可写持久化及原创建/编辑/重启/授权读取。只读文件 PEP/其他入口、完整目标配置与制品回退、原五道门重新裁定和远端 CI 等仍保留。

## 已取得的真实结果

审批有效期原为 05:13:56.373210Z 至 05:18:56.373210Z，模型返回后实际等待 296.895 秒；到期后批准 409，恢复与重复恢复均 expired，计数 23→23。四个 SQL 故障点各真实命中一次：Policy/关键 Audit 均 23→23，结果 Audit 23→24 且 unknown，旧投递 24→25 且重放后只有一条兼容时间线记录。各业务 JSON 和原始日志保存断言与实际退出码。
