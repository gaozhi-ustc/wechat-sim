"""send_starred: send the current first native favorite to every starred friend (batch_v2 send flow).

Scope: only the 'Starred' section at the top of Contacts (header 'Starred' ... first letter header), and the
profile's Weixin ID must also be in the star ledger (star_v1 / star_apply) -- non-starred friends are never sent.
Everything else (campaign REQUEST_ID by favorite title, dedupe ledger, recipient header / title checks, durable
intent before the single Send click) is batch_v2's.

Usage: python3 -I send_starred.py --send | --no-send [--max-rows N] [--from-current [--ordinal-base N]]
Env: as batch_v2 (WX_LEDGER = send ledger, WX_REQUEST_ID=auto); WX_STAR_LEDGER = star ledger.
"""
import json
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import batch_v2 as bv  # noqa: E402
from batch_v2 import BatchEngine, Unknown, Stop, need, absbox, canon, fold_wxid  # noqa: E402

STAR_LEDGER = os.environ.get('WX_STAR_LEDGER') or os.path.join(HERE, 'ledger_star_%s.sqlite3' % bv.ACCOUNT)
STARRED_BY_HAND = {'mengmeng777293'}     # A.阿萌baby: starred by hand while building star_v1 (not in the ledger)


def starred_ids():
    db = sqlite3.connect(STAR_LEDGER)
    ids = {fold_wxid(k.split('|wxid:', 1)[1]) for (k,) in db.execute("SELECT op_key FROM ops WHERE state='STARRED'")}
    return ids | {fold_wxid(w) for w in STARRED_BY_HAND}


class StarredSendEngine(BatchEngine):
    def __init__(self, send, limit, max_rows=None):
        super().__init__(send, limit, max_rows)
        self.starred = starred_ids()
        self.section_end = False
        self.redo_current = True       # restarts re-check the selected row; the send ledger dedupes (ALREADY_*)

    def scan(self, st, f, g):
        """Keep only rows of the Starred section: below the 'Starred' label, above the first letter header."""
        texts = self.ocr_box(st, f['im'], absbox(g, bv.W_LIST))
        page = bv.perceive_page(texts, g, f['im'])
        self.dbg('page', f['im'])
        rel = lambda t: (t[2][0] - g['x'], t[2][1] + t[2][3] / 2)
        star_h = [rel(t)[1] for t in texts if canon(t[0]) in ('starred', 'tarred') and 100 <= rel(t)[0] < 128]
        # the Starred section is followed by the alphabetical list's first header 'A' (x ~97); other single letters
        # inside the section are OCR noise (avatars) and must not end it
        letters = sorted(rel(t)[1] for t in texts if t[0].strip() == 'A' and 88 <= rel(t)[0] < 110)
        rows = page['rows']
        if star_h:
            rows = [r for r in rows if r['center'][1] > star_h[0] + 14]        # the label row itself
        if letters:
            self.section_end = True
            rows = [r for r in rows if r['center'][1] < letters[0] - 14]
        page['rows'] = rows
        self.j.event(kind='starred_page', rows=[r['name'] for r in rows], end=self.section_end)
        return page

    def scroll(self, st, f, g, button, notches):
        # past the Starred section: report "list did not move" so batch_v2 ends with its tail record
        if button == 5 and self.section_end:
            self.j.event(kind='section_end')
            return
        return super().scroll(st, f, g, button, notches)

    def send_chain(self, rec, p, op_key, g, f, ledger):
        w = fold_wxid(p['weixin_id'])
        # OCR can differ by a glyph between reads (g/q, 1/l): allow one substitution against a starred ID
        if w not in self.starred and not any(len(x) == len(w) and sum(a != b for a, b in zip(x, w)) <= 1
                                             for x in self.starred):
            raise Unknown('Weixin ID %r is not in the star ledger' % p['weixin_id'])
        return super().send_chain(rec, p, op_key, g, f, ledger)


if __name__ == '__main__':
    send = '--send' in sys.argv
    need(send or '--no-send' in sys.argv, 'specify --send or --no-send')
    max_rows = int(sys.argv[sys.argv.index('--max-rows') + 1]) if '--max-rows' in sys.argv else None
    eng = StarredSendEngine(send, None, max_rows)
    if '--from-current' in sys.argv:
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
