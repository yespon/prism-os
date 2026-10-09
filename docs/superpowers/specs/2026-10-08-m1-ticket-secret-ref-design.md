# M1 工单凭据引用与迁移增量设计

日期：2026-10-08。状态：响应脱敏、严格加密、持久 SecretRef 和存储密钥轮换已实现；管理员接口与配置事务绑定已实现；Provider 引用注入和旧配置迁移已完成本地验证；新 head 的隔离 PostgreSQL 验证通过，目标部署与真实模型/webhook 待验。依据：M1 治理设计、能力路线 §12.4 和 M1 退出门复核。此设计仅覆盖工单 webhook；M6 的通用 Secret Provider 与 Connector 生命周期仍按原路线立项。

## 已完成的响应边界

所有 `AlertSourceResponse` 隐藏 `ticket.headers` 的值；URL 含用户信息、查询串、片段或不能解析时隐藏整个 URL。此处理复制配置，不修改数据库。创建拒绝无法回填的占位符；更新只从同一租户查询得到的同一 Source 回填已有 Header/URL。目标地址改变时，不能复用占位 Header，必须显式替换或移除。Header 名称仍可见。此边界不保证任意 URL 路径、模板或其他告警源认证字段不存在 Secret。

## 引用与存储

1. 工单配置使用 `SecretRef`：不可变 ID、schema/version；tenant 由会话与 Source 事实确定，不接受浏览器指定。引用绑定 tenant、Source、`ticket.create` 用途与不可变版本。
2. 加密记录保存完整 webhook URL 和 Header；API、Policy 参数、Audit、Prompt 与投递表仅含引用。Secret-bearing URL 的路径同样必须移入加密记录，不能只处理查询串。
3. 复用现有加密算法与部署密钥，但增加严格方法：缺失密钥、无效密文、错误密钥或无法解码一律拒绝，禁止现有 `encrypt_text`/`decrypt_text` 的明文/原文回退。写入和运行时读取均适用。
4. 引用轮换生成新版本；旧批准不自动绑定新凭据。禁用记录使其立即不可读取。密钥轮换工具须同时处理新记录，且不输出明文或密文。
5. Secret 管理写入口只允许同租户管理员；GET 仅返回状态及不可变引用。输入错误不得回显 Header/URL；Secret 输入字段不得出现在校验错误、请求审计或 OpenTelemetry span 中。

## 提交前注入

Policy context 绑定 SecretRef ID/version 与非敏感模板摘要，不计算低熵 Secret 的公开摘要。恢复时核对引用未替换、权限有效、记录未禁用、租户/Source/用途匹配。关键 Audit 和审批通过后，在提交保留之前检查引用可解析；到真正网络提交前再次读取并核验。注入仅在 Provider 的局部请求变量中存在，不进入 Agent Tool 返回值或持久状态。

Provider 的人工建单与规则 `auto_ticket` 必须能解析同样的引用，才能迁移旧配置；它们仍不计为受控 Agent Action 的治理证据。任何解析失败均不发送请求。网络已提交而响应未知保持现有 unknown 语义，不自动重发。引用轮换与提交的并发语义需显式验证，不能把单次检查当作持续授权。

## 逐任务顺序与验收

1. **响应脱敏及编辑兼容（本轮）**：列表、创建、更新不返回 Header 明文；同源编辑可保留凭据；跨租户和新目标不能借占位符获取或转发旧值。
2. **严格加密与持久引用**：先写缺密钥、错密钥、跨租户、跨 Source、禁用及轮换测试；新表沿唯一 Alembic head 迁移。公开契约只含引用，不暴露存储模型。
3. **写入与读取接口**：管理员创建/轮换/禁用；认证接口只返回引用，错误脱敏。配置更新和引用绑定同事务，客户端不得指定其他 Source 的引用。
4. **Provider 与受控 Adapter 接入**：先拒绝未解析引用，后测试真实 httpx 请求只在最后一刻获得凭据；验证旧批准、撤权、禁用、解析失败、网络超时及幂等。
5. **旧配置迁移**：独立命令，默认 dry-run，仅输出 tenant/Source ID 和计数。显式指定隔离 tenant 后 apply；同事务写加密记录、更新引用、删除明文。密钥不可用时零写入；失败回滚。Alembic 不在无密钥时自动搬迁明文。迁移前备份按目标部署规程执行，备份与恢复不进入普通日志。
6. **兼容与回退**：关闭 Agent Action 开关保留引用和审计；人工/规则路径仍能使用已迁移引用。撤销新代码/表前须检查存量引用，禁止静默恢复明文配置。用隔离库测试升级、迁移、禁用和回退，记录旧路径与新路径的网络次数。
7. **Security Gate**：专项测试通过后仍需真实模型、webhook 和目标数据库演练。完成引用、明文迁移及真实部署证据后，再裁定 M1；当前 M1 未退出。

