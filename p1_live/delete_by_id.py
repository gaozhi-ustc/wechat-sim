"""delete_by_id: delete specific friends, each located by an exact Weixin ID search. Skip on any doubt.

For every Weixin ID given (file with one ID per line, first TSV column, or --ids a,b,c):
  1. Contacts search box <- the ID (typed key by key); the 'Contacts' result must carry the line
     "Weixin ID: <id>" exactly (case-insensitive) -> click it (opens the chat)
  2. chat: the newest non-timestamp item must be the "…开启了朋友验证…" / "…拒收…" notice (still unreachable)
  3. chat '...' -> info panel -> avatar -> profile card: its "Weixin ID:" must equal the ID exactly
  4. card '...' menu: the item must read 'Delete Contact' -> dialog must read 'Delete "<card name>"?'
  5. untick 'Clear Chat History' (chat kept) unless --clear-history -> Delete (dry run: Cancel)
  6. search the ID again: it must no longer appear under 'Contacts' -> DELETED_VERIFIED
Any check failing -> SKIPPED_<reason>, nothing clicked beyond read-only views ("宁可漏过，不可错删").
DRY RUN BY DEFAULT; --delete performs the deletion. Ledger: p1_live/ledger_delete_<account>.sqlite3 (key delete|acct|wxid:ID).

Usage: python3 -I delete_by_id.py <ids.txt|ids.tsv> [--delete] [--clear-history] [--limit N]
       python3 -I delete_by_id.py --ids huande,A6aron [--delete]
"""
import ctypes as C
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ['WX_REQUEST_ID'] = 'delete_by_id'
os.environ['WX_LEDGER'] = os.environ.get('WX_DEL_LEDGER') or os.path.join(
    HERE, 'ledger_delete_%s.sqlite3' % os.environ.get('WX_ACCOUNT', 'gaozhi-xinshu'))
import batch_v2 as bv  # noqa: E402
from batch_v2 import BatchEngine, Stage, Unknown, Stop, need, wxio, wxfast, canon, abspt  # noqa: E402
from star_v1 import chat_blocks, classify_line  # noqa: E402
import numpy as np  # noqa: E402

SEARCH = (170, 57)                       # main-window relative: Contacts search box
SEARCH_CLEAR = (275, 57)                 # its clear (x) button
RESULTS = (72, 72, 330, 400)             # search popup region (results list)
CHAT_MORE = (1057, 56)                   # chat header '...' -> info panel
PANEL_AVATAR = (873, 113)                # first member avatar in the info panel
CARD_SIZE_W = 328
CARD_MORE = (268, 60)                    # card-relative '...'
CARD_MENU = (230, 50, 260, 330)          # card-relative menu OCR region
CARD_DELETE = (335, 279)                 # card-relative 'Delete Contact' click point
DIALOG_SIZE = (330, 315)
D_TITLE, D_CHECK, D_DELETE, D_CANCEL = (40, 50, 250, 45), (97, 195), (105, 243), (226, 243)
NOTICE = re.compile(r'朋友验[证正]|开[启后]了朋友|拒收')
DEL_RE = re.compile(r'\s*De[l1I]ete', re.I)
ID_LINE = re.compile(r'weixin\s*[il1|]d\s*[:：]\s*(\S+)', re.I)


def id_eq(a, b):
    # OCR renders 'l' as '|' on the card; everything else must match exactly (case-insensitive)
    f = lambda v: (v or '').strip().lower().replace('|', 'l')
    return f(a) == f(b)


def is_red(px):
    return px[0] > 200 and px[1] < 140 and px[2] < 140


