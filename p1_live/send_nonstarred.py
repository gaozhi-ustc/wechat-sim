"""send_nonstarred: send the current first native favorite to every NON-starred friend (batch_v2 send flow).

Start: select the first alphabetical row (just below the 'Starred' section) and run with --from-current; starred
friends live only in the Starred section, so the alphabetical list below holds the non-starred ones. Second guard:
a profile whose Weixin ID is in the star ledger is excluded (EXCLUDED_SCOPE). The do-not-send list
(do_not_send.py) applies as on every send path.

Usage: python3 -I send_nonstarred.py --send | --no-send --from-current [--ordinal-base N] [--max-rows N]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import re  # noqa: E402
import time  # noqa: E402
from batch_v2 import BatchEngine, Stage, Unknown, Stop, need, fold_wxid, wxio  # noqa: E402
from send_starred import starred_ids  # noqa: E402
from star_v1 import chat_blocks  # noqa: E402  (pure chat-area segmentation; no star_v1 env side effects used here)
import numpy as np  # noqa: E402

NOTICE = re.compile(r'朋友验[证正]|开[启后]了朋友')
DELIVERY_SETTLE_S, DELIVERY_TIMEOUT_S = 1.5, 3.0


class NonStarredSendEngine(BatchEngine):
    def __init__(self, send, limit, max_rows=None):
        super().__init__(send, limit, max_rows)
        self.starred = starred_ids()
        self.redo_current = True       # restarts re-check the selected row; the send ledger dedupes (ALREADY_*)
        # friends whose send was refused (verification on / deleted): one JSON line each, across restarts
        self.unreach = open(os.path.join(HERE, 'evidence', 'unreachable_%s.jsonl' % time.strftime('%Y%m%d')), 'a')

    # -- after each Send: did WeChat refuse it ("…开启了朋友验证…" notice / red '!' next to the sent card)?
    def delivery(self, st, g):
        t0, red_seen, text = time.time(), False, ''
        while True:
            f = self.look(st)
            arr = np.asarray(f['im'].crop((g['x'], g['y'], g['x'] + g['w'], g['y'] + g['h']))).astype(np.int16)
            bl = chat_blocks(arr)
            rs = [b for b in bl if b['side'] == 'R']
            last = rs[-1] if rs else None
            below = [b for b in bl if last is not None and b['y0'] > last['y1'] and b['side'] == 'C']
            if below:
                y0, y1 = below[0]['y0'] - 4, below[-1]['y1'] + 4
                x0, x1 = min(b['x0'] for b in below) - 10, max(b['x1'] for b in below) + 11
                s = time.time()
                res, _ = wxio.ocr_engine()(arr[y0:y1, x0:x1][:, :, ::-1].astype(np.uint8).copy())
                st.add('ocr', s); st.n['ocr_calls'] += 1; self.ocr_calls += 1
                text = ''.join(r[1] for r in sorted(res or [], key=lambda r: (r[0][0][1], r[0][0][0])))
                if NOTICE.search(text):
                    return 'UNREACHABLE', text, f
            if last is not None:
                reg = arr[last['y0']:last['y1'], last['x0']:last['x0'] + 30]    # the red '!' is the card block's leftmost ink
                red_seen = red_seen or bool(((reg[:, :, 0] > 220) & (reg[:, :, 1] < 120) & (reg[:, :, 2] < 120)).sum() > 20)
            el = time.time() - t0
            if not red_seen and not below and el >= DELIVERY_SETTLE_S:
                return 'DELIVERED', '', f
            if el >= DELIVERY_TIMEOUT_S:
                return ('SEND_FAILED' if red_seen else 'UNCERTAIN'), text, f
            time.sleep(0.3)

    def back_to_list(self, rec, g, f):
        if rec.get('outcome') == 'SEND_CLICKED':
            st = Stage('delivery_check')
            d, text, f = self.delivery(st, g)
            rec.update(delivery=d, delivery_notice=text[:120])
            rec['stages'].append(self.finish_stage(st, delivery=d))
            if d != 'DELIVERED':
                self.unreach.write(json.dumps(dict(weixin_id=rec.get('weixin_id'), name=rec.get('name'), row=rec.get('row_name'),
                                                   ordinal=rec.get('ordinal'), delivery=d, notice=text[:160], at=time.time(),
                                                   run=self.run_id), ensure_ascii=False) + '\n')
                self.unreach.flush()
                self.dbg('delivery_%s_%04d' % (d.lower(), rec['ordinal']), f['im'], g)
        return super().back_to_list(rec, g, f)

    def exclude_recipient(self, p, row):
        w = fold_wxid(p['weixin_id'])
        if w in self.starred or any(len(x) == len(w) and sum(a != b for a, b in zip(x, w)) <= 1 for x in self.starred):
            return 'starred friend (Weixin ID %r in the star ledger)' % p['weixin_id']
        return None


if __name__ == '__main__':
    send = '--send' in sys.argv
    need(send or '--no-send' in sys.argv, 'specify --send or --no-send')
    need('--from-current' in sys.argv, 'start from the selected first alphabetical row (--from-current)')
    max_rows = int(sys.argv[sys.argv.index('--max-rows') + 1]) if '--max-rows' in sys.argv else None
    eng = NonStarredSendEngine(send, None, max_rows)
    eng.from_current = True
    eng.ordinal_base = int(sys.argv[sys.argv.index('--ordinal-base') + 1]) if '--ordinal-base' in sys.argv else 0
    try:
        r = eng.run()
        print(json.dumps({k: v for k, v in r.items() if k not in ('contacts', 'all_stages')}, ensure_ascii=False, indent=1, default=str))
    except (Stop, Unknown, Exception) as e:
        e = Stop('%s: %s' % (type(e).__name__, e)) if not isinstance(e, Stop) else e
        eng.j.event(kind='stop', reason=str(e))
        try:
            eng.finish_batch(eng.T0, eng.seen, dict(stopped=str(e)))
        except Exception as e2:
            print('finish failed', e2)
        print('STOP:', e)
        sys.exit(2)
