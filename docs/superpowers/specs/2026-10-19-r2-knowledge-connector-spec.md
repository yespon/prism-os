# R2 Spec：私有知识与参考连接器

**日期：** 2026-10-19
**状态：** 已批准（承接 [R1-B2 接缝草案](./2026-10-19-r1-r2r3-seam-contracts.md) 冻结为 R2 立项 Spec）
**范围：** O19/O20（知识库/记忆引用）、O21（文件）、O23（env/Secret）、O24/O25（Connector）的 R2 切片
**上游基线：** Octop b6 `eb280112`：`infra/knowledge/`（2,275 行）+ `infra/connectors/`
**非目标：** 全量 Connector 目录（O25 剩余目录逐项跟进）；通用 RAG 管理 UI 完整版；M6 完整数据治理

## 1. 交付目标：一条可演示闭环

**上传文档 → 索引 → 带来源引用的回答 → 撤权后不可召回**

验收场景（对应全量复核九组对标场景之 4）：
1. 同租户用户上传文档到私有知识库 → 索引完成（状态可见）
2. 绑定该知识库的 Agent 回答时输出引用（文档 ID、版本/哈希、引用位置）
3. 撤销用户对该库的访问权 → 后续检索不返回该库内容；已生成引用在打开时重新校验权限
4. 删除文档 → 索引失效，检索不再命中
5. 索引失败 → 对用户可见的降级提示（检索跳过，不静默）

## 2. 迁入策略（A/B/C 分类落地）

| 上游模块 | 策略 | 处理 |
| --- | --- | --- |
| `knowledge/service.py` 可见性 + 编排 | B | 逻辑保留；`owner_user_id: int` + `shared: bool` → `(tenant_id, user_id)` + 租户内共享/成员 ACL |
| `knowledge/index.py`（每 KB SQLite 索引） | B | 原样保留（纯逻辑、无身份依赖）；索引文件归入租户存储路径 |
| `knowledge/parse.py`/`ocr.py`/`chunk.py`/`citations.py` | A | 纯逻辑成批迁入 |
| `knowledge/retrieve.py`（检索格式化） | B | `user_id/is_admin` 参数 → 租户成员资格检查；失败降级保留 |
| `knowledge/jobs.py`（索引任务） | B | 中断恢复保留；后台任务携带 tenant 过滤 |
| `knowledge/embed.py` | B | 嵌入模型凭据：R2 用环境配置（不提前泛化 SecretRef，M6 才做通用 Provider） |
| `connectors/`（catalog/builder/probe/oauth） | B/C | Connector 目录定义与实例生命周期迁入；凭据接缝走 SecretRef 扩展的最小用途 |
| `connectors/qcc.py`/`mail_servers.py` 等具体连接器 | 暂不迁 | R2 只做两个参考 Connector（见 §4） |

## 3. 数据模型（Alembic 单链延伸，平台 Owner 串行）

```
KnowledgeBaseRecord     tenant_id, id, owner_user_id, name, visibility(private|tenant), created_at
KnowledgeDocumentRecord tenant_id, id, kb_id, filename, content_type, file_object_id, version, content_hash,
                        index_state(pending|indexing|ready|failed), index_error, indexed_at, created_at
KnowledgeMemberRecord   tenant_id, kb_id, user_id, granted_by, created_at   # 显式成员授权（tenant 可见性之外的收窄）
ConnectorCatalogRecord  tenant_id?, id, kind, schema_json, created_at       # 目录定义（平台级种子 + 租户自定义）
ConnectorInstanceRecord tenant_id, id, catalog_id, owner_user_id, name, secret_ref_id?, status, last_health, created_at
```

不变量：
- 所有行带 tenant；查询经统一 tenant 过滤（含后台索引任务与缓存）
- `visibility=tenant` 是"租户内全员可读"；写/删除仅 owner 或被授权成员
- 撤权 = 删 `KnowledgeMemberRecord` 行 + 该库检索结果即时失效（每次检索查当前成员资格，不缓存授权）
- 引用指向 `content_hash` 版本；打开引用重新校验当前权限（隔离先于检索）

## 4. 两个参考 Connector（M6 退出门的 R2 预付）

1. **Webhook Connector**（无 OAuth）：通用 HTTP 出站调用，凭据经 SecretRef——复用 M1 工单 webhook 的凭据注入接缝
2. **本地 SQLite 分析 Connector**（只读）：复用 10-17 MCP 演练已验证的自建 analytics 服务模式

两个 Connector 通过统一契约测试（标准错误、限流透传、凭据不入日志/Prompt、撤权后调用失败）。

## 5. 端点与权限（Gateway 路由）

| 端点 | 权限 |
| --- | --- |
| `POST/GET /api/knowledge/bases` | 认证成员；列表只返回可见库（owner/tenant/成员） |
| `POST /api/knowledge/bases/{id}/documents` | owner 或授权成员 |
| `GET /api/knowledge/bases/{id}/documents/{doc}/status` | 可见性同列表 |
| `DELETE /api/knowledge/bases/{id}/documents/{doc}` | owner 或授权成员 |
| `POST/GET/DELETE /api/knowledge/bases/{id}/members` | owner（授权管理） |
| `POST /api/connectors/instances` + health + delete | owner 或租户管理员 |

检索不设独立端点：作为 Agent 工具（`knowledge.search`）在受控范围装配，结果带引用进上下文——走既有 Skill/MCP 工具装配边界。

## 6. 治理接入

- `knowledge.search` 只读工具：读路径（对上下文注入）暂不接 Policy PEP（与 `read_file` 治理同级的扩面在后续批次）；但**检索前后权限校验是硬约束**（数据接缝，非 Policy）
- Connector 出站调用（副作用）：接入既有 Policy/Approval/Audit 链（与 `ticket.create` 同一 Adapter 模式）——R2 交付 Webhook Connector 的受控调用闭环
- 每次检索产生 run fact 关联（检索预算与引用进 R1 的 RunFact attributes）

## 7. 依赖预授权预案

- 嵌入链若需 langchain 1.x → 隔离能力 Worker（嵌入计算独立进程，经协议回传向量）
- 索引 SQLite 依赖无冲突（标准库）
- OCR（若启用）依赖单独评估；R2 先支持纯文本/Markdown/PDF 文本层

## 8. 测试与验收门

1. 契约测试：五场景（§1）+ 跨租户反例 + 撤权即时失效 + 删除失效 + 索引失败降级可见
2. 双层回归：迁入模块行为（上游逻辑改写测试）+ PrismOS 治理（tenant 过滤、现有能力不回退）
3. 迁移：新表 SQLite 升降级 + 非空降级保护；PostgreSQL 目标部署验证
4. 真实部署：N04 栈真实模型 + 真实文档闭环演示（§1 场景 1–5 全过）
5. 两个 Connector 契约测试全绿 + 撤权反例

## 9. 节奏（2–3 周，R0 实测成本校准）

| 周 | 交付 |
| --- | --- |
| 1 | 数据模型 + 迁移 + KnowledgeService/parse/chunk 迁入 + 上传/索引闭环 |
| 2 | 检索 + 引用 + 撤权/删除失效 + knowledge.search 工具接入 |
| 3 | Webhook Connector + SQLite 分析 Connector + 契约测试 + 真实部署演练 |
