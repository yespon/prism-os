# N04 真实运行接通与当前治理修复（2026-10-16，Asia/Shanghai）

沿用 codex/octop-integration / b474c64，不新建目标或分支。用户授权自行部署 WSL 环境，随后通过本机模型管理配置 gpt-5.6-luna。此处只使用该配置名称，不导出模型凭据或服务地址。M1/N04 的完整退出仍按原五道门裁定，N08 不启动。

## 新增可用能力

- 生产与本机代理的其余 /api/ 入口统一转发 Gateway，告警来源、事件、审批、租户设置等实际返回原认证 JSON；保留两条 Next.js Terminal chat 入口及原上传/线程更精确路由。本机事件 SSE 保持流式响应。生产前端和 WSL 初始化配置补齐 GATEWAY_URL，原 Terminal 代理不再错误连接容器自身 localhost。
- PostgreSQL 全局异步工厂不再跨事件循环复用 asyncpg 连接，支持原同步运行时回调的短生命周期循环。SQLite 行为保持。参见 [SQLAlchemy 多事件循环约束](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-multiple-asyncio-event-loops)。代价是 PostgreSQL 每次独立会话建立连接；这里不宣称高并发吞吐门已通过。
- Terminal 凭据依赖延后导入 Gateway 授权模块，冷启动时 Terminal/Assets 插件均可完整注册，原当前成员/资源/SSH 用途检查保留。
- HTTP 恢复只从持久决策白名单恢复原生 Agent 和保护来源上下文；当前事件换绑 Agent 时拒绝。客户端伪造字段不改变旧 Action。
- 已 submitted/unknown 的恢复操作在重新核对当前原生身份后读取持久事实。诊断完成后的正文变化不重算或重发已经提交的动作；unknown 保持未知。未提交动作仍检查原批准正文/目标，变化后拒绝。
- 未提交动作必须继续匹配当前 Policy 标识、版本及规则 verdict；旧批准不能在当前规则变化或配置缺失后继续消费。can_resume 投影也使用相同纯检查，历史审批事实保持原状。

## 真实环境与验收边界

使用已部署的独立 WSL 栈：Gateway/LangGraph、实际 PostgreSQL 租户/身份库、用户配置的真实模型、独立 HTTPS 测试工单接收端。测试账号和租户由原本地 operator repository/service 初始化，随后使用真实 HTTP 登录和原权限、Policy/Approval/Action/Audit 链路，不替换模型或 Provider。未读取用户的浏览器会话、密码或 CLI 账号。

接收端是自建测试目标，真实处理 HTTPS POST 并持久计数；不是 MockTransport，也不是企业 Jira 等外部业务系统。这里不将自建目标宣称为完整外部企业工具等价。凭据、转储、原始模型/SSE/服务诊断保存在忽略的私有 runtime；公开证据只保存状态、非敏感 ID、计数和摘要。

真实场景见各 JSON 与 validation.json：deny、allow、批准/拒绝、Agent 撤权、Secret 撤回、实际并发轮换单胜者、重启后恢复、HTTP 503/30 秒超时 unknown、重复恢复不增加调用，以及当前 Policy 变更后旧批准失效。最终提交必须等待全部当前必要门的实际退出码；不能以脚本存在记作通过。

审批正向场景使用原 Source 功能中的显式 title/key 模板，确保审批期间正文稳定。默认正文包含 diagnosis_result，诊断完成可能改变未提交动作的正文；此时旧批准按原保护失效。这里没有添加持久正文快照，不把此边界伪装成完整通用 Action 快照能力。

## 保留的实际失败及修复

