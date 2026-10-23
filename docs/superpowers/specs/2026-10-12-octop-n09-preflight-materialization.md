# N09-B：预检展示、安装事实与派生格式包

基线 `06875f8`，2026-10-12。承接 N09-A。保留完整 N09 安装/ACL/复制/撤回/脚本 PEP/18 专家实际行为与委派目标；M1 未退出，不实施 N08 生命周期。

本批在创建/编辑专家界面加入按需资源预检；明示全量成员、格式/依赖/绑定缺口、四项 Office 独立实现、来源 digest 与当前可见安装记录。切换模板/语言/租户/关闭立即丢弃旧结果并中止请求，失败可重试。预检不修改 Agent 草稿或安装标记。

查询安装事实只读取 TenantSkill 的当前租户 shared/current-user 行及 public 源目录，不调用会 ensure_user_config 写入的聚合查询。固定 personal/tenant/public 根、拒绝路径别名或不可信 install_dir，不返回绝对路径/内容。记录状态和全部成员摘要都匹配才标识 source_match；同名但内容不同/缺失/来源不明/禁用分别显示，匹配文件仍不代表资源已绑定、依赖就绪或执行获权。

原样来源保持不变。三处已知格式差异通过有限映射派生宿主 SKILL：Tencent Cloud Infra→tencentcloud-infra、file_reader→file-reader、tcapi 的扩展键保存在 metadata 下。其余合法 Skill 保留原字节。派生包逐成员记录原/宿主 SHA 与固定 revision，并随附固定上游根版权文本 `LICENSE.octop` 及其摘要；该摘要同时匹配 b5/b6 来源收据。使用原严格 validator 在临时空间校验，GET 鉴权下载 ZIP。未知适配、受限资源、篡改、版权文本缺失/篡改/别名、路径/标识无效拒绝；下载不安装、授权或执行。

修复原个人导入调用的 unsupported is_custom/tenant_id 参数，以已有 target_relative_path=tenant/user 落入原 personal 目录，保留已有 DB/冲突/回滚语义。通过真实 archive/installer/SQLite 记录测试，不以 mock 参数接收器证明接口可用。

验收：18 专家预检显示；27 个 retained Skill 派生包均经原 validator；三个差异源字节不变；导出/原个人导入实际可用、租户/用户隔离、同名冲突/缺文件/篡改/禁用与无配置写入；UI loading/error/retry/locale/tenant/template/close 的晚响应失效；原完整构建/制品/升级回退门继续通过。本批不自动批量安装，不把 USER/MEMORY 静态种子共享成活跃私有资料，不宣称 N09 或 M1 完成。

构建接续修正：在本机同时保留 Next 编译图并运行类型 worker 时出现内存/交换压力。正式 build/preview 入口先用 `next typegen` 生成当前路由契约，再严格 `tsc --noEmit`；通过后只在该子进程跳过重复 Next worker，直接 Next 命令默认仍执行内置检查。页面生成 worker 固定为 2。以真实路由不合法返回类型验证失败在编译前阻断，生产源码与独立检出分别构建，既有类型门不放宽。
