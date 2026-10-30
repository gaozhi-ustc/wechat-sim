"""delete_unreachable: delete friends who have deleted / blocked the owner (messages can no longer be sent).

Unreachable = the newest item at the bottom of the chat (timestamps ignored) is WeChat's system notice
"XX开启了朋友验证，你还不是他（她）朋友。请先发送朋友验证请求…". A friend who re-added the owner afterwards has newer
messages below the notice and is kept.

Traversal is batch_v2's (top proof / page linking / relink / tail proof / --from-current) over the whole Contacts list,
Starred section included. Per row:
  click row -> right-click -> 'Messages' -> chat title check -> look at the bottom of the chat (rec-OCR of the lowest
  centered lines) -> back to Contacts -> unreachable only: profile OCR (Weixin ID, self check, row/profile association)
  -> right-click -> the third menu item must read 'Delete Contact' -> click -> the dialog must read
  'Delete "<this friend>"?' -> untick 'Clear Chat History' (unless --clear-history) -> Delete (or Cancel in dry run)
  -> the deleted row is dropped from the traversal history so batch_v2 re-links to the next row.

DRY RUN BY DEFAULT: everything up to the confirmation dialog, then Cancel. Deleting needs --delete.
Usage: python3 -I delete_unreachable.py [--delete] [--clear-history] [--max-deletes N] [--max-rows N]
                                         [--from-current [--ordinal-base N]]
Ledger: WX_DEL_LEDGER (default p1_live/ledger_delete_<account>.sqlite3): CANDIDATE / DELETE_CLICKING / DELETED.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ['WX_STAR_ID'] = os.environ.get('WX_DEL_ID', 'delete_unreachable')
os.environ['WX_STAR_LEDGER'] = os.environ.get('WX_DEL_LEDGER') or os.path.join(
    HERE, 'ledger_delete_%s.sqlite3' % os.environ.get('WX_ACCOUNT', 'gaozhi-xinshu'))

import star_v1 as sv  # noqa: E402
import batch_v2 as bv  # noqa: E402
from star_v1 import (StarEngine, Stage, Unknown, Stop, need, wxio, absbox, canon, fold_wxid, row_selected,  # noqa: E402
                     perceive_profile_fast, name_match, chat_blocks, classify_line, ACCOUNT)
import numpy as np  # noqa: E402

DIALOG_SIZE = (330, 315)                 # 'Delete "<name>"?' confirmation (transient of the main window)
D_TITLE = (40, 50, 250, 45)
D_CHECK = (97, 195)                      # 'Clear Chat History' check mark: red (250,81,81) when ticked
D_DELETE = (105, 243)
D_CANCEL = (226, 243)
MENU_DELETE = (60, 95)                   # right-click point -> 'Delete Contact' item
DEL_RE = re.compile(r'\s*De[l1I]ete', re.I)  # canon() folds l->1, so match the raw OCR text
NOTICE = re.compile(r'朋友验[证正]|开[启后]了朋友')


def is_red(px):
    return px[0] > 200 and px[1] < 140 and px[2] < 140


class DeleteEngine(StarEngine):
    def __init__(self, delete, clear_history, max_deletes, max_rows=None):
        super().__init__(False, max_rows)
        self.do_delete, self.clear_history, self.max_deletes = delete, clear_history, max_deletes
        self.deleted = 0

    # -- whole Contacts list: keep Starred-section rows, drop only the 'Starred' label row
    def scan(self, st, f, g):
        texts = self.ocr_box(st, f['im'], absbox(g, bv.W_LIST))
        page = bv.perceive_page(texts, g, f['im'])
        self.dbg('page', f['im'])
        lab = [t[2][1] + t[2][3] / 2 for t in texts if canon(t[0]) in ('starred', 'tarred') and 100 <= t[2][0] - g['x'] < 128]
        if lab:
            page['rows'] = [r for r in page['rows'] if abs(r['center'][1] - lab[0]) > 14]
        return page

    # -- decision from the bottom of the chat only (no scrolling needed)
    def scan_chat(self, st, g, rec):
        arr = rec.pop('_chat_arr')
        bl = chat_blocks(arr)
        if not bl:
            return 'NO_MESSAGES', {}
        lines = []
        for b in reversed(bl):
            if b['side'] != 'C':
                return 'REACHABLE', dict(bottom=b['side'], lines=lines)
            crop = arr[b['y0'] - 4:b['y1'] + 4, max(0, b['x0'] - 10):b['x1'] + 11][:, :, ::-1].astype(np.uint8).copy()
            s = time.time()
            res, _ = wxio.ocr_engine()(crop)
            st.add('ocr', s); st.n['ocr_calls'] += 1; self.ocr_calls += 1
            text = ''.join(r[1] for r in sorted(res or [], key=lambda r: (r[0][0][1], r[0][0][0])))
            if classify_line(text)[0] == 'ts':
                continue
            lines.append(text)
            if NOTICE.search(''.join(reversed(lines))):
                return 'STAR', dict(notice=''.join(reversed(lines))[:120])     # 'STAR' = act on this row
            if len(lines) >= 2:                                                # a two-line notice at most
                return 'REACHABLE', dict(bottom='system', lines=lines)
        return 'REACHABLE', dict(bottom='top', lines=lines)

    # -- unreachable row: verify identity, then the Delete Contact dialog
    def star(self, rec, row, g, f, ledger):
        rec['decision'] = 'UNREACHABLE'
        st = Stage('delete')
        prev = {}

        def profile_ready(f):
            self.main_active(f)
            if not row_selected(f['im'], g, row['band']):
                raise Unknown('row no longer selected at its position')
            x, y, w, h = absbox(g, (520, 85, 350, 680))
            sig = np.asarray(f['im'].crop((x, y, x + w, y + h)))[::4, ::4].tobytes()
            same = prev.get('sig') == sig
            prev['sig'] = sig
            if not same:
                raise Unknown('profile still changing')
            return {}
        try:
            f, _ = self.poll(st, 'profile', profile_ready)
            p = None
            for attempt in range(2):
                try:
                    p = perceive_profile_fast(f['im'], g, row['band'])
                    break
                except Unknown as e:
                    err = str(e)
                time.sleep(0.25); f = self.look(st)
            if p is None:
                raise Unknown('profile: %s' % err)
        except (Unknown, Stop) as e:
            rec['stages'].append(self.finish_stage(st))
            rec.update(outcome='SKIPPED_PRE_DELETE', reason=str(e)[:200])
            return self.look(st)
        rec.update(name=p['name'], weixin_id=p['weixin_id'])
        if fold_wxid(p['weixin_id']) == fold_wxid(ACCOUNT):
            rec['stages'].append(self.finish_stage(st))
            rec['outcome'] = 'EXCLUDED_SELF'
            return f
        if not (p['selected'] and (not canon(p['name']) or not canon(row['name']) or name_match(row['name'], p['name'])
                                   or name_match(p['name'], rec.get('title', '')))):
            rec['stages'].append(self.finish_stage(st))
            rec.update(outcome='SKIPPED_PRE_DELETE', reason='row/profile association %r vs %r' % (row['name'], p['name']))
            return f
        op_key = 'delete|%s|wxid:%s' % (ACCOUNT, p['weixin_id'])
        if ledger.state(op_key) is None:
            ledger.put(op_key, 'CANDIDATE', intent=dict(row=row['name'], name=p['name'], weixin_id=p['weixin_id'],
                                                        title=rec.get('title'), evidence=rec.get('evidence'), run=self.run_id))
        if self.do_delete and self.max_deletes is not None and self.deleted >= self.max_deletes:
            rec['stages'].append(self.finish_stage(st))
            rec['outcome'] = 'NOT_DELETED_LIMIT'
            return f

        f, pt, m = self.open_menu(st, f, row, g)
        if m.get('self') or canon(m['delete']) != canon('DeleteContact'):
            f = self.close_menu(st)
            rec['stages'].append(self.finish_stage(st))
            rec.update(outcome='SKIPPED_PRE_DELETE', reason='menu %r' % m)
            return f
        self.menu_click(st, (pt[0] + MENU_DELETE[0], pt[1] + MENU_DELETE[1]), 'menu-delete-contact')

        def dialog_ready(f):
            # 'Delete "<name>"?' confirmation: a transient 330-px-wide window (taller when the name wraps).
            # Title, buttons and the history checkbox are located by OCR, not by fixed offsets.
            o = f['owner']
            ds = [w for w in o['wechat'] if w['id'] != o['main']['id'] and w['geom']['w'] == DIALOG_SIZE[0]]
            if len(ds) != 1 or o['active'] != ds[0]['id']:
                raise Unknown('delete dialog not shown')
            dg = ds[0]['geom']
            tx = sorted(self.ocr_box(st, f['im'], [dg['x'], dg['y'], dg['w'], dg['h']]), key=lambda t: t[2][1])
            title = None
            for i, t in enumerate(tx):
                if DEL_RE.match(t[0]) and len(re.sub(r'\s+', '', t[0])) > 7:
                    title, j = t[0], i
                    while not re.search(r'[?？]\s*$', title) and j + 1 < len(tx) and tx[j + 1][2][1] - tx[j][2][1] <= 30:
                        j += 1; title += tx[j][0]
                    break
            bd = [t[2] for t in tx if re.fullmatch(r'\s*De[l1I]ete\s*', t[0])]
            bc = [t[2] for t in tx if re.fullmatch(r'\s*Cance[l1I]\s*', t[0])]
            ck = [t[2] for t in tx if canon(t[0]) == canon('ClearChatHistory')]
            if not (title and len(bd) == 1 and len(bc) == 1 and len(ck) == 1):
                raise Unknown('dialog not readable yet: %r' % [t[0] for t in tx])
            return dict(geom=dg, title=title, delete=bd[0], cancel=bc[0], check=ck[0])
        try:
            f, dl = self.poll(st, 'menu', dialog_ready)
        except Stop as e:
            # never leave a confirmation open: Cancel by OCR if visible, else Escape (the dialog is the active window)
            f = self.look(st)
            o = f['owner']
            ds = [w for w in o['wechat'] if w['id'] != o['main']['id'] and w['geom']['w'] == DIALOG_SIZE[0]]
            if ds:
                dg = ds[0]['geom']
                bc = [t[2] for t in self.ocr_box(st, f['im'], [dg['x'], dg['y'], dg['w'], dg['h']])
                      if re.fullmatch(r'\s*Cance[l1I]\s*', t[0])]
                if bc:
                    self.menu_click(st, (bc[0][0] + bc[0][2] // 2, bc[0][1] + bc[0][3] // 2), 'dialog-cancel')
                elif o['active'] == ds[0]['id']:
                    self.x.key('Escape')
                time.sleep(0.6)
            rec['stages'].append(self.finish_stage(st))
            rec.update(outcome='SKIPPED_PRE_DELETE', reason='dialog: %s' % str(e)[:150])
            return self.recover(g)
        mid = lambda b: (b[0] + b[2] // 2, b[1] + b[3] // 2)
        P_DELETE, P_CANCEL = mid(dl['delete']), mid(dl['cancel'])
        P_CHECK = (dl['check'][0] - 15, dl['check'][1] + 9)
        title = dl['title']
        rec['dialog'] = title
        cand = [n for n in (row['name'], p['name'], rec.get('title', '')) if canon(n)]
        title_ok = bool(DEL_RE.match(title)) and (not cand or any(name_match(n, title[6:]) or canon(n)[:4] in canon(title) for n in cand))
        ok = title_ok
        if ok and not self.clear_history:
            for attempt in range(2):
                if not is_red(f['im'].getpixel(P_CHECK)):
                    break
                self.menu_click(st, P_CHECK, 'dialog-keep-history')
                for i in range(5):
                    time.sleep(0.2); f = self.look(st)
                    if not is_red(f['im'].getpixel(P_CHECK)):
                        break
            ok = not is_red(self.look(st)['im'].getpixel(P_CHECK))
            rec['kept_history'] = ok
        if not (ok and self.do_delete):
            self.menu_click(st, P_CANCEL, 'dialog-cancel')
            f, _ = self.poll(st, 'exit', self.main_active)
            rec['stages'].append(self.finish_stage(st))
            rec['outcome'] = 'DRY_RUN_WOULD_DELETE' if ok else 'SKIPPED_PRE_DELETE'
            if not ok:
                rec['reason'] = 'dialog title %r / history checkbox not as expected' % title
            return f
        ledger.put(op_key, 'DELETE_CLICKING', result=dict(at=time.time(), dialog=title))
        self.menu_click(st, P_DELETE, 'dialog-DELETE')
        try:
            f, _ = self.poll(st, 'exit', self.main_active)
        except Stop as e:
            ledger.put(op_key, 'UNKNOWN', result=dict(at=time.time(), error=str(e)))
            raise Stop('HALT: delete dialog did not close after Delete for %r: %s' % (p['name'], e))
        ledger.put(op_key, 'DELETED', result=dict(at=time.time(), dialog=title, kept_history=rec.get('kept_history')))
        self.deleted += 1
        rec['outcome'] = 'DELETED'
        if self.seen:
            self.seen.pop()            # the row is gone: re-link the page on the rows that are still there
        rec['stages'].append(self.finish_stage(st))
        return f

    def finish_batch(self, T0, seen, tail):
        out = super().finish_batch(T0, seen, tail)
        print('DELETED this run:', self.deleted)
        return out


if __name__ == '__main__':
    delete = '--delete' in sys.argv
    max_rows = int(sys.argv[sys.argv.index('--max-rows') + 1]) if '--max-rows' in sys.argv else None
    max_deletes = int(sys.argv[sys.argv.index('--max-deletes') + 1]) if '--max-deletes' in sys.argv else None
    eng = DeleteEngine(delete, '--clear-history' in sys.argv, max_deletes, max_rows)
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
