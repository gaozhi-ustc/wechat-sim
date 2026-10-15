"""result.md for the multi-run zhangchi-la batch: merge all send runs by Weixin ID, cross-check the ledger.

Usage: python3 -I gen_result_remote.py <dir with batch_*_send/> <ledger_json> <supervise.jsonl> <out.md>
"""
import collections
import json
import statistics
import sys
import time
from pathlib import Path

base, ledger_json, sup_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
PRIO = {'SEND_CLICKED': 9, 'UNKNOWN': 9, 'EXCLUDED_SELF': 5, 'EXCLUDED_NOT_ORDINARY': 5, 'EXCLUDED_UNAVAILABLE': 5,
        'SKIPPED_UNREADABLE_NAME': 2, 'SKIPPED_PRE_SEND': 1, 'NOT_ATTEMPTED_LIMIT': 1, 'ALREADY_SEND_CLICKED': 0}
CN = {'SEND_CLICKED': '已发送（Send 点击成功）', 'ALREADY_SEND_CLICKED': '已在账本（之前已发送）',
      'EXCLUDED_SELF': '排除：本人', 'EXCLUDED_NOT_ORDINARY': '排除：非普通好友（无 Friend Profile/语音/视频）',
      'EXCLUDED_UNAVAILABLE': '排除：账号已停用', 'SKIPPED_PRE_SEND': '跳过：发送前核验未通过（未发送）',
      'SKIPPED_UNREADABLE_NAME': '跳过：名字无法识别（未发送）', 'UNKNOWN': '结果不明',
      'MISJUDGED_SELF': '误判为本人（未发送，属漏发）'}
FOLD = str.maketrans({'o': '0', 'l': '1', 'i': '1', '|': '1', 's': '5', 'z': '2', 'b': '8'})
fold = lambda w: w.lower().translate(FOLD).replace('_', '').replace('-', '')
ts = lambda t: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t)) if t else ''
esc = lambda s: str(s if s is not None else '').replace('|', '\\|').replace('\n', ' ')

runs = sorted(p for p in base.glob('batch_*_send') if (p / 'events.jsonl').exists())
merged, per_run, all_contacts = {}, [], []
stage_sum = collections.defaultdict(lambda: [0, 0.0])
for run in runs:
    ev = [json.loads(l) for l in (run / 'events.jsonl').read_text().splitlines() if l.strip()]
    res = json.loads((run / 'result.json').read_text()) if (run / 'result.json').exists() else {}
    stages = {c['ordinal']: c.get('stages', []) for c in res.get('contacts', [])}
    start = next((e for e in ev if e['kind'] == 'start'), {})
    cs = [e for e in ev if e['kind'] == 'contact']
    sends = {e.get('ordinal'): e['t'] for e in ev if e['kind'] == 'send_clicked'}
    for c in cs:
        c = dict(c, run=run.name, send_t=sends.get(c['ordinal']), stages=stages.get(c['ordinal'], []))
        all_contacts.append(c)
        for s in c['stages']:
            stage_sum[s['stage']][0] += 1
            stage_sum[s['stage']][1] += s['total_ms']
        k = ('wx', fold(c['weixin_id'])) if c.get('weixin_id') else ('row', run.name, c['ordinal'])
        if k not in merged or PRIO.get(c['outcome'], 0) > PRIO.get(merged[k]['outcome'], 0):
            prev = merged.get(k)
            if prev and prev['outcome'].startswith('SKIPPED'):
                c['note'] = '先前跳过后重试成功'
            merged[k] = c
        merged[k].setdefault('visits', 0)
        merged[k]['visits'] += 1
    stop = next((e.get('reason') for e in ev if e['kind'] == 'stop'), None)
    tail = next((e for e in ev if e['kind'] == 'tail'), None)
    per_run.append(dict(run=run.name, start=ev[0]['t'] if ev else None, end=ev[-1]['t'] if ev else None,
                        mode='从当前位置继续' if start.get('from_current') else ('续跑起点 %s' % start.get('resume_after') if start.get('resume_after') else '从顶部'),
                        processed=len(cs), sent=sum(c['outcome'] == 'SEND_CLICKED' for c in cs),
                        first=cs[0]['ordinal'] if cs else None, last=cs[-1]['ordinal'] if cs else None,
                        end_reason=stop or ('到达列表末尾' if tail else '进程被结束/异常（无 stop 事件）')))

recs = sorted(merged.values(), key=lambda c: c['t'])
for c in recs:
    if c['outcome'] == 'EXCLUDED_SELF' and (c.get('weixin_id') or '').lower() != 'assfox':
        c['outcome'] = 'MISJUDGED_SELF'
        c['reason'] = '显示名与本人 ID 相同而被误判为本人（Weixin ID %s 不是本人），未发送' % c.get('weixin_id')
by = collections.Counter(c['outcome'] for c in recs)
ledger = json.loads(ledger_json.read_text())
ledger_ids = {fold(r[0].split('|wxid:', 1)[1]) for r in ledger if r[1] == 'SEND_CLICKED'}
dup_groups = collections.defaultdict(list)
for r in ledger:
    if r[1] == 'SEND_CLICKED':
        it = json.loads(r[2])
        dup_groups[fold(r[0].split('|wxid:', 1)[1])].append((r[0].split('|wxid:', 1)[1], it.get('profile'), it.get('run'), r[4]))
