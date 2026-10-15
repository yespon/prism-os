# 独立 DOCX 与当前有权产物读写

2026-10-15，沿用 `codex/octop-integration`、`4b3cf2c`。原 Office 四格式目标中的 DOCX 基础功能块；完整 Office 和 M1 未退出，N08不启动。

## 可用能力

独立实现 `office_docx` 已进入原 builtin 工具目录，不复制任何186个受限 Office 文件。生成真实 `.docx`，支持标题、Normal/Title/Heading1–3、段落、表格、页眉页脚；读取当前有权文档；替换正文、表格、页眉页脚中的文字，保留未修改的包成员与段落/表格结构。跨run替换采用首run字符样式，不能据此声称复杂混合字符样式无损。生成示例：[原文档](demo-original.docx)、[编辑结果](demo-edited.docx)。示例只证明独立引擎，原生权限和实际HTTP下载另有测试。

工具通过原 `current_file_access` 接缝复核当前账号、成员、租户、线程与Agent选择，不接受运行时伪造目录、不回退宿主磁盘读取。解析后、写入前/后与结果呈现均有当前授权；无adapter的独立Harness明确拒绝这一工具。输出限当前线程outputs；原 present_files、鉴权下载、附件和no-store语义复用。

二进制输出通过持有全部祖先描述符、完整暂存写入/fsync及原不覆盖原子发布产生。最终文件在完整写好后出现，既有文件、软/硬链接与替换祖先不能被覆盖；写入/发布失败清理明确归属的暂存。发布后授权丢失保留完整输出并返回 `inspection_required`、`retry:false`，不假称回滚，不自动重发。硬退出留下的隐藏暂存不按超时盲删；本块没有新增恢复/后台执行事实。原文本读写行为保留。

只解析有限ZIP/XML，不执行Office或外部程序。文本替换逐次计算增长上限，单段及全文件文本有界；文本提取、节点数量和树深也有限制，拒绝先分配巨大结果再检查。包大小/展开总量/成员数有限，拒绝重复成员、路径伪造、DTD/ENTITY（含UTF16）、宏/嵌入、外部关系和字段/活动内容。拒绝复杂文档是明确边界，不计功能等价。无新schema、Secret库、授权注册表或Run生命周期，原Policy/Approval/Action/Audit保持。

表格采用有限基础结构；[Microsoft 的 TableGrid 规范说明](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.tablegrid?view=openxml-3.0.1)允许阅读器在缺少显式网格时从内容构造网格。这不构成Word桌面版式验收。

## 实际验收

- 当前相关集成：72 passed, 59 warnings in 54.40s。真实DOCX包、跨run/表格/页眉替换、独立mammoth读取器、原工具schema/注册、实际HTTP产物下载/跨成员拒绝、撤权前后、路径/别名、磁盘中断和不覆盖原子发布均有实际结果；不使用真实模型。
- 完整后端：2284 passed, 18 skipped, 733 warnings in 796.91s (0:13:16)，退出0，2023 固定输入在完整验收期间不变。
- 自有实际PostgreSQL：72 passed, 59 warnings in 86.95s (0:01:26)。Config中的租户/成员/线程/Agent事实使用真实PG；原Auth User夹具为明确自有SQLite身份存储。不是生产DB或真实模型验收，临时容器已清理。
- 最终镜像 `sha256:6e4f43e145729dde35a51658db9d53f5fc3b29580fbee36aea9f22d43168cd4e`，7当前源码/测试文件一致；默认权限无网络：72 passed, 59 warnings in 60.03s (0:01:00)，容器已清理。
- b5→b6→b5：72 passed, 59 warnings in 83.75s (0:01:23); 72 passed, 59 warnings in 78.90s (0:01:18); 72 passed, 59 warnings in 89.87s (0:01:29)，144 固定宿主契约，退出0且宿主未改变。新增工具/测试进入原CI与默认升级清单。
- 原CI Ruff、品牌526原允许项、代码/文档空白门保留，无新豁免。504个未变前端仅复用4b3cf2c继承的完整前端/严格构建/50追踪及既有格式清理范围；来源902成员、原能力制品、锁/清单和provisioner只按各自未变哈希复用。不复用旧完整后端结果。

首轮runner因未建立logs目录未启动pytest，`runner-unlaunched.json`保留；已补创建目录。格式/导入顺序问题修正后才有最终门。初始64项、原子发布69项及规范顺序69项各自原始日志保留。初版完整后端2281通过/18跳过和初版镜像/数据库/三阶段结果保留，压缩源码快照与旧inputs逐字节匹配；审查补文本膨胀及结构上限后以独立bounded门重新验收，不能把初版结果算作当前全量。WSL启动超时不算实际测试，不重复已运行且输入未变的门。原始日志和示例在暂存/提交逐字节核对SHA256，见 `validation.json`。

## 使用与未完成范围

`office_docx(action="create", output_path="/mnt/user-data/outputs/report.docx", document={"title":"报告", "paragraphs":[{"text":"摘要", "style":"Heading1"},"正文"], "tables":[[["项目","结果"],["开发","完成"]]], "header":"内部资料", "footer":"草稿"})`；之后用原 `present_files` 呈现。

`inspect` 指定当前有权source_path；`replace` 另选新output_path并提供literal replacements。既有输出明确拒绝，不因网络/授权未知结果自动换名重发。文档中的外部关系、域/目录、修订、复杂字符格式/布局、图片、Word桌面打开/渲染/导出PDF尚未验收，DOCX完整功能仍待扩展。XLSX/PPTX/PDF独立能力及整个Office目标不据此完成，目录中的原排除与待完成提示保持。

N04真实模型→原受控Tool→可计数工单环境、N07远端CI、真实远端命令/挂载/终止、Browser/交互/Apple、通用Secret、18专家/实际子Agent委派、外部Runtime/MCP及全部原N01–N15/O01–O42/F01–F12、PrismOS M1–M7/Golden/五门仍保留。未推送、发布或部署。
