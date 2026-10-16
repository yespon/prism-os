# N04 独立 WSL 测试环境（2026-10-16，Asia/Shanghai）

沿用 `codex/octop-integration` / `645fb42`。用户明确授权“需自己部署，如需我配合请给出操作流程”。本块部署并保留独立本机测试栈，不改变其他项目服务，不推送、不发布。原 M1–M7、N01–N15、O01–O42/F01–F12 和全部退出条件保持；M1 未退出，N08 不启动。

## 已可使用

- Windows 本机访问 `http://localhost:18026`，实际 PowerShell HTTP 请求返回 200；未初始化时跳转 `/setup`。
- 原 Gateway、LangGraph、前端生产构建、租户/认证/检查点三个 PostgreSQL 数据库独立运行；原认证和线程边界保留。
- `https://ticket-receiver:8443/tickets` 为栈内真实 HTTPS 测试工单接收端。独立 token、受验证证书，持久接收次数与幂等键哈希；不存储请求正文、凭据或原幂等键。`/stats` 需要认证，`/health` 不含业务数据。
- 同幂等键/同正文返回同测试工单 ID，接收次数仍逐次增加；同键不同正文返回 409。故障模式 `ok/fail/timeout` 可从受保护本地文件控制，实际 HTTP 503 和延迟响应均先记录接收事实。
- 原 Provider 从实际 Gateway 容器发送成功/重复/503/超时请求，TLS 验证保持开启。当前确认的是本地目标网络传输，不是模型或受控 Action Golden 验收，也不是外部企业工单服务等价。
- 三数据库各自 pg_dump/独立 pg_restore 成功，租户恢复库唯一 head 为 `n8h9i0j1k2l3`。备份内容留在私有 runtime，公开证据只保存摘要/表数/恢复库名。此项不等于完整应用/配置恢复或目标部署制品回滚。
- 重启 Gateway/LangGraph/接收端后健康和原初始化状态恢复，接收次数保持。数据库与文件保留，便于继续真实测试。

## 用户需要的操作

1. 打开 `http://localhost:18026/setup`，自行设置管理员邮箱和密码。
2. 登录 `http://localhost:18026/admin/models`，添加支持工具调用的真实模型，填模型标识、正确服务地址与 API Key，保持服务证书验证，执行连接测试并启用模型。
3. 告知模型配置名称即可，无需向聊天发送账号密码/API Key。管理员配置完成后将继续使用真实认证、租户和审批人运行 allow/deny/approval/撤权/故障/调用次数，并重新裁定原五道门。

运行目录（WSL）：`/root/.codex/worktrees/octop-integration/prism-os/backend/tmp/n04-wsl`。

配置和数据库密钥所在 `config.yaml`、`runtime.env`、接收端 token/key 均为 0600，runtime 根目录 0700，整个 runtime 被 Git 与镜像构建排除。不要将它们复制到公开证据。30 天本地测试证书到期需重新签发；不关闭验证。

在上述工作区，使用 `backend/.venv/bin/python scripts/octop_wsl_test_env.py status` 查看状态；`up` 启动、`stop` 停止但保留数据，`restart` 重启。`init` 只允许空 runtime，拒绝覆盖既有配置。管理入口核对自身 marker 和目录归属；拒绝无 marker/错误 marker/符号链接目录。不会运行清卷命令。

`receiver/receiver-mode` 是私有本地故障控制文件，常态为 `ok`；故障验收后恢复 `ok`。后台收据只用作核对调用事实；当前失败/超时记录不自动认定生产工单成功。

## 验收与证据范围

- `receiver-tests-final`：16 项通过（10 新增接收端/归属测试 + 6 原运行配置检查）；实际 TLS socket、并发请求、相同幂等键、冲突、未授权、持久重开、真实客户端超时与管理入口拒绝。
- `receiver-runtime-final`：原 Provider → 当前容器网络 → HTTPS 接收端；2 次同键成功请求、1 次实际 503、1 次原 30 秒 Provider 超时，接收端增量精确为 4。
- `health`、`backup`、`restart`、`deployment-proof.json`：实际运行、独立数据库备份恢复、重启、持久计数和挂载/监听/权限检查。
- `upgrade.json`：固定新增部署/接收端契约下 b5→b6→b5，各阶段实际 16 项通过。它是源码能力升级/回退，不是运行数据库破坏性降级或完整目标部署回滚。
- `historical-reuse.json`：2045 个未变输入精确哈希，原 2403 后端/18 跳过、151 Office PG/镜像及前端生产构建等只按原范围复用；不声称本块新跑全后端/前端，不将测试数相加伪装一次全量结果。原包/依赖锁/902 原样资源未改变。
- 不启动重复前端构建。独立前端服务使用已验收 `.next` 和原依赖只读挂载，记录 BUILD_ID 摘要；它是本地测试环境，不宣称已制作独立可移植前端镜像。

首次 Provider 验收失败原样保留：验收脚本重建 Incident 时间戳，使第二次请求与相同幂等键的正文不同，被接收端正确拒绝。现仅固定测试 Incident 时间；Provider 未改。初始 Ruff 的测试导入排序失败与修正前输入快照保留，修正后静态检查及三阶段当前测试通过。

## 未完成边界和下一步

真实模型尚未配置，真实认证下的模型→受控 Tool→接收端、审批人/请求者、撤权/unknown/重启后恢复、完整 M1 五门仍待验。受控 Action 默认 off/deny，trusted graph canary 未启用。当前模拟故障和本机 HTTPS 接收端不能替代真实模型或外部业务系统验收。N07 远端 CI、真实远端设备/集群、通用 Secret/委派及完整专家/Office/外部能力仍保留。
