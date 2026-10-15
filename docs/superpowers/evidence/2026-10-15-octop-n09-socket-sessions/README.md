# 原 Terminal WebSocket 当前会话与多连接隔离

2026-10-15，沿用 `codex/octop-integration` 与 `f76e3eb`。本块只关闭已复现的交互连接会话缺口。M1未退出，N08不启动。

## 新增可用能力

原 Auth User/Session 与 Terminal 租户、成员、线程、资产、Keychain 权限共同约束 WebSocket。Header、查询参数、Cookie 采用与 HTTP 相同的优先级；明确失效的 Header 不回退到另一有效凭据。令牌只在连接闭包中保存，不进入 Agent 上下文、共享 PTY、Run 或持久记录。

连接建立、资产查询后、PTY 获取/启动前、输入、resize、空闲等待及输出发送均重新检查当前会话。删除、到期、换绑或 Auth 存储不可用时关闭该连接；原共享 PTY 的资源授权独立保留，一条连接撤销不破坏另一条合法连接及同一个 PTY PID。并发 detach 不再破坏广播集合遍历。

发送被慢对端阻塞时，撤权先取消并回收发送任务，再有限等待关闭，避免阻塞合法对端广播。握手发送也可能阻塞，有限等待不等同于对端已确认。HTTP/WS 的已结束等待任务异常均回收，避免丢失异常的后台任务。关闭浏览器连接不宣称远端命令已取消或副作用已回滚；原 unknown、Policy/Approval/Action/Audit 不替换。

## 实际验收

- 真实隔离复现 `socket-observed`：4处失败（输入、resize、空闲、输出），原日志保留。首轮测试收集错误、实现缺少 asyncio 导入、随后局部导入缩进错误和已完成 receive 任务异常未回收的中间结果一并保留，未记为通过。
- 最终相关集成：106 passed, 188 warnings in 66.63s (0:01:06)。19项新增测试使用实际 ASGI WebSocket 帧、原数据库授权和真实本地 `/bin/bash` PTY；SSH builder 仅在自有测试环境替换为 Bash，不能计作真实 SSH。慢发送单元使用受控背压传输和原 Auth DB，完整成员/资产路径由其余集成覆盖。
- 完整后端：2250 passed, 18 skipped, 713 warnings in 912.58s (0:15:12)；2021 固定输入全程不变，退出码0。
- 当前实际隔离 PostgreSQL：19 passed, 33 warnings in 48.12s，原 User/Session 使用 TIMESTAMPTZ，Config/成员/资产使用自有数据库；旧通用 Terminal 夹具明确使用自有 SQLite Auth，不将 runner 的通用 schema 文本当作全范围证明。临时容器已删除。早期47项 PostgreSQL结果保留，仅对应其当时18项连接与29项终端范围；当前19项连接已重新运行。
- 最终后端镜像 `sha256:19309ada80b9753adca73c4db2630c6932d0a1a621e696be82ef3be3e6445a91`，14源码/测试文件匹配；默认权限、无网络：103 passed, 188 warnings in 69.31s (0:01:09)，容器清理完成。无特权容器或隔离放宽。
- b5→b6→b5：89 passed, 186 warnings in 114.20s (0:01:54); 89 passed, 186 warnings in 96.00s (0:01:35); 89 passed, 186 warnings in 97.50s (0:01:37)，141 固定宿主输入，所有阶段退出0，宿主未改变。
- 原 CI Ruff、品牌允许项526、代码/文档空白门保留，无新增豁免。原始日志逐字节归档，暂存及提交 blob SHA256核对。

504个未变前端输入仅复用f76e3eb继承的完整测试/严格生产构建/50追踪及其既有格式清理范围。902来源成员、原分发制品/依赖锁/清单和provisioner镜像HTTP证据仅按各自未变哈希复用；旧完整后端结论不复用。WSL启动超时不算测试，不重复已经实际启动且输入未变的门。

## 未完成边界

本块不覆盖跨来源 WebSocket 策略或全局委派生命周期。真实远端命令/共享挂载/终止、Browser/交互和Apple、N04模型/外部工具/可计数工单、N07远端CI仍待。通用Secret按原N10/M6接缝保留，不扩大ticket-only仓库。18专家/实际子Agent委派、独立Office四格式、外部Runtime/MCP、全部N01–N15/O01–O42/F01–F12与原M1–M7/Golden/五门退出条件保持。未推送、发布、部署。
