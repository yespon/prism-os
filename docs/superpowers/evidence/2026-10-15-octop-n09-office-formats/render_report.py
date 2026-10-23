from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
v=json.loads((HERE/'validation.json').read_text())
delta=json.loads((HERE/'capability-delta.json').read_text())
for entry in delta['implementations'].values():
    entry['status']='independent functional baseline accepted in owned local databases/container; full equivalence pending'
delta['acceptance']={'backend':v['backend'],'related':v['related'],'postgres':v['postgres'],'image':v['image']['backend_image'],'upgrade':v['upgrade']}
(HERE/'capability-delta.json').write_text(json.dumps(delta,indent=2,ensure_ascii=False)+'\n')
report=f'''# 独立表格、演示文稿与 PDF 基础能力

2026-10-15启动，2026-10-16接续验收（Asia/Shanghai）。沿用 `codex/octop-integration`、`f7ca429`。完整Office、第一里程碑和全部后续目标未据此退出，N08不启动。

## 可用功能与边界

| 格式 | 当前可用路径 | 尚未完成 |
| --- | --- | --- |
| DOCX | 前块原生创建/读取/替换、正文/表格/页眉页脚、当前权限与原子输出；本块修正发布后撤权夹具并确认数据库实际inactive | 复杂布局、混合字符样式完整保留、域/TOC、修订、图片和桌面渲染 |
| XLSX | 原生创建多个工作表、表头/冻结/筛选、数值/文本与有限显式公式、读取及按A1编辑；实际保留其他表/样式/合并单元格 | 透视表、完整图表/函数、计算引擎、缓存值刷新和高级无损往返 |
| PPTX | 宽版标题/段落/表格/备注、读取和文字替换；未改文字/首run样式保留；新文稿不带打印机二进制设置 | 完整版式/图表/动画/媒体/高级样式往返和桌面渲染；外部输入含打印机二进制设置亦暂拒绝 |
| PDF | 实际文本提取、选页/重复/重排、逐来源授权的合并、可见PNG渲染、Latin-1基础文本PDF | 中文/完整Unicode字体嵌入、OCR、表格识别、填写表单、复杂排版；不执行表单/JavaScript |

`office_xlsx`、`office_pptx`、`office_pdf`进入原builtin工具目录，与原 `office_docx` 并存。所有输入/结果通过原 `current_file_access`，复核当前账号、成员、租户、线程、Agent/资源选择；解析/合并后再次复核，输出复用已验收的持有祖先描述符、不覆盖原子发布和原 `present_files`/鉴权下载。PDF合并逐项检查全部输入，不能把其他线程/宿主文件混入。跨成员下载、撤权前/处理期间、输出路径伪造及未知结果均拒绝交付；令牌不传播进Run，原Policy/Approval/Action/Audit保持。

XLSX普通字符串不会被转为公式；只有显式formula对象支持有限安全函数，外部引用/DDE/网络函数拒绝。读取公式明确 `calculated:false`，没有计算值时不伪造总数。PPTX新建模板去掉未引用的打印机设置关系；宏和任意二进制嵌入拒绝规则保留。ZIP大小/展开量/成员数、流式XML节点/深度、文档文本/替换增长、表格维度、PDF页数/文本/像素均有限制；外部关系、DTD/ENTITY（含UTF16）、重复成员和伪造包路径拒绝。不复制186个受限主Office资源或51个受限外部资源。

PDF底层操作串行使用，未初始化表单执行。生成字体不支持的中文明确拒绝，不能用缺字结果冒充完成。基础PDF的实际像素渲染已验收，不能外推为Word/PPT桌面渲染、任意PDF或实际Office产品兼容性全量通过。

## 实际验证

- 最终相关集成：{v['related']['summary']}。独立读取器/原文件API、实际XLSX/PPTX/PDF字节、页序/合并及非全白PNG像素均核对；原真实租户/成员/线程授权保持。工具schema隐藏runtime，未凭模拟模型算真实模型调用。
- 完整后端：{v['backend']['summary']}，退出0；{v['input_count']}固定输入全程不变。
- 自有实际PostgreSQL：{v['postgres']['summary']}。Config中的租户/成员/线程/Agent事实为实际PG；Auth User夹具为明确自有SQLite存储。原工单/生产数据库未调用，临时容器已清理。
- 最终镜像 `{v['image']['backend_image']}`，{len(v['image']['files'])}当前源码/测试/锁输入匹配；默认权限、无网络：{v['image_tests']['summary']}。实际PDF文本和PNG像素、两类ZIP格式/备注和当前授权均在容器中执行，容器已清理。
- b5→b6→b5：{'; '.join(v['upgrade']['stages'])}，{v['upgrade']['host_inputs']}固定宿主契约，宿主未改变，阶段均退出0。新工具/测试/显式依赖加入原CI与升级契约，原CI完整pytest自动包含新测试。
- 原CI Ruff、品牌526原允许项、代码/文档空白门保留，没有新增豁免。原始日志、四份示例在暂存/提交逐字节核对，见 `validation.json`。

本块显式声明并固定原环境已有 openpyxl3.1.5、python-pptx1.0.2、pypdfium2 5.3.0。实际离线lock/sync通过，全部包版本与f7ca429相同；宿主锁内容因显式声明改变，原清单按当前锁重新生成/验证，不能复用旧锁/旧依赖清单结论。902原始迁入成员、外部来源、实际wheel/sdist、完整静态清单均新运行验证。当前锁/元数据和未变源码的范围分开保存。

504未变前端输入仅复用f7ca429继承的完整前端/严格构建/50追踪及既有格式清理范围。原provisioner实际HTTP仅按未变服务源码哈希复用；不代表当前真实集群。旧完整后端不复用。

## 中间结果与真实撤权修正

初版综合结果7失败/88通过全部来自PPTX默认打印机二进制配置被正确拒绝；原日志保留。确认引擎自带该未引用配置后，仅在新建文稿中去除其关系，二进制/宏拒绝门不放宽；之后95项通过。

旧DOCX发布后撤权夹具在运行中的event loop内调用asyncio.run，历史日志有未等待协程警告，实际只证明发布后异常保持unknown，不能算实际成员已撤回。本块改用原 `_run_async`，额外查询确认数据库status=inactive，且保留完整输出/拒绝交付；当前相关、PG和镜像真实通过，历史日志不改写。三格式解析/合并中撤权也由实际原数据库事实验证，当前99项结果不再出现该夹具警告。

## 演示与未完成退出项

[表格](demo-budget.xlsx)、[演示文稿](demo-slides.pptx)、[PDF](demo-report.pdf)、[实际PDF页面PNG](demo-page.png)为纯引擎生成/编辑/合并样例；原生权限、撤权和实际下载另有集成测试，不拿样例代替真实用户/模型运行。

原目录的Office排除/待完成提示保留，以上是宿主独立基础能力，不是四类受限源码已迁入或完整Office等价。后续继续高级Office、完整专家/子Agent及外部运行接缝；所有N01–N15、O01–O42/F01–F12和PrismOS M1–M7/Golden/五门目标保持。M1仍待N04真实模型→原受控Tool→可计数工单、远端真实命令/挂载/终止及全部工具、N07远端CI等；缺配置不抵消其他实施。通用Secret仍依原N10/M6，N08持久执行/委派不提前启动。未推送、发布、部署。
'''
(HERE/'README.md').write_text(report)
p=ROOT/'docs/superpowers/plans/2026-10-14-octop-functional-milestones.md'
s=p.read_text().replace('独立DOCX基础读写/实际下载已接入并本地验收；','独立四格式基础读写/实际下载已接入并本地验收（PDF生成Unicode/OCR/表单等高级能力仍待）；')
marker='2026-10-16：沿用f7ca429接入独立XLSX/PPTX/PDF基础功能块'
if marker not in s:
    s+='\n'+marker+f'''，[证据](../evidence/2026-10-15-octop-n09-office-formats/README.md)记录{v['backend']['passed']}完整后端/{v['backend']['skipped']}跳过、{v['related']['passed']}相关/实际隔离PostgreSQL/默认权限镜像与{v['upgrade']['host_inputs']}固定契约三阶段升级回退。真实XLSX数值/字面文本/未计算公式与编辑保留、PPTX正文/表格/备注及PDF选页/合并/可见PNG像素走原文件授权与原子输出；当前成员撤权前/处理中拒绝交付。旧DOCX发布后夹具仅generic unknown的历史边界明确保留，当前已实际写入并查询inactive成员；不改写旧日志。显式声明原有三引擎，离线锁定/安装包版本不变；当前源/外部分发/清单/wheel/sdist新核对，504未变前端与provisioner仅按范围复用。完整Office高级能力（含PDF中文字体/OCR/填表）、专家/委派、外部接缝和全部原目标/退出门保留；M1/N04/N07未退出，N08不启动。\n'''
p.write_text(s)
print('Updated existing milestone status and actual format evidence only')
