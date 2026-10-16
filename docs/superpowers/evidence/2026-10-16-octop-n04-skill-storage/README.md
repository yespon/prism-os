# N04 Skill 持久化与只读运行闭环

沿用 codex/octop-integration / 36941c7；不新建目标/分支，不提前启动 N08。用户配置的模型名称为 gpt-5.6-luna，真实调用均经原 HTTP 登录、原诊断图、当前成员/Agent/来源/Skill 授权、原 Policy/Audit 和自有 PostgreSQL。此处按配置名称记录，不推断模型供应商身份。

## 已修复的实际问题

原测试栈整个 /app/skills 只读，原生租户 Skill 创建返回 503。控制器增加该测试栈专属 backend/tmp/n04-wsl/skills-custom 可写持久目录，只覆盖 /app/skills/custom；来源和 public 保持只读。初始化与 skills-storage 升级操作均支持，后者检查原项目/归属、源挂载和自有路径，拒绝目录别名及外部挂载，原 Compose 字节私有备份，原配置保留且重复执行不覆盖已有资源。

实际创建/编辑/同名创建拒绝、非管理员写拒绝、跨租户读取拒绝和服务重建后内容/资源 ID/文件 SHA 保持均通过。初次真实诊断另暴露请求持有 Skill 行锁、后台又等待同一行的自阻塞：skill-lock-reproduction.json 保存实际 pg_blocking_pids 和 ReadTimeout，回归在修复前失败。现在诊断入口在 SSE 等待/启动后台前结束预检事务；后台和交付仍独立重查当前授权，并未去掉资源行锁或当前身份检查。

修复后的实际模型 read_file 调用产生一条 read_only/allow 决策及对应 action.policy_evaluated/action.read_result 成功 Audit；模型实际返回当前标记。停用资源后新诊断返回 403，接收端计数保持 25。通过的原 CRUD 范围按 live-skill-read.json 复用，原诊断超时保留，新的读取结果单列 live-skill-read-current.json，不重写首次失败。

## 验证范围和原始失败

- 新存储/归属保护 14 项通过；新增诊断事务回归、原诊断/来源撤权/当前交付/Skill 引用/长流相关 89 项通过；原模块另外接入独立 PostgreSQL 验证真实行锁 NOWAIT 和独立后台事务。
- 新应用镜像及当前固定源码 b5→b6→b5 按变化范围重新验收；之前仅存储控制器的升级证据保留为较早范围。具体终态、输入和原始 SHA 见 validation.json，不能以启动代替通过。
- 最初新增测试行长度错误，以及首次镜像探针漏挂接收端源码导致收集失败均原样保留。修正测试格式与只读显式挂载后复验；当前生产代码未为测试放宽权限。镜像探针无网络、默认权限、无 Docker socket，临时容器清理结果单列。
- 额外真实只读 Audit 故障由限定原测试租户/只读 Action 的 PostgreSQL 触发器完成，原始结果另列。Skill 主文已作为合法选中来源注入提示，因此这证明 Tool 的事务/Audit 边界，不声称模型此前不知道主文内容，不把提示缓存当作文件读取。

historical-reuse.json 对原 2058 输入逐字节核对，只有存储控制器、其测试、诊断路由函数及该测试四个输入变化，其余按原精确覆盖范围复用。source-scope.json 保证诊断路由其他函数 AST 未变，变化前自有源码归档保留。这里没有新全量后端/前端运行声明，所有锁文件和上游来源固定不变。运行镜像字节、实际挂载、开关 off、三库备份恢复和公开证据凭据检查在最终验收中再次核对。

## 使用与未完成边界

本机原入口 http://localhost:18026；已有环境升级命令为 `backend/.venv/bin/python scripts/octop_wsl_test_env.py skills-storage`，只作用于本工作区专属栈，不触碰其他项目。无需重新配置已可用模型。

当前块不等于整个 M1 退出。其他文件/工具入口的完整复核、完整目标配置/制品回退和原五道门最终裁定、远端 CI 及全部原 N01–N15/O01–O42/F01–F12 与 PrismOS 目标继续保留。自建 HTTPS 接收端不等价企业工单系统，实际集群/设备、完整专家与后续持久委派等不据此记作完成。