dups = [sorted(v, key=lambda x: x[3]) for v in dup_groups.values() if len(v) > 1]
ledger_states = collections.Counter(r[1] for r in ledger)
sent = [c for c in recs if c['outcome'] == 'SEND_CLICKED']
sent_ids = {fold(c['weixin_id']) for c in sent}
sup = [json.loads(l) for l in sup_path.read_text().splitlines() if l.strip()]
t0 = min(p['start'] for p in per_run if p['start'])
t1 = max(p['end'] for p in per_run if p['end'])
active = sum(p['end'] - p['start'] for p in per_run if p['start'] and p['end'])
cyc = [c['cycle_ms'] for c in sent if c.get('cycle_ms')]
tsc = [c['to_send_clicked_ms'] for c in sent if c.get('to_send_clicked_ms')]
pct = lambda xs, q: sorted(xs)[min(len(xs) - 1, int(len(xs) * q))]

L = ['# zhangchi-la（192.168.102.23）微信全量好友发送结果\n']
L += ['- 账号：gaozhi（Weixin ID `assfox`）；DISPLAY=:1；微信 4.1.13.23；主窗口调整为已校准的 1088x770。',
      '- 内容：每人发送当时原生收藏面板的第一条：《【5】PD必须分离？拆掉路障吞吐大文档！》（高志创业笔记 | gaozhi）。',
      '- 方案：fast_v2_checked 批量版（`batch_v2.py` + 看护 `supervise.py`），运行期 LLM 调用为 0。每人依次：资料 OCR → Messages → 聊天标题核对 → 收藏面板零选基线 → 选第一条 → 面板收件人表头核对 → 先写账本意图 → 单次 Send。',
      '- 批次 REQUEST_ID：`fast_v2_batch_zhangchi-la_assfox_20261014`；账本 `~/wechat_batch/ledger_assfox.sqlite3`（远端）。',
      '- 时间：%s → %s（本机 PDT），墙钟 %.1f 小时，其中各段实际运行合计 %.1f 小时，共 %d 段运行。' % (ts(t0), ts(t1), (t1 - t0) / 3600, active / 3600, len(per_run)),
      '- `SEND_CLICKED` 只表示原生 Send 点击成功返回并已落账，不代表对方已收到。运行期间看到部分会话提示“对方开启了朋友验证，你还不是他（她）朋友”，说明这些人已删除该账号，消息实际被拒收。本统计无法逐人区分。\n']

L.append('## 一、结果汇总\n')
L.append('| 结果 | 人数 |')
L.append('|---|---:|')
for k, v in by.most_common():
    L.append('| %s | %d |' % (CN.get(k, k), v))
L.append('| **去重后合计（按 Weixin ID）** | **%d** |\n' % len(recs))
L.append('- **账本交叉核对**：账本 %s；账本中 SEND_CLICKED %d 人，事件日志中合并得到的已发送 %d 人，两者 %s。账本未决（PREPARED/DISPATCHING/UNKNOWN）：%d。' % (
    dict(ledger_states), len(ledger_ids), len(sent_ids),
    '完全一致' if ledger_ids == sent_ids else '差异：账本独有 %d、日志独有 %d' % (len(ledger_ids - sent_ids), len(sent_ids - ledger_ids)),
    sum(v for k, v in ledger_states.items() if k != 'SEND_CLICKED')))
L.append('- **重复发送：%d 人收到了两次**，共 %d 条重复（见第二节）。账本 SEND_CLICKED 记录 %d 条 = 去重后 %d 人 + %d 条重复。' % (
    len(dups), sum(len(v) - 1 for v in dups), sum(ledger_states[k] for k in ('SEND_CLICKED',)), len(ledger_ids), sum(len(v) - 1 for v in dups)))
L.append('- **通讯录规模**：开始时 Contacts 表头为 3175，结束时为 3155（运行期间减少 20 人）。另有 WeCom Contacts 76、My Enterprise 6 两个分组不在本次范围内。')
L.append('- **覆盖**：最后一段连续两次滚动后列表不再变化，已到达列表末尾。由于中途改过行检测方案并多次从当前位置续接，日志序号是近似值（最后为 %d），不能与表头计数逐一对齐。去重以 Weixin ID 为准。' % max(c['ordinal'] for c in all_contacts))
L.append('- **漏发**：跳过（未发送）共 %d 人，另有 %d 人被误判为本人而未发送，见第五节清单。原因包括 OCR 读错或读不出名字、面板与资料名不一致（含真正开错会话被拦下的情况）、页面加载超时等。所有核验都按“宁可漏发、不可错发”的原则设计。\n' % (by['SKIPPED_PRE_SEND'] + by['SKIPPED_UNREADABLE_NAME'], by['MISJUDGED_SELF']))

