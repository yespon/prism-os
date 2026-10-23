# N09-A：来源资源声明与只读预检

2026-10-12，基线 `fddc307`。本批实现 N09 的第一步：已许可保留资源的最小声明、逐文件和 bundle digest、现有宿主 Skill 格式检查。N05/N06 前置已验证。N08 的快照/执行绑定和 M1 真实门尚未完成，本批不启动生命周期，也不安装/授权/执行任何资源。

复用 prismos_octop 来源收据与目录；expert 的 skills/agents/scripts、参考资料、知识种子与 USER/AGENTS 模板等辅助文件全部声明；manifest 与已声明 persona prompt 另列为 template_members，subagent 模板本身给出来源/prompt 摘要且不虚构配套文件。文件只从固定导入成员读取，拒绝目录别名、未声明/被改字节、遍历或未知 ID；声明 digest 用排序后的相对路径+SHA，和语言、时间、机器路径无关。来源 commit 与 digest 分开保留。

`GET /api/agent-catalog/templates/{template_id}/resources?locale=zh|en` 继续使用原认证/租户入口，返回 schema、来源、逐项资源/member 摘要、已排除资源及格式预检。Skill 检查调用现有 harness validator；compatible 只表示源 frontmatter 符合该验证器，不能推断已安装、依赖具备或已获权限。脚本/子 Agent 仍要求未来 tool/schema/PEP/Sandbox 与委派绑定；MCP/外部依赖、名称冲突、当前资源拥有/共享/撤回尚未核对，明确标记未检查。整体 installation_checked/execution_ready 为 false。

绝不放宽原 Skill validator，不改原样来源字节，不执行脚本/插件，不复制凭据，不将 API 读成功写成 bundled_resources_installed。源数据变更仍通过 compare/import/receipt/制品与升级门。四个受限 Office 子树继续显示独立实现待完成，不把删除源文件当作能力完成。

验收：18 专家逐个覆盖全部资源文件/摘要/来源；语言不改变 bundle 内容标识；未知/恶意 ID、缺认证/租户、篡改/新增/符号链接拒绝；合法 Skill 与格式不兼容 Skill 均显示真实结果；数据库与配置不写入；wheel 与 b5→b6→b5 保留新宿主模块并通过同样契约。原 N09 后续安装/资源 ACL/复制/升级/18 专家实际行为、两个资源专家与一个子 Agent 委派仍需逐项完成。