测试覆盖至少包括：响应脱敏且数据库不被修改、同源回填、跨租户/跨 Source、目标变更、Secret 输入不被错误回显、缺/错密钥、密文篡改、事务失败、轮换与撤销、审批后引用变化、Provider 最小注入、旧路径兼容及迁移幂等。每个任务更新逐任务计划和门禁证据，记录新结果并保留历史基线。

## 任务 2 实施记录

公开 `SecretRef` 只含 v1 schema、不可变 ID、tenant、Source、`ticket.create` 用途及版本 1；每次凭据轮换创建新 ID。工单仓库位于 AIOps 层，使用调用方事务，不独立提交。加密记录包含引用绑定与完整 URL/Header；读取必须满足 tenant/Source/用途/版本/启用状态，且核对密文内绑定，阻止跨记录密文替换。材料对象的 repr 不展示 URL/Header。当前仓库是内部基础能力，调用方的管理员授权将在任务 3 接入。

严格加密方法要求显式部署密钥，不接受明文解密，不对以密文前缀开头的输入跳过加密。缺密钥、错误密钥与坏密文均报不含 Secret 的错误。既有宽松函数的兼容行为保留。存储密钥轮换脚本同时处理新表并维持引用不变；升级到新 head 后才运行该脚本。

迁移 `n8h9i0j1k2l3` 接在 `m7g8h9i0j1k2` 后，仅建表，不自动搬迁旧配置。空表可升降级；表内存在任意凭据时降级拒绝删除，保留版本和数据。SQLite 已验证；新迁移的 PostgreSQL 与目标部署仍待验，此前 PostgreSQL 证据仅覆盖旧 head。

验证：严格加密、仓库及 SQLite 迁移合计 18 项通过；平台契约 130 项及相邻安全测试 48 项通过。SecretRef 尚未进入工单 Provider，旧明文配置仍存在，试点开关保持默认关闭，M1 未退出。

本轮完整后端回归：`1411 passed, 18 skipped, 30 warnings`，零失败；Ruff 和 diff 检查通过。18 个跳过仍为未配置 live/LLM/S3 环境，不替代目标部署验收。

## 任务 3 实施记录

Gateway 新增 `/api/alert-sources/{source_id}/ticket-secret`：POST 创建，PUT 轮换，GET 查询引用及启用状态，DELETE 禁用。POST 接收 `webhook_url` 与可选 `headers`；PUT 还须提交 `expected_ref_id`，DELETE 通过查询参数提交该 ID。所有操作要求认证的同租户管理员；默认关闭的 `PRISMOS_TICKET_SECRET_ADMIN_TENANT` 只允许一个明确选定的租户。响应不含材料；输入通过有界解析和固定错误消息处理，避免校验错误回显 Secret。

创建、轮换在同一事务写加密记录、绑定 Source、移除内联 URL/Header、写关键 Audit；轮换同时禁用旧引用。Source 行锁与完整配置 CAS 防止覆盖并发配置，失败整体回滚。禁用保留绑定与审计。一般告警源配置接口拒绝新增、替换或删除引用，也拒绝引用与内联凭据混用。GET 仅读元数据，不需要解密密钥。

生产 Compose 将部署加密密钥传入 Gateway 与 LangGraph；开发 Compose 继续使用既有 env_file。管理员开关仅在 Gateway 声明。Provider 尚不能消费引用，当前保持管理开关关闭；只在隔离测试 Source/租户验证管理接口，不能在现有投递来源上启用。下一步按任务 4 接入 Provider 和受控 Adapter，随后实施旧配置迁移。

验证：管理接口与响应脱敏定向测试 `17 passed`，包含跨租户、普通成员拒绝、错误不回显、缺密钥、关键审计失败回滚和并发轮换单胜者。完整后端 `1420 passed, 18 skipped, 30 warnings`；Ruff、Compose YAML 结构与 diff 检查通过。新 head 的 PostgreSQL 迁移及 JSON CAS 仍需目标数据库验证；未执行部署或放量，M1 未退出。

## 任务 4 的实施接缝与验证边界

工单目标解析现在返回服务端选定的 Source ID，所有 Signal/RawAlert/Source 查询保持 tenant 过滤且仅选择 active Source。请求上下文对引用配置摘要绑定不可变 SecretRef schema/ID/version/tenant/Source；不解密，也不生成凭据公开摘要。旧无凭据 canary 的 HTTPS/无 Header 限制保留。

