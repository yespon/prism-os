# 范围及剩余接缝

本批为已确认 Native Agent 的原 `read_file` / `ls` 具体成员访问接缝。实际 ToolRuntime 结合原 HTTP 创建、原登记与真实文件，允许路径得到同次安全读取内容；禁用、成员/租户/Agent 撤回、实例变化、未选择同名来源、符号链接、完整成员变化、目录替换、路径绕过、钩子缺失与读取后选择变化均拒绝。目录最多两层，宽目录投影选择，已登记嵌套来源不继承父资源授权。

不证明完整 Sandbox、任意代码执行、挂载与所有工具均已隔离。原 bash 在本地允许 Skill 绝对路径并映射到共享根，容器行为仍由原 Sandbox 执行；这些路径尚未接本批读取钩子。`tools.py` 的 `validate_local_bash_command_paths`、`replace_virtual_paths_in_command` 与 `bash_tool` 是下一批必须审查的原接缝，不通过字符串过滤宣称任意命令安全。未登记嵌套来源/未知内容与旧共享/个人目录重叠还需核对。

没有 Native ID / 旧绑定 metadata 的 default、terminal、legacy 语义保持原路径，明确列为未迁移；原普通用户数据工具相邻回归保留。宿主读取依赖原 graph 已消费 capability 的可信上下文，当前成员钩子不增加新的可持久执行身份；自动来源与事件条件在运行中仍需受保护上下文、撤回/取消/unknown 验收。真实 Gateway 证明启动/认证/原生命周期，不替代 N04 真实模型/外部 Tool/工单次数。

完整成员复制/分享和目标重授权、结果历史 ACL、普通聊天/人工线程续接具体实例、原 C3–C5/33 非 Skill/18 专家子 Agent/独立 Office及外部运行/MCP继续原队列。完整C2/N09/M1未退出，N04/N07-B为P0，N08持久执行/委派未启动；N01–N15/O01–O42/F01–F12与原PrismOS设计、能力及退出门保持。
