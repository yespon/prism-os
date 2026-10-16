from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
v=json.loads((HERE/'validation.json').read_text())
assert v['complete']
r=v['results']
c=v['composite']
backend_line=f"{c['passed']}通过/{c['skipped']}跳过（{c['unchanged_non_font_passed']}个未变非字体节点+{c['current_font_passed']}个当前字体节点，按范围合成闭合）"
diagnostic = ('本块先前完整后端日志保留SQLite夹具的120秒faulthandler耗时诊断；随后继续推进并实际退出0，未修改夹具或重启该验收；具体耗时原因未裁定。' if v['backend_full_faulthandler_notices'] else '当前全量未触发120秒faulthandler耗时诊断。')
body=f'''# 原生 PDF 的授权字体与水平 Unicode/中文文本

2026-10-16（Asia/Shanghai），沿用 `codex/octop-integration` 与 `b6b886c`。

## 可用功能和用户路径

原 `office_pdf` 创建操作新增可选 `font_path`：上传字体→返回原虚拟路径→创建PDF→原鉴权下载/呈现。字体必须是当前有权读取的TTF或TTC首个face；不查找隐式宿主字体。原账号/成员/租户/线程/Agent/资源权限在读取、处理后、原子输出和交付前继续复核。原Policy/Approval/Action/Audit未替换。

指定字体后可嵌入实际字体程序，生成已验证的水平预组合希腊文/俄文/中文等文本；没有字体时保持原Latin-1基本路径。输出携带实际源字体SHA256。缺少字形、受限/bitmap-only嵌入标志、格式控制/代理字符、RTL及非零组合音标明确拒绝。完整复杂脚本整形、自动换行、字体选择/子集化、CFF/OTF、OCR/表单/高级排版仍待；不能以本块推断所有Unicode脚本的排版正确性。

字体最多32MiB，校验TrueType表、Unicode cmap4/12、字形范围和偏移；重复映射只解析一次，多映射合计最多100000条，复制的字体表总长度不得超过输入长度。保留原PDF页数/行数/字数/页宽/文件大小/像素边界及不覆盖原子发布。缺字不静默退回其他字体。

## 实际验收

- 当前字体相关：{r['related-final']}，包括真实HTTP字体上传→原生工具→下载，当前成员/跨线程/宿主路径和处理中实际撤回。
- 当前后端按范围闭合：{backend_line}；{v['frozen_inputs']}最终固定输入。不是一次当前源码的全量运行。
- 自有隔离PostgreSQL：{r['postgres-final']}。成员/线程/资源为实际PG；原Auth夹具继续自有SQLite范围，不代表目标N04。
- 当前默认权限、无网络镜像：{r['image-runtime-final']}；`{v['image']}`，{v['image_file_matches']}当前文件一致，容器已清理。只有公开的固定测试字体作为单文件只读挂载，测试复制到当前线程uploads后才经原生授权读取；没有生产用户资源、凭据或Docker socket挂载。
- b5→b6→b5：{' / '.join(r['upgrade-final'])}；{v['upgrade_inputs']}宿主契约固定，宿主未变。
- 两个独立PDF栈验证中文：PDFium实际文本/可见PNG；Poppler实际 `pdftotext`、`pdffonts`（embedded=yes、Unicode=yes）及PNG渲染。最终PNG与已目视核对的中文页面像素相同；没有缺字方框。

HTTP上传的sandbox获取仅为local存储夹具接缝，不是实际远端sandbox验收。真实模型、外部工具和工单没有调用，不能计为N04。前端、外部SDK worker及来源/制品/清单/provisioner仅按未变输入范围复用；宿主锁与全部引擎版本未变。原CI静态、品牌和空白门保留，没有新增豁免。

{diagnostic}

## 初始结果与累计规模修正

初始完整后端/PG/镜像/升级都等待实际终态后保留，代码和输入保存在 `source-initial.tar.gz`/`source-initial.json`/`inputs-initial.json`。复核以两份各60000条有效范围的合成cmap元数据复现：初版接受合计120000条。未进行内存耗尽或native字体执行。

在本功能块内加入全局预算和重复映射去重；新增回归在native解析前拒绝该输入。cmap预算修正后的完整后端/PG/镜像/升级已实际通过。随后以表别名元数据复现了复制总量放大，补齐总表长度预算；最终仅font_coverage函数体改变，既有字体测试AST不变并追加一项回归。所有字体节点、当前真实HTTP授权链、PG、镜像和升级对最终源码复验；未受影响节点按full-reuse-scope.json的函数/文件/节点边界复用，当前后端以两个明确范围闭合，不宣称又运行一次全量。所有初始日志和示例保留，最终文件另外命名。

## 演示、来源和未完成边界

[最终中文PDF](demo-chinese-final.pdf)、[PDFium页面](demo-chinese-final.png)、[独立Poppler页面](demo-poppler-final.png)。这是实际格式/本地原生入口验收，不是Office桌面、OCR、真实专家模型行为或外部服务验收。

NotoMono原始二进制仅作可重复测试输入，源包声明OFL-1.1，SHA/完整版权通知留在tests/fixtures/pdf-fonts。中文验收使用既有系统WenQuanYi字体，源包版本/SHA及声明的Font embedding exception/M+通知保留在demo-final.json和cjk-font-copyright.txt；没有把系统字体设为工具默认或复制为Octop来源。调用者仍须提供当前有权使用的字体文件。

backend/tmp的现有上下文、测试与复现资料均保留，仅从Git和宿主Docker上下文排除。完整N01–N15、O01–O42/F01–F12及原PrismOS M1–M7/Golden/五门保持。第一里程碑仍待真实模型→受控工具→可计数工单、真实远端命令/挂载/终止与全部工具、N07远端CI等；N08持久执行/委派不启动。完整Office、专家/子Agent和外部业务接缝继续推进，未推送、部署、发布。
'''
(HERE/'README.md').write_text(body)
message='\n2026-10-16：沿用b6b886c接入原生PDF的授权TrueType/TTC字体与水平Unicode/中文文本，[证据](../evidence/2026-10-16-octop-office-pdf-fonts/README.md)包含原HTTP字体上传→工具→下载、当前授权/撤权、实际字体嵌入与两个独立PDF栈中文文本/像素，以及修正累计cmap规模后的当前后端分范围闭合/隔离PG/镜像/升级回退。初始全量终态和源码快照保留，修正后按新输入验收；宿主锁未变，backend/tmp仅排除于Git/构建而保留本地资料。完整复杂整形/自动排版/OCR/表单和完整Office等目标保持，原M1/N04/N07退出及N08前置门不变。\n'
for name in ['2026-10-14-octop-functional-milestones.md','2026-10-09-octop-next-iterations.md']:
 p=ROOT/'docs/superpowers/plans'/name
 assert message not in p.read_text()
 with p.open('a') as stream:stream.write(message)
p=ROOT/'docs/superpowers/plans/2026-10-14-octop-functional-milestones.md'
s=p.read_text().replace('PDF生成Unicode/OCR/表单等高级能力仍待','PDF水平Unicode/中文已验，复杂文字整形/OCR/表单等高级能力仍待',1)
p.write_text(s)
(HERE/'capability-delta.json').write_text(json.dumps({'base_commit':'b6b886c','source_imported':'No excluded Octop Office source imported; immutable OFL NotoMono test asset with provenance/notices','functional_integration':'Original office_pdf explicit current-authorized font_path, native upload/owned creation/download; horizontal precomposed text/CJK','actual_local_acceptance':r,'independent_pdf_checks':['PDFium text/visible Chinese PNG','Poppler text/embedding facts/visible Chinese PNG'],'remaining':['Full complex-script shaping, wrapping and advanced typography','OCR/forms and full Office fidelity','Actual expert/delegation/external runtime and original platform goals','N04 real model/tool/countable ticket, real remote and N07 remote CI'],'M1_exited':False,'N08_started':False},indent=2)+'\n')
print('Final font evidence and existing plan status updated')
