# 原 Auth 会话到期与 HTTP 当前交付

2026-10-15。沿用 `codex/octop-integration`、`40b7971`。第一里程碑 HTTP 会话功能块；M1 未退出，N08 不启动。

## 可用能力

原 User/Session 表仍是认证事实源。空白、缺失、损坏和已过期的到期值不再产生不限期会话。统一解析原 ISO 时间、实际 PostgreSQL datetime 和旧 UTC 无时区时间；原可选字段按实际 schema 查询，避免旧 PostgreSQL 表第一次失败后继续使用已失败事务。原 `/api/auth/session` 使用相同到期契约，存储错误返回通用错误，不记录令牌和数据库异常原文。

请求开始后，会话删除、过期、换绑或存储不可用会阻止旧结果交付。只读请求在响应头前发现撤权时返回401；写请求返回503及 `inspection_required`，不假装已撤销已发生的业务写入。实际 SSE 在空闲等待和每次交付时复核，撤权后关闭本地消费任务，不发送迟到私有结果或伪造 RUN_FINISHED。另一会话注销不影响当前合法会话。

原 Header／Cookie／查询参数会话、Session／logout、账号改密字段语义、Native 文件／历史入口、授权 Range 与附件头保持可用。令牌只在当前请求闭包中使用，不新增会话权限表，不放入图执行上下文、Run、Prompt、Action 或持久状态。原 Policy/Approval/Action/Audit 不替换。

## 实际验证

- 初始隔离复现：11 failed / 2 passed，涉及无效到期、在途删除/过期/换绑仍返回结果和异常日志令牌泄漏；原日志保留。
- 最终相关集成：`101 passed, 102 warnings in 41.97s`，包含前一块账号撤权、原文件/历史入口及原审批路由。实际 HTTP 中间件与实际 ASGI SSE 发送帧均验证；原 Native 入口使用原数据库成员/线程事实，不靠伪造请求身份。
- 完整后端：`2231 passed, 18 skipped, 642 warnings in 754.22s (0:12:34)`，退出码0，全部 2019 个宿主/前端输入在整个验证期间哈希未变。旧块的六处测试夹具失败历史仍留在40b7971，不改写。
- 实际自有 PostgreSQL：`41 passed, 11 warnings in 12.55s`，包括 TIMESTAMPTZ、旧可选列、原 logout 与 Session API、空闲SSE、Native下载/历史/Range。租户解析夹具只选择明确的自有测试租户；原 Native 授权仍读实际成员/线程。原 runner 的通用 SQLModel schema 标签不代表本块范围，实际范围以测试文件与本说明为准。临时数据库容器已清理。
- 最终镜像 `sha256:389754ccf7fa55567ea05b37b8a56af6a0f98e41037cb12d4df4484871b0745b`，9个当前源码/测试输入匹配；默认权限、无网络实际验证 `78 passed, 93 warnings in 36.81s`，容器已清理。本次不含需要嵌套 namespace 的Local命令正向测试，不将上一块明确未覆盖的容器范围改写为通过。
- b5→b6→b5三阶段分别：75 passed, 79 warnings in 28.64s; 75 passed, 79 warnings in 35.96s; 75 passed, 79 warnings in 37.93s。139 个宿主契约哈希固定，全部阶段退出码0，宿主未改变。新 Auth 文件及测试进入原探针默认清单。
- 当前 CI Ruff、原品牌526允许项和代码/文档空白检查通过，无新增豁免。原始 `.log` 不做空白清理，逐字节归档核对。

504个未变前端输入仅复用40b7971继承的原完整测试/严格构建/50追踪及其既有格式清理范围；来源902成员、原制品/清单/依赖锁及旧provisioner实际HTTP只按各自未变哈希复用。不复用旧后端全量结论。`validation.json` 保存所有结果与原始日志SHA，暂存/提交逐项核对。

首次 runner 在日志目录建立前未启动 pytest，保留 `session-runner-unlaunched.json`；目录建好后才有正式复现结果。WSL启动超时不计实际验证，不重复启动已经运行/通过且输入未变的门。

## 未完成边界与下一功能块

本块是 HTTP 准入及结果/长流交付。WebSocket不由该HTTP中间件承载，仍须单独处理交互连接会话的撤销和多连接隔离；下一块继续此缺口。已委派远端工作、远端副作用没有因此被宣称取消或回滚，不新增后台Run生命周期。

N04真实模型/外部Tool/可计数工单环境引用及N07远端CI仍待；真实SSH/Kubernetes、Browser/设备、通用Secret/Connector、18专家/实际子Agent委派、独立Office和外部运行接缝均保留。所有N01–N15、O01–O42/F01–F12、原M1–M7/Golden/五门及必要退出条件不删减。未推送、发布或部署。
