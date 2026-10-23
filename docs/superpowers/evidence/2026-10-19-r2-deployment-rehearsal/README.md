# R2 部署演练：知识闭环与撤权失效（2026-10-19）

分支 `codex/octop-integration`；R2 后端镜像（含知识五表、检索/引用、knowledge.search 装配、参考 Connector）。N04 WSL 栈：真实 HTTP 登录、PostgreSQL、迁移 `o9i0j1k2l3m4 -> p0j1k2l3m4n5` 真实执行。

## 演练一：五场景闭环（run_rehearsal.py，complete: true）

1. **kb-created**：POST /api/knowledge/bases 创建私有知识库（真实认证+租户上下文）
2. **document-ready**：上传 Markdown 运维手册 → 内联管线（解析/分块/嵌入分派/索引）→ `index_state=ready`
3. **private-kb-invisible-to-nonmember**：同租户非成员列表不可见、文档 404
4. **grant-revoke-cycle**：owner 经 members 端点授权 → 成员可读（200）→ 撤权 → **即时 404**
5. **delete-invalidates**：删除文档后状态 404

## 演练二：真实模型带引用回答（run_cited_answer.py）

目标：绑定 KB 的 agent 经认证 LangGraph 代理回答 runbook 问题，流中出现引用标记。

### 过程中发现并修复的两个真实缺陷（保留记录）

1. **知识路由挂载前缀错误**：`/knowledge` 而非网关约定的 `/api/knowledge`——演练 404 暴露；create_app 的 `_IncludedRouter` 包装使路由清单探查失真，真实 404 是可靠信号。已修（路由前缀对齐 files 约定）。
2. **agent meta_info 丢弃**：创建端点只存模板溯源元数据，调用方的 `knowledge_base_ids` 落不了库 → `knowledge.search` 从未装配 → 模型只能泛答。AgentCreateRequest 已接受 meta_info（溯源键保持服务端独有不可覆写）。252 项 agent 相关测试通过。

### 状态：通过（complete: true, citations_in_stream: true, mentions_rotation: true）

修复链完整后重跑：真实模型 `gpt-5.6-luna` 经认证 LangGraph 代理，绑定 KB 的 agent 调用 `knowledge.search`，
回答流中出现 `prismos-kb-citations` 引用标记，且回答内容（每季轮换、先 dry-run）来自上传的 runbook。

修复链共三处（全部由真实演练逐层暴露，每处独立提交）：
1. 知识路由前缀（`/knowledge` → `/api/knowledge`）
2. 创建端点丢弃 meta_info（AgentCreateRequest 接受并合并，溯源键服务端独有）
3. AgentConfig 转换丢 meta_info + 字段定义因编辑脚本半途失败而缺失（容器内 AttributeError 暴露）

## 边界

- 嵌入分派未配置租户 embedding 模型 → hash 向量降级（语义检索质量受限，机制闭环完整）
- 撤权即时失效经 HTTP API 端到端验证；`knowledge.search` 工具级的撤权反例在契约测试（test_knowledge_tools / test_knowledge_retrieval）
- 秘钥与模型原始回复仅在私有 runtime；公开 receipt 只含状态与 ID