class DeleteById(BatchEngine):
    def __init__(self, delete, clear_history):
        super().__init__(delete, None)
        old = self.dir
        self.run_id = time.strftime('delid_%Y%m%dT%H%M%S') + ('_delete' if delete else '_dry')
        self.dir = wxio.OUT / self.run_id
        old.rename(self.dir)
        self.j.f.close()
        self.j = wxfast.Journal(self.dir / 'events.jsonl')
        self.sink.dir = self.dir
        self.do_delete, self.clear_history = delete, clear_history
        self.results = []
        x = self.x
        x.x.XKeysymToKeycode.argtypes = [C.c_void_p, C.c_ulong]
        self.shift = x.x.XKeysymToKeycode(x.d, x.x.XStringToKeysym(b'Shift_L'))
        self.ctrl = x.x.XKeysymToKeycode(x.d, x.x.XStringToKeysym(b'Control_L'))

    # -- low level
    def key(self, keysym, shift=False, ctrl=False):
        x = self.x
        code = x.x.XKeysymToKeycode(x.d, x.x.XStringToKeysym(keysym.encode()))
        need(code, 'no keycode for %r' % keysym)
        mods = ([self.shift] if shift else []) + ([self.ctrl] if ctrl else [])
        for m in mods:
            x.xt.XTestFakeKeyEvent(x.d, m, 1, 0)
        x.xt.XTestFakeKeyEvent(x.d, code, 1, 0); x.xt.XTestFakeKeyEvent(x.d, code, 0, 0)
        for m in reversed(mods):
            x.xt.XTestFakeKeyEvent(x.d, m, 0, 0)
        x.x.XSync(x.d, 0)
        time.sleep(0.04)

    def type_text(self, s):
        for ch in s:
            if ch.isalpha():
                self.key(ch.lower(), shift=ch.isupper())
            elif ch.isdigit():
                self.key(ch)
            elif ch == '_':
                self.key('underscore', shift=True)
            elif ch == '-':
                self.key('minus')
            elif ch == '.':
                self.key('period')
            else:
                raise Unknown('cannot type %r' % ch)

    def hover_click(self, pt):
        x = self.x
        self.epoch += 1
        x.move(pt[0] - 10, pt[1] - 3); time.sleep(0.12)
        x.move(*pt); time.sleep(0.15)
        x.xt.XTestFakeButtonEvent(x.d, 1, 1, 0); x.x.XSync(x.d, 0); time.sleep(0.06)
        x.xt.XTestFakeButtonEvent(x.d, 1, 0, 0); x.x.XSync(x.d, 0)

    def windows(self):
        o = self.q.observe(self.pid)
        return o, [w for w in o['wechat'] if w['id'] != o['main']['id']]

    def wait(self, cond, timeout=3.0, first=0.25, every=0.2):
        time.sleep(first)
        t0, last = time.time(), None
        while True:
            try:
                return cond()
            except Unknown as e:
                last = e
            if time.time() - t0 > timeout:
                raise Unknown(str(last))
            time.sleep(every)

    def clean(self):
        """Escape popups / cards back to the bare main window."""
        for i in range(4):
            o, extra = self.windows()
            if not extra and o['active'] == o['main']['id']:
                return
            # never Escape: on the bare main window Escape closes WeChat to the tray. A click on the main window's
            # title bar closes search popups and profile cards alike.
            self.hover_click(abspt(self.g, (600, 16)))
            time.sleep(0.5)
        o, extra = self.windows()
        need(not extra, 'cannot close WeChat popups: %r' % extra)

    # -- steps
    def search(self, wid):
        g = self.g
        self.clean()
        self.hover_click(abspt(g, (31, 162)))                 # Contacts tab
        time.sleep(0.5)
        self.hover_click(abspt(g, SEARCH)); time.sleep(0.3)
        self.key('a', ctrl=True); self.key('BackSpace'); time.sleep(0.2)
        self.type_text(wid)

        def results():
            im = self.look(Stage('search'))['im']
            texts = wxio.ocr(im, [g['x'] + RESULTS[0], g['y'] + RESULTS[1], RESULTS[2], RESULTS[3]])
            texts.sort(key=lambda t: t[2][1])
            plain = lambda u: re.sub(r'\W+', '', u).lower()
            heads = {plain(t[0]): t[2][1] for t in texts
                     if plain(t[0]) in ('contacts', 'groupchats', 'internetsearchresults', 'chathistory', 'more')}
            if not heads:
                raise Unknown('no search result sections yet: %r' % [t[0] for t in texts[:6]])
            return texts, heads
        texts, heads = self.wait(results, timeout=4.0, first=1.0)
        c0 = heads.get('contacts')
        if c0 is None:
            return None, 'no Contacts section'
        nxt = min([y for k, y in heads.items() if y > c0] + [10 ** 6])
        ids = [(t, ID_LINE.search(t[0])) for t in texts if c0 < t[2][1] < nxt]
        lines = [(t, m.group(1)) for t, m in ids if m]
        hit = [(t, v) for t, v in lines if id_eq(v, wid)]
        if len(hit) != 1:
            return None, 'search: Contacts rows %r' % [t[0] for t, m in ids]
        t = hit[0][0]
        names = [u for u, m in ids if not m and abs(u[2][1] - (t[2][1] - 24)) <= 12]
        return dict(id_box=t[2], name=names[0][0] if names else ''), None

    def chat_unreachable(self):
        g = self.g
        f = self.look(Stage('chat'))
        arr = np.asarray(f['im'].crop((g['x'], g['y'], g['x'] + g['w'], g['y'] + g['h']))).astype(np.int16)
        bl = chat_blocks(arr)
        lines = []
        for b in reversed(bl):
            if b['side'] != 'C':
                break
            crop = arr[b['y0'] - 4:b['y1'] + 4, max(0, b['x0'] - 10):b['x1'] + 11][:, :, ::-1].astype(np.uint8).copy()
            res, _ = wxio.ocr_engine()(crop)
            text = ''.join(r[1] for r in sorted(res or [], key=lambda r: (r[0][0][1], r[0][0][0])))
            if classify_line(text)[0] == 'ts':
                continue
            lines.append(text)
            if NOTICE.search(''.join(reversed(lines))):
                return ''.join(reversed(lines))
            if len(lines) >= 2:
                break
        return None

    def cancel_dialog(self, cg):
        """never leave a delete confirmation open: press its Cancel button if one is visible in the card"""
        im = self.look(Stage('cancel'))['im']
        tx = wxio.ocr(im, [cg['x'], cg['y'] + 120, cg['w'], 400])
        bc = [t for t in tx if re.fullmatch(r'\s*Cance[l1I]\s*', t[0])]
        if len(bc) == 1:
            b = bc[0][2]
            self.hover_click((b[0] + b[2] // 2, b[1] + b[3] // 2)); time.sleep(0.6)

    def card(self):
        o, extra = self.windows()
        cs = [w for w in extra if w['geom']['w'] == CARD_SIZE_W]
        if len(cs) != 1:
            raise Unknown('profile card not shown')
        return cs[0]['geom']

    def one(self, wid):
        g = self.g
        rec = dict(weixin_id=wid, t0=time.time())
        self.results.append(rec)
        key = 'delete|%s|wxid:%s' % (bv.ACCOUNT, wid)
        if self.ledger.state(key) in ('DELETED', 'DELETED_VERIFIED'):
            rec['outcome'] = 'ALREADY_DELETED'
            return
        hit, why = self.search(wid)
        if not hit:
            rec.update(outcome='SKIPPED_NOT_FOUND', reason=why)
            return
        rec['search_name'] = hit['name']
        b = hit['id_box']
        self.hover_click((b[0] + 40, b[1] - 10))                # the result row (name line just above the ID line)

        def chat_open():
            f = self.look(Stage('chat'))
            o = f['owner']
            if len(o['wechat']) != 1:
                raise Unknown('popup still open')
            t = self.read_title(f['im'], g)
            if not canon(t) or (canon(hit['name']) and not (canon(hit['name'])[:4] in canon(t) or canon(t)[:4] in canon(hit['name']))):
                raise Unknown('chat title %r vs %r' % (t, hit['name']))
            return t
        try:
            rec['chat_title'] = self.wait(chat_open, timeout=4.0, first=0.8)
        except Unknown as e:
            rec.update(outcome='SKIPPED_CHAT', reason=str(e)[:150])
            return
        time.sleep(0.4)
        notice = self.chat_unreachable()
        if not notice:
            rec.update(outcome='SKIPPED_STILL_REACHABLE', reason='bottom of chat is not a friend-verification / reject notice')
            self.dbg('reachable_%s' % wid, self.look(Stage('x'))['im'], g)
            return
        rec['notice'] = notice[:120]
        # info panel -> avatar -> card
        self.hover_click(abspt(g, CHAT_MORE)); time.sleep(0.9)
        self.hover_click(abspt(g, PANEL_AVATAR))
        try:
            cg = self.wait(self.card, timeout=3.0, first=0.8)
        except Unknown as e:
            rec.update(outcome='SKIPPED_CARD', reason=str(e)); self.clean(); return
        im = self.look(Stage('card'))['im']
        texts = wxio.ocr(im, [cg['x'], cg['y'], cg['w'], 200])
        cid = []
        for t in texts:
            m = ID_LINE.search(re.sub(r'\s+', '', t[0]))
            if not m:
                continue
            v = m.group(1)
            # long IDs wrap: join a continuation line directly below the ID line (still compared exactly)
            cont = [u for u in texts if t[2][0] - 5 <= u[2][0] <= t[2][0] + t[2][2] and 8 <= u[2][1] - t[2][1] <= 22
                    and ':' not in u[0] and '：' not in u[0] and re.fullmatch(r'[\w.-]+', u[0].strip())]
            if cont and not id_eq(v, wid) and id_eq(v + cont[0][0].strip(), wid):
                v = v + cont[0][0].strip()
            cid.append(v)
        cname = [t[0] for t in texts if 110 <= t[2][0] - cg['x'] <= 140 and 40 <= t[2][1] - cg['y'] <= 66]
        rec.update(card_id=cid, card_name=cname[0] if cname else '')
        if len(cid) != 1 or not id_eq(cid[0], wid):
            rec.update(outcome='SKIPPED_CARD_ID', reason='card Weixin ID %r' % cid)
            self.clean(); return
        self.ledger.put(key, 'CANDIDATE', intent=dict(weixin_id=wid, name=rec['card_name'], notice=notice[:160], run=self.run_id))
        # card '...' -> 'Delete Contact'
        self.hover_click((cg['x'] + CARD_MORE[0], cg['y'] + CARD_MORE[1])); time.sleep(0.9)
        im = self.look(Stage('menu'))['im']
        mt = wxio.ocr(im, [cg['x'] + CARD_MENU[0], cg['y'] + CARD_MENU[1], CARD_MENU[2], CARD_MENU[3]])
        dl = [t for t in mt if canon(t[0]) == canon('DeleteContact')]
        if len(dl) != 1 or abs(dl[0][2][1] - (cg['y'] + 272)) > 10:
            rec.update(outcome='SKIPPED_MENU', reason='menu %r' % [t[0] for t in mt])
            self.clean(); return
        self.hover_click((dl[0][2][0] + 40, dl[0][2][1] + 7))

        def dialog():
            # the confirmation is drawn inside the card window: 'Delete "<name>"?' + Clear Chat History + Delete/Cancel
            im = self.look(Stage('dialog'))['im']
            tx = wxio.ocr(im, [cg['x'], cg['y'] + 120, cg['w'], 420])
            # the title may wrap: 'Delete "<long name' + '...>"?' -> join the lines from 'Delete' down to the '?'
            st_ = sorted(tx, key=lambda t: t[2][1])
            ttl = []
            for i, t in enumerate(st_):
                if DEL_RE.match(t[0]) and len(re.sub(r'\s+', '', t[0])) > 7:
                    joined, j = t[0], i
                    while not re.search(r'[?？]\s*$', joined) and j + 1 < len(st_) and st_[j + 1][2][1] - st_[j][2][1] <= 30:
                        j += 1; joined += st_[j][0]
                    ttl.append((joined, 0, t[2]))
            btn_d = [t for t in tx if re.fullmatch(r'\s*De[l1I]ete\s*', t[0])]
            btn_c = [t for t in tx if re.fullmatch(r'\s*Cance[l1I]\s*', t[0])]
            chk = [t for t in tx if canon(t[0]) == canon('ClearChatHistory')]
            if not (len(ttl) == 1 and len(btn_d) == 1 and len(btn_c) == 1 and len(chk) == 1):
                raise Unknown('delete dialog not readable yet: %r' % [t[0] for t in tx])
            return ttl[0][0], btn_d[0][2], btn_c[0][2], chk[0][2]
        try:
            title, bd, bc, bk = self.wait(dialog, timeout=3.0, first=0.6)
        except Unknown as e:
            rec.update(outcome='SKIPPED_DIALOG', reason=str(e)[:150])
            self.cancel_dialog(cg); self.clean(); return
        rec['dialog'] = title
        P_DELETE = (bd[0] + bd[2] // 2, bd[1] + bd[3] // 2)
        P_CANCEL = (bc[0] + bc[2] // 2, bc[1] + bc[3] // 2)
        P_CHECK = (bk[0] - 15, bk[1] + 9)
        cn = canon(rec['card_name'])
        ok = bool(cn) and (cn in canon(title) or canon(title[6:])[:4] in cn)
        if ok and not self.clear_history:
            for attempt in range(2):
                if not is_red(self.look(Stage('chk'))['im'].getpixel(P_CHECK)):
                    break
                self.hover_click(P_CHECK)
                for i in range(5):
                    time.sleep(0.2)
                    if not is_red(self.look(Stage('chk'))['im'].getpixel(P_CHECK)):
                        break
            ok = not is_red(self.look(Stage('chk'))['im'].getpixel(P_CHECK))
            rec['kept_history'] = ok
        if not (ok and self.do_delete):
            self.hover_click(P_CANCEL); time.sleep(0.6)
            rec['outcome'] = 'DRY_RUN_WOULD_DELETE' if ok else 'SKIPPED_DIALOG'
            if not ok:
                rec['reason'] = 'dialog %r vs card name %r / history checkbox' % (title, rec['card_name'])
            self.clean(); return
        self.ledger.put(key, 'DELETE_CLICKING', result=dict(at=time.time(), dialog=title))
        self.j.event(kind='input', label='DELETE', weixin_id=wid, dialog=title)
        self.hover_click(P_DELETE); time.sleep(1.2)
        self.ledger.put(key, 'DELETED', result=dict(at=time.time(), dialog=title, kept_history=rec.get('kept_history')))
        self.clean()
        again, why = self.search(wid)
        rec['outcome'] = 'DELETED_VERIFIED' if not again else 'DELETED_STILL_LISTED'
        if not again:
            self.ledger.put(key, 'DELETED_VERIFIED', result=dict(at=time.time()))
        self.clean()
        self.hover_click(abspt(g, SEARCH_CLEAR))

    def run_ids(self, ids, limit=None):
        self.ledger = bv.Ledger(bv.LEDGER)
        full = wxio.observe()
        self.pid = full['pid']; self.g = full['main']['geom']
        need((self.g['w'], self.g['h']) == bv.MAIN_SIZE, 'main geometry not calibrated')
        self.hover_click(abspt(self.g, (600, 16)))             # activate the main window
        self.j.event(kind='start', mode='delete_by_id', delete=self.do_delete, n=len(ids))
        done = 0
        for wid in ids:
            if limit is not None and done >= limit:
                break
            try:
                self.one(wid)
            except (Unknown, Stop) as e:
                self.results[-1].update(outcome='SKIPPED_ERROR', reason=str(e)[:150])
                try:
                    self.clean()
                except Exception:
                    pass
            r = self.results[-1]
            r['ms'] = round((time.time() - r.pop('t0', time.time())) * 1000)
            self.j.event(kind='id', **r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
            if r['outcome'] in ('DELETED_VERIFIED', 'DRY_RUN_WOULD_DELETE', 'DELETED_STILL_LISTED'):
                done += 1
        out = dict(delete=self.do_delete, results=self.results)
        (self.dir / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
        self.sink.close(); self.j.close()
        return out


def load_ids(argv):
    if '--ids' in argv:
        return [s for s in argv[argv.index('--ids') + 1].split(',') if s]
    path = next(a for a in argv[1:] if not a.startswith('--') and os.path.exists(a))
    ids = []
    for line in open(path):
        v = line.split('\t')[0].strip()
        if v and v != 'weixin_id' and not v.startswith('#'):
            ids.append(v)
    return ids


if __name__ == '__main__':
    ids = load_ids(sys.argv)
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    eng = DeleteById('--delete' in sys.argv, '--clear-history' in sys.argv)
    out = eng.run_ids(ids, limit)
    from collections import Counter
    print(Counter(r['outcome'] for r in out['results']), eng.dir)