Policy 和关键 Audit 通过、审批处于可提交状态后，先检查当前 Source 绑定和凭据可解析，再消费批准/保留提交。Provider 创建客户端后重查请求者和实际目标，重新读取当前 Source 绑定与有效引用，解密仅用于该次 HTTP POST 的局部 URL/Header；配置对象保持引用形式。手工建单和 auto_ticket 复用同一解析路径与引用读取，但仍不计为受控 Agent Action 的治理证据。

SecretRef 被撤销或改变若发生在最后核验之前，则不发送；在最后核验之后已经发出的请求无法撤销，网络/接收端的真实提交结果仍需幂等与 reconciliation。提交 claim 后再次核验失败时保留 unknown，不释放保留或自动重发；当前 M1 状态机不新造生命周期。

HTTPX/HTTPcore 的 request-context 日志隐藏请求细节，其他并发请求的日志不受影响；HTTP 异常不向上暴露原请求链。Provider 回显已知 URL/Header 材料的结果字段被弃用，避免写回事件或 Incident。部署时仍需验证实际 tracing/exporter 与真实 Provider 的错误、响应和脱敏边界。

新增测试使用真实 SQLModel 持久事实、实际 HTTPX Client 与受控 MockTransport；覆盖 tenant/Source/引用绑定、坏密文/缺错密钥、审批后轮换/禁用/撤权/模板变更、claim 后再次核验、并发单提交、超时 unknown、日志/结果/存储及人工/规则兼容。本记录不代表真实模型/目标 webhook/PostgreSQL 或 M1 退出已通过；旧明文迁移另由任务 5 完成。

任务 4 本地验证结果（2026-10-09）：新增 Provider 测试 24 项，相邻合计 83 项；完整后端 `1455 passed, 18 skipped, 30 warnings`；平台契约 130 项与相邻检查 48 项；`make octop-build`（92 项有界后端、类型、Gateway、wheel、生产构建）通过。任务 5 迁移和任务 7 真实环境门仍未完成。

## 任务 5 的实施接缝

命令 `backend/scripts/migrate_ticket_secret_refs.py` 默认 dry-run，要求显式配置、租户和已存在的指定迁移 head；`--source-id` 可重复，`--limit` 默认 100、最大 1,000。独立维护进程关闭查询/驱动日志并仅输出 ID、计数和固定状态。apply 对完整选中批次预检，Source 行锁加完整 JSON CAS，Secret/引用/明文移除/关键 Audit 同事务；其他配置和禁用状态保留。混合引用与明文、无效绑定、缺密钥、审计失败或 CAS 冲突拒绝整批。

已迁移引用包括禁用状态仍可作为存储事实核对，重复 apply 不重新启用、不生成新记录；非 webhook 仅报告待处理，不计为已迁移。提交确认丢失明确返回 unknown/null 数量，重新 dry-run 核对事实；不宣称零写入。迁移前批准失效，新请求重新审批。备份、恢复与开关回退步骤见 [迁移操作规程](../../migrations/ticket-secret-refs.md)，真实环境验收仍待任务 7。

任务 5 本地结果（2026-10-09）：新增迁移/迁移后受控行为 23 项，与相邻用例共 57 项通过；完整后端 `1478 passed, 18 skipped, 30 warnings`，完整前端 94 项；平台契约 130 项、相邻 48 项和唯一 head 通过；`make octop-build` 115 项有界后端及全部构建步骤通过。真实部署迁移、开关回退与 M1 五道门仍待 N04。

## 任务 6–7 的隔离 PostgreSQL 证据（2026-10-09）

`backend/scripts/verify_ticket_secret_postgres.py` 在仅本次测试创建的 PostgreSQL 16.15 容器与持久卷中完成全链升级、空表降级/再升级、CLI dry-run/apply/重复执行、Source JSON CAS、并发轮换单胜者、关键审计失败整批回滚、租户隔离、禁用保持、重启后引用/数据/审计可读、加密备份恢复、非空表降级拒绝，以及迁移前备份恢复后再迁移。容器和测试卷已清理；新入口 `make octop-postgres` 可重复执行，来源记录包含缓存镜像 ID。

第一次镜像下载遇到 TLS 超时，改用已有缓存；首版探针用了不适合重启持久性的 tmpfs，修正为独立卷，并在重启后重新取得宿主端口。最终验证通过，不以初次结果宣布通过。管理员身份由受控 ASGI fixture 提供，不计为真实 Gateway/LangGraph 身份传播。目标部署、真实模型/接收端、实际 exporter 脱敏和开关回退仍待任务 7，M1 未退出。
