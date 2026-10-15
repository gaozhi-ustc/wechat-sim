"""Supervisor for long batch_v2 --send runs: restart after *safe* stops, resuming near the stop point.

Safety: never restarts if the ledger has PREPARED/DISPATCHING/UNKNOWN rows; waits until WeChat shows only
its main window (e.g. an incoming-call popup is gone) before restarting; gives up after repeated no-progress.
Usage: python3 -I supervise.py [--first-resume N]   (N = ordinal of the last processed / currently selected row)
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wxio  # noqa: E402
import wxfast  # noqa: E402

LEDGER = os.environ['WX_LEDGER']
LOG = HERE.parent / 'supervise.jsonl'
MAX_RESTARTS, BACKOFF = 60, 3


def log(**kw):
    kw['t'] = time.time()
    with LOG.open('a') as f:
        f.write(json.dumps(kw, ensure_ascii=False) + '\n')
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def unresolved():
    db = sqlite3.connect(LEDGER)
    try:
        return db.execute("SELECT op_key,state FROM ops WHERE state IN ('PREPARED','DISPATCHING','UNKNOWN')").fetchall()
    except sqlite3.OperationalError:
        return []


def wait_clean(limit_s=3600):
    q = wxfast.XQ()
    t0 = time.time()
    while time.time() - t0 < limit_s:
        o = q.observe(wxio.wechat_pid())
        if len(o['wechat']) == 1:
            return True
        time.sleep(10)
    return False


def run_summary(d):
    ev = [json.loads(l) for l in (d / 'events.jsonl').read_text().splitlines() if l.strip()]
    ords = [e['ordinal'] for e in ev if e['kind'] == 'contact']
    tail = next((e for e in ev if e['kind'] == 'tail'), None)
    stop = next((e['reason'] for e in ev if e['kind'] == 'stop'), None)
    return (max(ords) if ords else None), tail, stop


resume = int(sys.argv[sys.argv.index('--first-resume') + 1]) if '--first-resume' in sys.argv else 0
best = resume
no_progress = 0
for n in range(MAX_RESTARTS):
    bad = unresolved()
    if bad:
        log(kind='halt', reason='ledger unresolved', rows=bad); break
    if not wait_clean():
        log(kind='halt', reason='WeChat extra window persisted 1h'); break
    before = set(p.name for p in (HERE / 'evidence').glob('batch_*_send'))
    log(kind='launch', n=n, resume_after=resume)
    rc = subprocess.call([sys.executable, '-I', str(HERE / 'batch_v2.py'), '--send', '--from-current', '--ordinal-base', str(resume)],
                         stdout=open(HERE.parent / ('batch_send_%s_%02d.log' % (time.strftime('%Y%m%dT%H%M%S'), n)), 'w'), stderr=subprocess.STDOUT)
    new = sorted(set(p.name for p in (HERE / 'evidence').glob('batch_*_send')) - before)
    d = HERE / 'evidence' / new[-1] if new else None
    last, tail, stop = run_summary(d) if d else (None, None, 'no run dir')
    log(kind='exit', n=n, rc=rc, run=str(d), last_ordinal=last, tail=tail, stop=stop)
    if tail and tail.get('complete') is not None:
        log(kind='done', tail=tail); break
    if last is not None and last > best + 2:
        best, no_progress = last, 0
    else:
        no_progress += 1
        if no_progress >= BACKOFF:
            log(kind='halt', reason='no progress in %d consecutive runs' % BACKOFF); break
    resume = last if last is not None else best      # continue after the currently selected (last processed) row
    time.sleep(5)
