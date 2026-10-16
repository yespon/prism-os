# PPTX 当前授权图片插入（2026-10-16，Asia/Shanghai）

沿用 codex/octop-integration / 0ba4466，继续原独立 Office 能力；完整原 N/O/F、PrismOS 目标和退出门保持。M1/N04/N07 待验，N08 不启动。

## 已可使用

原 office_pptx 新增 add_images 操作，images 参数包含 1-based slide、当前授权 source_path 和可选 left_inches/top_inches/width_inches/alt。PNG/JPEG 通过已有规范化器应用 EXIF 方向并清除元数据，嵌入真实 PNG，保持纵横比。图片置于已有内容之后的图层；不会自动排版或避让已有形状。

默认位置 0.7/1.6 英寸、宽 6 英寸。有限正宽与非负位置、完整图片须在幻灯片内；拒绝布尔/NaN/无效页码/未知字段/矢量或动画输入。每次最多 16 张，单张原图 4 MiB、原图/规范化总量各 8 MiB，整份文稿最多 64 个图片形状，保留原包体/展开/结构限制。

原文稿及全部图片来源在处理后再次核对当前权限，复用 owned_office_operation 的来源核验、新输出独占创建和发布。越界图片、跨用户下载、成员处理中撤权和覆盖输出均回归。模拟授权夹具只证明本地治理接缝，不等于真实模型调用。

## 具体使用

对已有有权访问的 source.pptx 调用 office_pptx(action="add_images", source_path="/mnt/user-data/outputs/source.pptx", output_path="/mnt/user-data/outputs/pictured.pptx", images=[{"slide":1,"source_path":"/mnt/user-data/uploads/figure.png","left_inches":1,"top_inches":2,"width_inches":3,"alt":"统计图"}])，随后使用原 present_files 展示。

返回实际新文件路径、字节数和摘要；拒绝/不确定结果仍是 unavailable / inspection_required / retry=false，不自动覆盖或重试。

## 当前验收范围

- 相关集成 90 项通过，涵盖所有直接引用 PPTX 的历史测试以及共享图片规范化；精确结果与时长见 validation.json 和原始日志。
- 实际图片像素、DrawingML 位置/宽高/alt、图片去重与形状 ID、其他图表/可编辑 XLSX/备注的部分字节保持，以及原生工具→鉴权下载和处理前/中撤权均有断言。
- 实际隔离 PostgreSQL、当前镜像无网络/default privileges、固定输入 b5→b6→b5，必须各自实际结束为 0 后才允许提交，结果写入 validation.json；不以计划数替代结果。
- demo-pictured.pptx 包含真实插图，另页可编辑图表和备注保留；demo-source.png 为本地生成图片。实际引擎重读和包内容已验证，未做桌面渲染。
- historical-reuse.json 固定 2048 未变输入。office_pptx.py AST 仅原工具函数变化，其余原有函数完全相同；所有直接引用其模块的测试均重新运行。其他宿主能力只按上块相同输入的已有证据复用，未声称本块又跑完整后端/前端。
- 前端、原资源/许可/SDK/worker、宿主依赖锁/迁移未改。当前 WSL N04 测试栈继续固定在已验收的 DOCX 镜像，以便用户完成模型配置；本块不宣称新图片能力已替换该环境。

## 仍待

独立 Office 完整等价仍未退出：图片裁剪/替换/删除、自动布局/复杂版式、桌面渲染、动画、完整图表类型和保真仍待。既有图片作为原文稿内容保留；本块不声称对所有既有图片重新规范化。原本机 TLS 计数接收端不等于真实模型/外部企业工单验收。N04 真实 allow/deny/审批/撤权/故障与五门、N07 远端 CI，以及其他原里程碑退出项均保留。