1. 原代理遗漏 /api/alert-sources，来源创建落入前端 HTML 404；修复实际路由后以当前 HTTP/认证重验。
2. 原冷启动插件循环导入与 PostgreSQL 连接跨循环复用导致真实图失败；受保护原日志保留，冷进程及独立 PG 多循环/并发查询与真实模型诊断复验。
3. 原恢复入口丢失 Agent 上下文，随后又因诊断正文更新而无法读已提交事实；保留首次 403/409、真实提交事实和计数，修复当前恢复行为。
4. 已批准后把当前 Policy 改为 deny，旧实现仍向隔离接收端发送一次，13→14；真实失败和原始提交保留。新版本不再把持久决策误作当前执行授权，并以真实配置变化重验。
5. 验收脚本最初漏传 Secret DELETE 的 expected_ref_id，原 API 正确返回 422；只补跑未完成场景。
6. 验收环境脚本曾逐服务生成不同 Policy 版本，当前版本门正确拒绝正常恢复。改为一次生成同时下发，并通过实际容器环境白名单核对一致后重验；原失败保留。
7. 新冷启动夹具最初假设 FastAPI 所有路由都有 path，及新增 fixture 导入排序问题，均保留失败并修正夹具，不降低产品门禁。

## 测试与历史复用

此前已启动的完整后端在 inputs-before-settled-read.json 对应快照完成：2435 通过、18 跳过。其后只调整恢复/状态投影和 Policy 检查函数，并新增 Policy 回归；由当前针对性、当前镜像和固定源码升级回退闭合，不宣称在最终源码上又跑了一次完整后端。

source-before-*.tar.gz 保留变化前自有源码；final-scope.json 验证其余 AST 不变、配置构造器提取等价。当前输入记录于 inputs.json，前端/来源/制品/worker 等仅按 historical-reuse.json 未变覆盖范围复用。18 个历史跳过仍按原环境条件记录，新增真实目标验收独立列出，不能直接抵消所有跳过。

当前镜像字节证明、默认权限无网络镜像回归、实际 PG 查询、升级/回退结果及原始日志 SHA 见 validation.json。上游固定原版本和 902 原样成员、宿主锁和唯一迁移 head 不变。远端 CI 未执行，未推送或发布。

## 仍需推进的原退出条件

保留原目标部署的 Policy/Audit 实际写故障、审批实际到期、旧审计投递故障与恢复、只读文件 PEP/其他入口真实复核、完整目标配置/备份/制品回退等尚未取得的证据。必须重新逐项裁定 M1 五道门，不能仅凭当前模型/工单正向链路启动 N08。通用 Secret、真实远端设备/集群、完整专家/Office/外部能力以及原全部 N/O/F 与 PrismOS 能力目标继续保留。

## 本批最终计数口径与闭合

接收端 V2 从每个 HTTP POST 入口即持久记账，认证失败、无效正文和幂等冲突也计入，避免只统计成功受理掩盖额外调用。原 V1 的 18 条历史记录保留为 admitted receipts，不能追认成全部 HTTP 请求；counter_version=2 / historical_v1_receipts=18 明确分界。升级未重写旧回执。

在 V2 下重新执行实际模型矩阵：allow 及两项批准/重启分别只发送一次；拒绝、Agent 撤权、Secret 撤回/并发轮换、批准后当前 Policy 变更均不发送；503 和 30 秒超时各一次并保持 unknown，所有已结算重复恢复均无新增 POST。最终接收端计数 23，真实业务目标仍是隔离 HTTPS 测试接收端。

完整后端快照 2435 通过/18 跳过；后续当前 Policy/恢复相关 69 通过，当前核心镜像 95 通过，最终 V2 接收端宿主/镜像各 10 通过。原应用固定源码 b5→b6→b5 每阶段 100 通过；仅最终接收端变化的同三阶段每阶段 10 通过，181 个宿主契约输入核对。两轮覆盖关系由 final-scope.json 和 validation.json 明确，不把分组相加宣称一次最终源码全量。最终运行开关均 off，三数据库再次真实备份/恢复成功；公开证据按真实配置中凭据核对且不导出材料。

最终差异门另清理 test_incident_diagnosis.py 文件末尾一个空行；final-whitespace.json 保存前后 SHA，AST 完全相同。镜像/升级保留原测试字节事实，不重写历史结果；最终源码输入仅此非语义差异，生产代码未变。
