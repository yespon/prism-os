# 受控原生读取与严格模式结果访问

沿用 codex/octop-integration、94d6da1；原 N/O/F 和里程碑范围不变。M1 未退出，N08 未启动。

本块新增可用任务：从实际已认证的 Incident 诊断入口，由配置的 gpt-5.6-luna 读取当前 Agent 明确选择的资源包内 Word，制作新 Word，展示下载；实际成功终态、重新登录历史、文件哈希、同租户非所有者及跨租户拒绝均核对。文档中的随机验收标识不在选中 Skill 的提示词中。没有调用工单工具，接收端保持 26。

## 实际问题与修复

- `binary-policy-repro` 隔离复现：关键 Policy 写入失败，原生 DOCX inspect 仍返回正文。原 PEP 只替换 read_file 工具名，其他原生工具调用共享二进制读取时没有经过同一 Policy。
- 主机新增 GovernedReadMiddleware，由图工厂的服务器验证范围注入，不接受客户端 JSON 选择。共享文件及 Skill 成员 read/read_bytes 在该上下文中使用原 read_file Action、当前成员、持久 Policy 和 Audit；原有资源、路径、文件身份检查保留。上下文穿过既有异步/线程桥，legacy read_file 内部读取不重复建 Policy。每次原生读取仍记结果：Office inspect 的读取和授权复查是两次实际读取，使用同一请求决策、两条结果，不把它们误记为两次模型调用。
- 首个真实任务实际执行成功，但严格模式 GET state 返回 500，阻断完整验收。SDK threads.read 重建图时没有新执行凭证；修复使用 SDK 服务端只读运行上下文重建原 lead 图结构，避免消费执行凭证或加载当前 Agent/Skill 资源。客户端同名配置不能取得这个例外；新执行和状态写入口仍校验身份。隔离检查同时核对节点、状态通道及待执行节点保持，真实任务随后直接复核，零新增模型提交。

## 正向与约束验收

| 场景 | 实际证据 | 范围 |
| --- | --- | --- |
| 资源内 Word → inspect/create/present → 下载/新登录历史 | real-binary-task-current.json | 真实配置模型；原任务运行 success、无待执行节点；不是模拟模型 |
| 读取前 Policy Audit 写失败 | real-binary-faults.json 第一例 | 实际 PostgreSQL 租户限定触发器命中；无决策/审计残留，工具 unavailable，正文标识不返回 |
| 读取后结果 Audit 写失败 | real-binary-faults.json 第二例 | 实际读取已发生，持久 allow 决策保留；结果不交付模型，不能称“未发生读取” |
| 身份不符、作用域复位、嵌套桥、正常 Office 保留 | reader-related / history-topology | 隔离 SQLite/工具/图检查；不等同真实远端或业务服务 |
| 当前镜像相关集成 | reader-image-related-cwd | 默认容器权限、无网络；含真实文件格式操作和原权限边界 |
| 来源升级/回退 | upgrade-final.json | 固定宿主适配层及任务验收入口，旧/当前/回退来源；各次范围见 receipt |
| 服务重启、上一已验收镜像回退、重应用 | runtime-cycle-current.json | 新 Word 与此前中文 PDF/PNG 的实际下载哈希、运行状态、历史、ACL 保持；零新增模型任务 |

Policy 故障触发器已清理，试点及严格图上下文恢复 off，六个既有服务保留。密钥、配置、完整诊断流仅保存在忽略的私有 runtime；公开材料仅测试内容、标识及结果。主机和镜像代码一致性见 runtime-image-history/final-runtime。

## 证据解释与复用

保留所有失败。`binary-policy-fixed` 是最初修复的单例通过；`reader-scope-regression-v2` 中失败来自对 Office 授权复查审计条数的错误断言，修正期望后通过。无 v2 的 reader-scope-regression 是命令参数顺序错误，没有启动测试。`reader-image-related` 是容器工作目录错误，没有启动测试，cwd 版才提供镜像验收。首次生命周期核验误以为共享线程的 PNG receipt 自带 thread_id，在首轮重启后的核对阶段停止，未切换镜像；修正引用共同 PDF 线程后保留 current 结果。首次 SQL 探针引用了首轮未完成 receipt，断言即停止，未安装故障；current 版使用已完整验收的同一任务。

首次真实任务的 500 以及修复前升级记录均保留；real-binary-task-current 是原任务核验，不是重新执行。reader-related 的文件、成员、资源与旧 ticket 覆盖输入在历史修复后保持；图工厂变化另由 history-factory-regression、history-topology、当前镜像及最终来源探针覆盖。2453/18 的旧完整后端和旧前端证据只作为各自未变范围基线，不算本轮完整回归或远端 CI。

## 行为差异与未完成边界

原生 Office 任务能力保留。仅服务器授权的受控诊断读取增加持久只读 Policy/Audit；关键存储失败时不向模型返回内容，普通 Office 任务不被这个试点开关取消。Agent 暂停阻止新执行，但合法所有者既有文件及历史仍可访问。

本块不宣告全部 O21/O26 或 M1 通过：其他命令/工具运行入口、完整专家/子 Agent、Office 高级能力、真实远端/外部业务运行、原五道门最终裁定及远端 CI 仍按原计划推进。此处没有将“尚未接入”写成“已删除”，也未把全部工具统一声明为 read_file 治理已验收。
