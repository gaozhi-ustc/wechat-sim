#!/usr/bin/env python3
"""LOCAL archive documentation only; no project imports, runtime or target access."""
from pathlib import Path
import os, hashlib, re, json
A=Path('/tmp/wxview92/wechat-sim'); S=A/'snapshot'; R=S/'upgrade_20261010T1529'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
intro=(A/'records/agent-introduction.md').read_text()
core=['DELIVERY.md','CONTINUATION_20261010T1620.md','HANDOFF_20261011T0157.md','NEW_ROUND_DELIVERY_20261013.md']
parts=[intro,'\n### 8.1 早期与上轮验收原文（保留历史，不作为恢复许可）\n']
for name in core:
 p=R/name
 parts += [f'\n#### 完整历史文档 `{name}`\n\n归档路径：`snapshot/upgrade_20261010T1529/{name}`；archive SHA-256 `{sha(p)}`。以下正文为该阶段原文，后续有效纠偏和当前暂停优先。\n\n',p.read_text(),'\n---\n']
handoff=(R/'CURRENT_HANDOFF.md').read_text()
heads=[m.group(1) for m in re.finditer(r'^## (.+)$',handoff,re.M)]
parts += ['\n### 8.2 历史阶段导航（从早至晚；原日志正文仍保留原顺序）\n\n']
parts += ['- '+h+'\n' for h in reversed(heads)]
parts += [f'\n### 8.3 全部累计 CURRENT_HANDOFF 正文（原来倒序，历史断言不自动生效）\n\n源路径：`/tmp/wxview92/upgrade_20261010T1529/CURRENT_HANDOFF.md`；归档SHA-256 `{sha(R/"CURRENT_HANDOFF.md")}`；{len(handoff.splitlines())}行。2026-10-14 21:15暂停发生于原文最后21:13条之后，见本入口置顶及records/pause-and-children.md，不能沿正文最新“继续现场”执行。\n\n',handoff,'\n---\n']
parts += ['\n### 8.4 全部开发/实施/测试/独审/部署/故障文档索引\n\n每条是真实复制文件，source/归档字节差异见copy-manifest。原文时间来源不同可能相差约一小时，不擅自校正统一。Markdown按原相对路径排序，详情链接不是完成断言。\n\n']
docs=sorted(S.rglob('*.md'))
for p in docs:
 rel=str(p.relative_to(A))
 parts += [f'- [{rel}]({rel}) — {p.stat().st_size} bytes，SHA-256 `{sha(p)}`\n']
parts += ['\n### 8.5 原始证据与未完成候选索引\n\n所有源码/测试/日志/图片/模型/ABI reference/fixture和大JSON实际位于snapshot同路径。非Markdown逐项依据见 [records/copy-manifest.jsonl](records/copy-manifest.jsonl)，不是只链接外部绝对路径。49文件经授权值脱敏，脱敏版不得替代原始不可变hash证据；原source SHA同时保存。\n\n',
'- 最新终态：`snapshot/ocr_first_terminal_readonly_1791982429309891739.jsonl`。\n',
'- CP无输入关闭：`snapshot/cp14_v3_embedded_close-noinput_1791981463823986058.jsonl`。\n',
'- 当前计时原始anchor：`snapshot/direct_live_msg_mv6nn1hjqjrlfm6nuy9_start.json`；原request：`snapshot/ocr_first_original_request_20261014.json`（未审批）。\n',
'- 上轮真实覆盖及计时：`snapshot/db13_round_final_report_20261013T0603.jsonl`；该轮有10confirmed，不是本轮0发送。\n',
'- 未批准首viewport：`snapshot/ocr_first_viewport_20261014/`五files（RESULT/evidence/layout/source/test）。\n',
'- tail待审候选：`snapshot/ocr_first_tail_20261014/`（RESULT与red/green/diff/integrity/test/source）。\n',
'- launcher被停候选：`snapshot/ocr_first_launcher_20261014/`四files（没有最终RESULT）。\n',
'- 外部微信计划：`external-plans/`；原path/sourceSHA/archiveSHA见external-file-manifest。\n',
'- 子任务和暂停：`records/pause-and-children.md`、`records/task-terminal.json`。\n',
'- 排除原credential/DB/.git/cache：`records/excluded-files.json`；未读secret，不把其路径引用当真实值。\n',
'- 源工作树的7staged版本：`records/git-staged/`；身份未知/未commit，不把归档当Git提交。\n',
'- 最终文件/权限/哈希/私密检查：`records/final-verification.json`、`records/final-file-manifest.jsonl`、`records/sensitive-scan.json`。\n',
'\n## 9. 暂停收束\n\n本session只完成归档和记录，不恢复微信开发/生产，不继续首个Send，不触碰范围外资产，不自动委派未知session。业务当前新轮仍0clicked/整体未完成。下一session必须先确认接手安排、原始请求区别、当前批准缺口与未来现场状态。本地全部可取得源码/文档/候选/必要证据已复制保存；尚未取得完整人类逐消息历史和远端-only原账/secret，明确缺失而不编造。\n']
content=''.join(parts).encode()
p=A/'agent.md'
with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'wb') as f:f.write(content)
print(json.dumps({'agent_path':str(p),'bytes':len(content),'lines':len(content.splitlines()),'markdown_documents_indexed':len(docs),'handoff_headings':len(heads),'sha256':sha(p)}))
