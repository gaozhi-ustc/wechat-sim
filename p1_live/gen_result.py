"""Build result.md (per-friend detail + summary) from a batch_v2 run's result.json / events.jsonl.

Usage: python3 -I gen_result.py <run_dir> <out.md> [title]
"""
import collections
import json
import statistics
import sys
import time
from pathlib import Path

# Usage: gen_result.py <out.md> <title> <run_dir> [<run_dir> ...]   (runs in chronological order)
out = Path(sys.argv[1])
title = sys.argv[2]
runs = [Path(a) for a in sys.argv[3:]]
PRIO = {'SEND_CLICKED': 5, 'UNKNOWN': 5, 'DRY_RUN_PREPARED': 4, 'EXCLUDED_SELF': 3, 'EXCLUDED_NOT_ORDINARY': 3, 'EXCLUDED_UNAVAILABLE': 3, 'SKIPPED_UNREADABLE_NAME': 1,
        'NOT_ATTEMPTED_LIMIT': 2, 'SKIPPED_PRE_SEND': 1, 'ALREADY_SEND_CLICKED': 0}
events, merged, per_run = [], {}, []
res = {}
for run in runs:
    ev = [json.loads(l) for l in (run / 'events.jsonl').read_text().splitlines() if l.strip()]
    r = json.loads((run / 'result.json').read_text()) if (run / 'result.json').exists() else {}
    cs = r.get('contacts') or [e for e in ev if e['kind'] == 'contact']
    st = {e.get('ordinal'): e['t'] for e in ev if e['kind'] == 'send_clicked'}
    for c in cs:
        c = dict(c, run=run.name, send_t=st.get(c['ordinal']))
        k = ('wx', c['weixin_id']) if c.get('weixin_id') else ('ord', run.name, c['ordinal'])
        if k not in merged or PRIO.get(c['outcome'], 0) >= PRIO.get(merged[k]['outcome'], 0):
            if k in merged and merged[k]['outcome'] == 'SKIPPED_PRE_SEND' and c['outcome'] != 'SKIPPED_PRE_SEND':
                c['note'] = 'earlier run skipped: %s' % (merged[k].get('reason') or '')[:60]
            merged[k] = c
    per_run.append(dict(run=run.name, wall_s=r.get('wall_s', round(ev[-1]['t'] - ev[0]['t'], 3) if ev else None),
                        processed=len(cs), sent=sum(c['outcome'] == 'SEND_CLICKED' for c in cs),
                        resume_after=next((e.get('resume_after') for e in ev if e['kind'] == 'start'), 0),
                        stop=next((e['reason'] for e in ev if e['kind'] == 'stop'), None),
                        tail=r.get('tail'), ocr_calls=r.get('ocr_calls')))
    events += ev
    res = r if r.get('tail') and r['tail'].get('complete') is not None else (res or r)
# order: by the latest run's ordinal (the final full pass uses the definitive row scheme), then earlier runs
contacts = sorted(merged.values(), key=lambda c: (c['ordinal'], c['run']))
start = next((e for e in events if e['kind'] == 'start'), {})
stops = [e for e in events if e['kind'] in ('stop', 'send_unknown', 'UI_STALLED')]
sends = [e for e in events if e['kind'] == 'send_clicked']
run = runs[-1]


def ts(t):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t)) if t else ''


def stage_ms(c, name):
    for s in c.get('stages', []):
        if s['stage'] == name:
            return s['total_ms']
    return None


by = collections.Counter(c['outcome'] for c in contacts)
sent = [c for c in contacts if c['outcome'] == 'SEND_CLICKED']
cyc = [c['cycle_ms'] for c in sent]
tsc = [c['to_send_clicked_ms'] for c in sent if c.get('to_send_clicked_ms')]
send_t = {c['ordinal']: c.get('send_t') for c in contacts}

L = []
L.append('# %s\n' % title)
L.append('- 运行目录：`%s`' % run)
L.append('- 开始：%s；结束：%s；墙钟：%s s' % (ts(events[0]['t']) if events else '', ts(events[-1]['t']) if events else '',
                                         res.get('wall_s', round(events[-1]['t'] - events[0]['t'], 3) if events else '')))