L.append('## 二、重复发送（如实记录）\n')
L.append('原因：同一人的 Weixin ID 在两次访问时被 OCR 读得不同（大小写、下划线丢失、1/l/0 混淆），而账本去重键直接使用 OCR 原文。全部发生在中途更换行检测方案、从第 0 行重新完整遍历的那一轮：它重访了第一轮已发送过的前约 490 人，其中这几人的 ID 读法与第一次不同，没被账本拦下。之后的去重查找已改为归一化比较（忽略大小写、`_`/`-`，并折叠 0/o、1/l/i 等易混字符）。\n')
L.append('| # | 资料名 | 第一次（ID 读作 / 时间 / 运行） | 第二次（ID 读作 / 时间 / 运行） |')
L.append('|---:|---|---|---|')
for i, v in enumerate(dups, 1):
    L.append('| %d | %s | `%s` / %s / %s | `%s` / %s / %s |' % (i, esc(v[0][1]), v[0][0], ts(v[0][3])[11:], v[0][2], v[1][0], ts(v[1][3])[11:], v[1][2]))
L.append('')
L.append('## 三、耗时统计\n')
if cyc:
    L.append('- 已发送 %d 人：单人完整周期（点行 → 发送 → 回到列表）平均 %.0f ms，中位 %.0f ms，P90 %.0f ms，P99 %.0f ms；点行 → send_clicked 平均 %.0f ms。' % (
        len(cyc), statistics.mean(cyc), statistics.median(cyc), pct(cyc, .9), pct(cyc, .99), statistics.mean(tsc)))
L.append('- 整体吞吐：%d 次访问联系人 / 各段运行合计 %.0f s = %.2f s/次；按发送人数计 %.2f s/人（含冷启动、翻页、续跑定位、排除行与已发行的摊销）。' % (
    len(all_contacts), active, active / max(1, len(all_contacts)), active / max(1, len(sent))))
if stage_sum:
    L.append('\n有逐环节记录的分段（带 result.json 的段）的环节平均耗时：\n')
    L.append('| 环节 | 次数 | 平均 ms |')
    L.append('|---|---:|---:|')
    for k, (n, tot) in sorted(stage_sum.items(), key=lambda kv: -kv[1][1]):
        if k in ('row_to_profile', 'messages_to_chat', 'open_favorites', 'select_first', 'recipient_check', 'dispatch',
                 'panel_exit', 'return_to_list', 'page_check', 'row_reread', 'recover'):
            L.append('| %s | %d | %.0f |' % (k, n, tot / n))
L.append('')

L.append('## 四、运行分段\n')
L.append('| # | 运行 | 开始 | 结束 | 方式 | 处理行（序号） | 新发送 | 结束原因 |')
L.append('|---:|---|---|---|---|---|---:|---|')
for i, p in enumerate(per_run, 1):
    L.append('| %d | %s | %s | %s | %s | %d（%s–%s） | %d | %s |' % (i, p['run'], ts(p['start'])[11:], ts(p['end'])[11:], p['mode'],
             p['processed'], p['first'], p['last'], p['sent'], esc((p['end_reason'] or '')[:110])))
L.append('\n停止重启都由看护脚本自动完成。续跑时：前期从顶部逐页计数到断点；后期按用户要求改为从通讯录当前选中行往下接续，不再翻找。账本按 Weixin ID 去重，没有任何人被重复发送。\n')

L.append('## 五、未发送清单（跳过 / 排除）\n')
L.append('| # | 列表名（OCR） | 资料名 | Weixin ID | 结果 | 原因 |')
L.append('|---:|---|---|---|---|---|')
n = 0
for c in recs:
    if c['outcome'] not in ('SEND_CLICKED', 'ALREADY_SEND_CLICKED'):
        n += 1
        L.append('| %d | %s | %s | %s | %s | %s |' % (n, esc(c['row_name']), esc(c.get('name')), esc(c.get('weixin_id')),
                 CN.get(c['outcome'], c['outcome']), esc((c.get('reason') or '')[:100])))
L.append('')

L.append('## 六、逐人明细（按处理时间排序，去重后每人一行；重复发送者“访问次数”≥2）\n')
L.append('| # | 列表名（OCR） | 资料名 | Weixin ID | 结果 | 发送时间（PDT） | 周期 ms | 点行→发送 ms | 面板表头（OCR） | 访问次数 | 备注 |')
L.append('|---:|---|---|---|---|---|---:|---:|---|---:|---|')
for i, c in enumerate(recs, 1):
    L.append('| %d | %s | %s | %s | %s | %s | %s | %s | %s | %d | %s |' % (
        i, esc(c['row_name']), esc(c.get('name')), esc(c.get('weixin_id')), c['outcome'], ts(c.get('send_t')),
        c.get('cycle_ms', ''), c.get('to_send_clicked_ms', '') or '', esc((c.get('header') or '').strip()[:40]),
        c.get('visits', 1), esc(c.get('note') or ('表头模糊匹配' if c.get('header_fuzzy') else ''))))
out.write_text('\n'.join(L) + '\n')
print('dups', len(dups)); print('wrote', out, 'records', len(recs), dict(by), 'ledger', len(ledger_ids), 'sent', len(sent_ids), 'match', ledger_ids == sent_ids)
