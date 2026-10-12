# N07：独立构建与隔离部署证据

2026-10-12（Asia/Shanghai），基线 `a4c1531`。N07 本地构建与部署已验证；远端 CI 未运行，N04 目标环境仍待位置/配置引用。M1 未退出，不启动 N08 持久执行实现。完整 N01–N15、O01–O42/F01–F12 与原 PrismOS 门禁保持原范围。

## 实际结果

| 检查 | 结果与边界 |
| --- | --- |
| 独立检出与锁定安装 | 自有 `.venv`/`node_modules`；无原工作区模块来源；原两个锁文件不变。注册表缓存可以复用，原工作区依赖目录没有被借用 |
| 完整后端 | 1,550 通过、18 跳过、30 warnings；跳过项不记通过 |
| 完整前端 | 43 文件 / 128 通过；两个完整 UI 流程按实测使用 15 秒有界预算，全部断言保留；此前 5 秒超时日志保留 |
| `make octop-build` | 187 后端 / 37 前端有界测试、类型、真实认证 Gateway、902 文件 wheel/sdist、生产构建通过 |
| 固定旧来源与升级回退 | 重新从固定 b5 commit 取得原始归档，校验原 SHA 和成员锚点，只保留过滤源码及收据；b5→b6→b5 三次各 53 项相同宿主契约通过，不依赖原临时缓存 |
| 生产 Dockerfile / Compose | 独立镜像和 6 个实际服务；PostgreSQL、db-init、Gateway、LangGraph、前端、Nginx 运行通过；运行源码与候选摘要相符，镜像内 902 成员校验通过 |
| 真实 HTTP 路径 | 首次管理员设置→登录→会话/租户→Agent 创建/编辑→问卷只读→鉴权头像摘要→Gateway/LangGraph 线程创建/状态；模型与外发没有调用 |
| 重启与备份恢复 | 重启 PostgreSQL/Gateway/LangGraph/前端后会话与 Agent 保留；单管理员；真实 pg_dump/pg_restore 校验 head 和 Agent 数据；不保留含会话的数据库转储 |
| 隔离与清理 | 唯一容器/网络/卷，临时配置及数据，端口只绑定 loopback；清理后本项目容器、网络、卷均为空；两个服务的受控 Action 与严格图上下文均实测为 off |
| 文件追踪与代理 | 50 个 NFT 收据，引用均在独立 frontend 内；原根目录/whole-project warning 已消失；生产目录 API 实际穿过 Nginx，本地配置用日志前缀校验通过 |
| 原能力与静态门 | 完整能力账本保持 42 / 12；品牌、CI 修改面 Ruff 与差异门通过；CI 仅本地解析与检查，未记远端通过 |

原始日志及结构化摘要由 [validation.json](validation.json) 记录 SHA。独立模块见 [runtime-origins.json](runtime-origins.json)，来源升级见 [upgrade.json](upgrade.json)，部署、恢复、实际镜像 ID 与清理见 [compose.json](compose.json)，镜像运行源码见 [image-source-match.json](image-source-match.json)。候选源码摘要见 [candidate-code.json](candidate-code.json)。

## 修改与实际发现

NodeSource TLS 失败后，后端从官方 Node Debian 镜像取得 Node/npm/npx。安装继续使用原锁文件，Compose 启动使用 `uv run --frozen`。Docker 上下文保留能力包 Markdown，实际镜像验证模板/资源完整。

初次部署服务健康，但 `/api/auth/bootstrap-status` 返回 500：Gateway 仍假定前端负责 PostgreSQL 身份建表。Gateway 现在按原 TEXT 时间/INTEGER 标记结构创建缺失表，PostgreSQL 事务锁串行化初始化，不改写存量表、不新增身份仓库或 Alembic 分支。随后首次设置、登录、多进程重启及数据保留通过。既有部署身份字段兼容仍需目标环境验收。

首次通过生产入口访问目录 API 返回 404；生产/本地 Nginx 现显式转发 `/api/agent-catalog`。demo Artifact/History/Search 与静态入口统一限定公开 demo 范围，拒绝遍历、跨线程、根目录和线程别名符号链接，保持原文件 URL/历史形状/排序分页；缺少可选数据返回 404 或空列表。

## 保留的限制与后续动作

容器仍使用原 LangGraph dev/no-reload 路径。日志记录自定义 checkpointer 缺少 `adelete_for_runs`、`aprune` 和 allow-blocking 的影响：不能据本轮空线程状态请求宣称 Run 取消回退、历史修剪或 M2 持久生命周期完成。这些进入 N08 增量设计及实际验收。旧配置兼容输入优先级 warning 未阻断本轮独立路径；原后端 30 项 warning 保留，未通过升级依赖掩盖。

测试 PostgreSQL 初始化的本地 trust 提示与重启产生的 terminating-connection 日志属于本次隔离/重启演练，不代表目标数据库安全门通过。3 个依赖外部环境的运维插件在本次隔离配置中关闭；原插件能力不因此削减。

下一步：N07-B 取得实际远端 CI 证据；环境信息具备即执行 N04 真实模型→受控 Tool→可核对次数的测试工单及 M1 五道门。等待期间准备 N08 增量设计，资源声明/安装与独立 Office 的 N09 预检按原依赖推进。当前树与候选制品排除 237 项已知受限资源，既有 Git 历史未重写，未向远端推送。

## 复现入口

从迁入分支独立检出，先按锁文件安装前后端，再运行：

```sh
make octop-build
make octop-upgrade OCTOP_UPGRADE_DIR=/absolute/empty-evidence/upgrade
make octop-compose OCTOP_COMPOSE_EVIDENCE=/absolute/empty-evidence/compose
```

后两项使用新证据目录；需要注册表/GitHub 访问、Docker daemon 和正常依赖安装。Compose 入口先构建实际 Dockerfile，再由脚本创建唯一测试资源并在退出时清理。CI 已接入同样入口与证据上传；实际运行后才能更新状态。