L.append('- 模式：%s；send=%s；批次 REQUEST_ID 见 ledger' % (res.get('mode', start.get('mode')), res.get('send', start.get('send'))))
L.append('- 列表表头计数：%s；已处理 occurrence：%d；尾部：%s' % (
    (res.get('tail') or {}).get('header_count'), len(contacts), json.dumps(res.get('tail'), ensure_ascii=False)))
L.append('- 停止/异常事件：%s' % ('; '.join('%s: %s' % (e['kind'], e.get('reason') or e.get('error')) for e in stops) or '无'))
L.append('- OCR 调用：%s；调试帧丢弃：%s\n' % (res.get('ocr_calls'), res.get('debug_frames_dropped')))

L.append('## 运行分段\n')
L.append('| 运行 | 续跑起点 | 处理行 | 新发送 | 墙钟 s | OCR | 结束原因 |')
L.append('|---|---:|---:|---:|---:|---:|---|')
for pr in per_run:
    L.append('| %s | %s | %s | %s | %s | %s | %s |' % (pr['run'], pr['resume_after'], pr['processed'], pr['sent'], pr['wall_s'],
             pr['ocr_calls'], (pr['stop'] or json.dumps(pr['tail'], ensure_ascii=False) or '')[:90].replace('|', '/')))
L.append('')
L.append('## 结果汇总（按列表序号合并，同一序号以最终结果为准）\n')
L.append('| 结果 | 人数 |')
L.append('|---|---:|')
for k, v in by.most_common():
    L.append('| %s | %d |' % (k, v))
L.append('| **合计** | **%d** |\n' % len(contacts))
if sent:
    L.append('- 发送成功（SEND_CLICKED）：%d 人；单人 cycle 平均 %.1f ms、中位 %.1f ms、P95 %.1f ms；点行→send_clicked 平均 %.1f ms' % (
        len(sent), statistics.mean(cyc), statistics.median(cyc), sorted(cyc)[max(0, int(len(cyc) * 0.95) - 1)],
        statistics.mean(tsc) if tsc else 0))
    if res.get('wall_s'):
        L.append('- 吞吐：%.2f s/行，%.2f s/成功发送（含冷启动、翻页、排除行摊销）' % (res['wall_s'] / max(1, len(contacts)), res['wall_s'] / len(sent)))
L.append('')
if res.get('per_stage'):
    L.append('## 环节耗时\n')
    L.append('| 环节 | 次数 | 平均 ms | 合计 ms | 其中 OCR ms | 其中等待 ms |')
    L.append('|---|---:|---:|---:|---:|---:|')
    for k, a in res['per_stage'].items():
        L.append('| %s | %d | %.1f | %.1f | %.1f | %.1f |' % (k, a['n'], a['avg_ms'], a['total_ms'], a['ocr_ms'], a['wait_ms']))
    cat = collections.Counter()
    for s in res.get('all_stages', []):
        for k in ('wait_ms', 'capture_ms', 'window_ms', 'ocr_ms', 'classify_ms', 'input_ms', 'ledger_ms', 'other_ms'):
            cat[k] += s[k]
    L.append('\n按类别合计（ms）：' + ' · '.join('%s %.1f' % (k[:-3], v) for k, v in cat.most_common()) + '\n')

L.append('## 逐人明细\n')
L.append('| # | 列表名（OCR） | 资料名 | Weixin ID | 结果 | send_clicked 时间 | 点行→资料 | 聊天 | 收藏 | 选中 | 表头 | 发送 | 退出 | 回列表 | cycle ms | 备注 |')
L.append('|---:|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|')
esc = lambda s: str(s if s is not None else '').replace('|', '\\|').replace('\n', ' ')
for c in contacts:
    f = lambda n: '' if stage_ms(c, n) is None else '%.0f' % stage_ms(c, n)
    L.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
        c['ordinal'], esc(c['row_name']), esc(c.get('name')), esc(c.get('weixin_id')), c['outcome'],
        ts(send_t.get(c['ordinal'])), f('row_to_profile'), f('messages_to_chat'), f('open_favorites'), f('select_first'),
        f('recipient_check'), f('dispatch'), f('panel_exit'), f('return_to_list'), c.get('cycle_ms', ''),
        esc(((c.get('reason') or '') + ' ' + (c.get('note') or '')).strip()[:80])))
out.write_text('\n'.join(L) + '\n')
print('wrote', out, len(contacts), 'contacts', dict(by))
