# 工单明文配置迁移为 SecretRef

适用：`codex/octop-integration` 的 N03，实现 head `n8h9i0j1k2l3`。命令仅用于独立维护进程，不能注册为 Gateway API 或在服务进程中调用。M1 真实环境门仍待 N04，管理员及 Agent Action 开关继续默认关闭。

## 准备与预检

按目标部署规程备份业务库并验证可恢复性；旧库备份可能含明文凭据，保存在受限位置。先暂停目标 Source 的投递及配置写入，确认 Gateway/LangGraph 和维护进程使用同一业务数据库、同一部署加密密钥。命令从环境取得 `DEERFLOW_SECRETS_ENCRYPTION_KEY`，不接受密钥参数，不输出数据库 URL、Webhook、Header、密文或完整配置。不要把密钥写入命令历史。

显式提供 `--config` 或 `PRISMOS_CONFIG_PATH`，文件必须声明 `database.url`；支持现有整值 `$VARIABLE` 引用。拒绝隐式默认数据库、缺失 SQLite 文件和非指定 head，不自动建表或迁移 schema。`--tenant` 必填；`--limit` 默认 100、上限 1,000，约束所有选中 Source 的数量，超限整批拒绝。用重复 `--source-id` 明确分批，不进行隐式分页或跨租户迁移。

在 backend 目录运行：

```sh
uv run --locked python -m scripts.migrate_ticket_secret_refs \
  --config /path/to/deployment-config.yaml --tenant TENANT_ID \
  --source-id SOURCE_ID --limit 100
```

默认 `dry-run`，不写 Source、Secret 或 Audit。成功输出仅含 tenant/Source ID、固定状态和计数。`eligible` 表示可迁移，`already_referenced` 表示原引用绑定与密文可校验，`no_ticket` 表示无需处理。`unsupported_provider` 明确保留待处理，不计为已迁移；当前实现只支持 webhook。混合引用与明文、无效 URL/Header、悬空/跨租户引用或密钥不可用均拒绝整批。

## Apply 与核对

在相同参数末尾显式添加 `--apply`。同一事务取得选中 Source 行锁，预检完整批次，然后写加密记录、对完整 Source JSON 做 CAS、替换不可变引用、删除 `webhook_url`/`headers`、写 `secret.migrated` 关键审计。任一步在提交前失败则整批回滚，不留下前半批写入。其他 Source 配置、模板、状态和租户数据保留；禁用来源和禁用引用不会重新启用。

独立命令在维护范围内关闭进程及驱动日志，退出时恢复原日志阈值；这是为了防止旧 JSON CAS 参数及异步驱动工作线程暴露明文。此行为不适合在线服务并发调用。实际部署 tracing/exporter 与真实接收端仍须 N04 核对。

成功输出 `status=succeeded` 和确认的迁移数量；提交前失败输出 `status=aborted, migrated=0`，退出码 2。如果提交确认丢失，输出 `status=unknown, migrated=null`，不把已可能提交的数据当作零写入。先在相同数据库重新 dry-run，核对引用、加密记录与 `secret.migrated` 审计，再决定下一步。重复 apply 对已迁移引用不创建新记录、不产生重复审计。

重新读取 Source 确认无内联 URL/Header；人工、规则和受控 Agent 路径均使用同一引用 Provider。迁移改变目标摘要，迁移前批准的请求必须拒绝恢复；新请求重新走 Policy/审批，不把旧批准重新绑定到新引用。停用或回退前核对真实接收端次数及 unknown 提交，不能盲目重发。

## 回退

关闭 Agent Action 开关保留 SecretRef、加密记录和审计；人工与规则路径使用支持引用的版本。若需停用凭据，走管理员禁用接口并核对当前引用 ID。不要恢复内联明文，不直接删除引用记录；非空 Secret 表阻止破坏性 Alembic 降级。制品回退和数据库恢复分别按部署规程验证，恢复旧备份需要相应应用版本与密钥并重新处理批准和投递事实。

## 本地验证边界

SQLite 事务、CAS、CLI、干净错误、密钥缺失、批量/租户边界、幂等、禁用保持、审计失败整批回滚和丢失提交确认有自动化测试。人工/规则使用实际 HTTPX Client + MockTransport，受控路径检查迁移前批准拒绝、新批准单提交；它们不替代真实模型/网络 Provider/目标部署的验收。
