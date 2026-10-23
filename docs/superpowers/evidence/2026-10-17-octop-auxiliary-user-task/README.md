# 原专家与非 Skill 资源的真实任务

沿用 codex/octop-integration、d52ff07；原里程碑、N01–N15、O01–O42/F01–F12 和必要退出条件不变。M1 未退出，N08 未启动。

新增可用任务：从原目录创建“育儿陪伴”专家，明确安装并选择上游记忆一致性检查脚本，在纯虚构的当前线程工作区中完成“同步 → 主题变更/过期 → 更新索引/恢复同步”，制作可下载中文 Markdown 报告，重新登录查看历史。配置模型为 gpt-5.6-luna。实际输出中两次同步、一次过期，最终 run success 且无待执行节点；没有以模型自述代替脚本执行。

## 核实到的环境偏差

- 原脚本、安装和受控命令已接入；此前 Local/AIO 隔离证据不证明当前应用容器支持嵌套用户命名空间。
- 首个实际任务在默认容器配置中失败，Bubblewrap 明确无法创建用户命名空间。real-auxiliary-task.json 和失败日志保留，不算能力验收。
- 自定义 seccomp 放宽方案被自动审批拒绝，未执行。没有使用 privileged、unconfined、额外 SYS_ADMIN、应用 Docker socket，也没有修改主 Compose 安全设置。
- WSL 原生 Bubblewrap 实际隔离可运行、能力集为零。新增独立原生测试配置：克隆自有 PostgreSQL 三库并保留模型加密配置，服务仅绑定 loopback。原18026和Compose不变。

原生浏览器入口为 [http://localhost:18036](http://localhost:18036)。任务经同一产品认证/API入口执行；页面和匿名拒绝已检查，不称逐控件浏览器自动化。测试代理支持HTTP/SSE，未实现WebSocket；原容器WebSocket入口保留。默认容器脚本限制仍在，不把原生成功算作默认容器已修复。

## 实际证据

| 场景 | 证据 | 范围 |
| --- | --- | --- |
| 原目录、专家、真实脚本/模型/报告 | real-native-auxiliary-current.json / .md | 脚本和持久提示词哈希保持；新登录历史、非所有者/跨租户拒绝通过 |
| 错误处理和恢复 | 报告真实过期/exit 2及同步恢复；pause-recovery.json | 暂停拒绝新执行，不新增run且合法历史保留；启用后资源/提示词复原 |
| 服务重启/当前代理 | native-restart.json、native-proxy-current-result.json、real-native-after-restart.json | 同一任务/文件哈希保持，零新增模型提交 |
| 隔离与重启保护 | native-control-related-result.json | 实际Local/AIO脚本及拒绝；身份/PID会话改变或活动任务时不发送停止信号 |
| 来源升级和回退 | upgrade.json + upgrade-current.json | 原生配置/任务CLI加入固定契约；旧/当前/回退来源脚本场景，不冒充三次真实模型验收 |

首次原生任务也实际成功，但探针误用Agent UUID调用按名称查询的详情接口，最后核验404。修正查询并直接重核验原任务，未重复模型执行。原失败保留，容器失败与原生成功不混算。

## 最短使用流程

当前原生配置已启动。账号配置引用：忽略目录 backend/tmp/n04-wsl/native-profile/live-fixture.json，仅本机读取，不提交/公开。副本切换测试账号标签，以使用另一成员的新个人资源空间；原容器账号不变。副本不会自动同步原环境后续配置修改。

- 新任务：`backend/.venv/bin/python scripts/octop_auxiliary_task_probe.py --base-url http://127.0.0.1:18036 --fixture backend/tmp/n04-wsl/native-profile/live-fixture.json --output <新的证据文件.json>`，会调用真实模型。
- 只核验既有结果：加 `--resume docs/superpowers/evidence/2026-10-17-octop-auxiliary-user-task/real-native-auxiliary-current.json`，使用新输出文件，不提交新模型任务。
- 安全重启原生Gateway/LangGraph：`backend/.venv/bin/python scripts/octop_wsl_native_env.py --mode restart --output <新的重启证据.json>`。要求保存的进程身份/会话仍匹配、无活动任务；无法确认时停止，不接管其他PID。
- 从空的专用私有目录准备配置：同脚本默认prepare。已有目录拒绝覆盖；失败保留诊断和数据库。

不新增密钥依赖，不收集/公开密钥；完整流、环境、数据库材料和进程日志保持私有，公开报告仅含虚构演练内容。

## 行为差异与未完成边界

原脚本默认$HOME/.octop/workspace；主机说明要求显式OCTOP_WORKSPACE指向当前线程。保留上游原件、许可/来源哈希和只读资源视图，写入保留租户/成员/Agent/资源/线程授权。M1工单试点保持原边界和off；不宣称所有Bash均完成Policy/Approval/Action/Audit验收。

只验收手动记忆一致性任务；完整育儿业务、其他专家/子Agent、heartbeat/cron、真实外部投递、完整记忆维护/迁移、默认容器脚本、原五门裁定和远端CI仍待。没有把未接入说成已删除。

复用仅限未变输入：前端源码/既有构建未变；d52ff07的API/Harness生产代码、容器镜像和关闭态制品回退未变。新原生配置、CLI和控制保护由本块实际证据覆盖；旧完整后端不算本轮全量。保留此任务CLI作为后续升级行为回归入口。

提交前发现Popen返回到exec之间记录命令行的时序问题，导致最后进程核对误报；现已等待精确启动argv再记录。旧记录仅在原PID启动时间、精确启动argv及所有权nonce均吻合后修正，未接管其他进程。原失败、修正记录、控制回归及新的实际重启保留；当前判定见auxiliary-final-proof-current，原实任务未重复。
