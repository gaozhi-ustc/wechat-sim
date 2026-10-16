"""fast_v2_checked batch: all ordinary friends in Contacts, ordered from the top.

Batch once: lock, ledger, model+warmup, account, scroll list to top + top proof.
Page: list OCR once -> rows (name column only); overlap-linked to the previous page.
Per row: click -> profile OCR x1 -> classify (self / not-ordinary / already sent / new)
  new -> Messages -> favorites (visual) -> select (visual) -> header rec-OCR -> intent -> Send x1
  -> panel exit -> back to Contacts tab -> cheap rec-only check of next row label.
Tail proof: list pixels unchanged after scrolling AND ordered occurrences == header count.
Zero LLM calls. Usage: python3 -I batch_v2.py --send | --no-send [--limit N]

Campaign (REQUEST_ID): WX_REQUEST_ID unset or 'auto' -> read the title of the first favorite once per run
(Favorites tab) and look it up in the ledger's campaigns table: same title -> same REQUEST_ID (dedupe, resume);
new title -> new REQUEST_ID (started from the current position like any run). Each send also checks the panel's first
item title against the campaign title. An explicit WX_REQUEST_ID keeps the old fixed-ID behaviour.
"""
import difflib
import unicodedata
import fcntl
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fast_v2 import (HERE, wxio, wxfast, Stop, need, Unknown, Ledger, absbox, abspt, norm, row_selected,
                     TPL, MAIN_SIZE, PANEL_SIZE, P_HEADER, P_SEND_CLICK, W_ACTIVATE, W_AVATAR,
                     W_CONTACTS_TAB, REQUEST_ID, ACCOUNT, SELF_NAMES, PROD_LOCK, LEDGER, Stage, FastEngine,
                     chat_visual, panel_visual, read_header_fast, perceive_profile_fast, WAITS)
from ocr_mvp_v1 import W_LIST, GREEN_ROW, close
import ocr_mvp_v1 as v1
import numpy as np  # noqa: E402  (after fast_v2 puts the OCR site on sys.path)
import cv2  # noqa: E402

MODE = 'fast_v2_checked_batch'
SCROLL_NOTCHES = 4
WAITS.update(scroll=(0.35, 3.0))
WAITS['chat'] = (0.30, 2.5)
SYSTEM_HINTS = ('微信团队', '文件传输', 'Weixin Team', 'File Transfer')
AUTO_RID = os.environ.get('WX_REQUEST_ID', '') in ('', 'auto')
W_FAV_TAB = (31, 211)                  # sidebar Favorites icon
W_FAV_ALL_PX = (250, 140)              # 'All Favorites' row: green when selected
W_FAV_VIEW = (61, 33, 1027, 200)       # search box + list header + first card of the Favorites tab
P_FIRST_TITLE = (265, 92, 360, 22)     # panel-relative title line of the first favorite (rec-only)


_CONFUSE = str.maketrans({'o': '0', 'l': '1', 'i': '1', '|': '1'})


def canon(s):
    """lower + fold OCR-confusable glyphs (0/o/O, 1/l/I/|) + keep only letters/digits/CJK."""
    s = (s or '').lower().translate(_CONFUSE)
    return ''.join(ch for ch in s if unicodedata.category(ch)[0] in 'LN')


_WXFOLD = str.maketrans({'o': '0', 'l': '1', 'i': '1', '|': '1', 's': '5', 'z': '2', 'b': '8'})


def fold_wxid(w):
    """OCR-robust Weixin ID key: case, '_'/'-' and confusable glyphs folded (dedupe lookups only)."""
    return (w or '').lower().translate(_WXFOLD).replace('_', '').replace('-', '')


def title_prefix_ratio(short, full):
    """similarity of an OCR'd (possibly '…'-truncated) title line to the full campaign title."""
    a, b = canon(short), canon(full)
    return difflib.SequenceMatcher(None, a, b[:len(a)]).ratio() if a and b else 0.0


def resolve_campaign(ledger, title, create):
    """(request_id, is_new) for the favorite title; same content (fuzzy, OCR-tolerant) reuses its campaign."""
    db = ledger.db
    db.execute('CREATE TABLE IF NOT EXISTS campaigns(request_id TEXT PRIMARY KEY, account TEXT, title TEXT, created REAL)')
    for rid, t in db.execute('SELECT request_id,title FROM campaigns WHERE account=? ORDER BY created DESC', (ACCOUNT,)):
        a, b = canon(t), canon(title)
        if a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.85:
            return rid, False
    rid = 'fav_%s_%s' % (ACCOUNT, time.strftime('%Y%m%dT%H%M%S'))
    if create:
        db.execute('INSERT INTO campaigns VALUES(?,?,?,?)', (rid, ACCOUNT, title, time.time()))
    return rid, True


def similar(a, b):
    a, b = canon(a), canon(b)
    return a == b or (a and b and difflib.SequenceMatcher(None, a, b).ratio() >= 0.6)


def perceive_page(texts, g, im=None):
    """Rows of the Contacts group from one list OCR; works scrolled (sticky header) or at top."""
    texts = sorted(texts, key=lambda t: t[2][1])
    flat = lambda t: re.sub(r'\s+', '', t[0])
    header = [t for t in texts if re.fullmatch(r'\W?V?Contacts', flat(t))]
    if len(header) != 1:
        raise Unknown('Contacts header not unique: %r' % [t[0] for t in texts])
    h = header[0][2]
    hy = h[1] + h[3]
    count = [t for t in texts if re.fullmatch(r'\d+', t[0].strip()) and abs(t[2][1] - h[1]) < 8]
    manage = [t for t in texts if flat(t).endswith('ManageContacts')]
    official = [t for t in texts if 'OfficialAccounts' in flat(t)]
    # Top: Search, Manage Contacts first; between Manage Contacts and the Contacts header only collapsed
    # group headers (Official Accounts / WeCom Contacts / My Enterprise ...) and their counts -- no item in
    # the contact-name column, i.e. no contact rows hidden above the Contacts group.
    between = texts[2:texts.index(header[0])] if manage and texts[1] is manage[0] else None
    top = between is not None and all(not (128 <= t[2][0] - g['x'] <= 142) for t in between)
    rows = []
    if im is None:
        return dict(top=top, count=int(count[0][0]) if count else None, header_y=hy, rows=rows)
    arr = np.asarray(im).astype(np.int16)
    y0, y1 = hy + 1, g['y'] + g['h'] - 1
    # Rows = text lines in the contact-name column (ink relative to each line's own row background).
    reg = arr[y0:y1, g['x'] + 128:g['x'] + 250]
    bg = arr[y0:y1, g['x'] + 63:g['x'] + 64]
    ink = (np.abs(reg - bg).max(axis=2) > 40).sum(axis=1) >= 2
    runs, st, gap = [], None, 0
    for i, v in enumerate(list(ink) + [False] * 6):
        if v:
            if st is None:
                st = i
            gap = 0
        elif st is not None:
            gap += 1
            if gap > 4:                       # allow small gaps inside a glyph line
                runs.append((y0 + st, y0 + i - gap + 1)); st, gap = None, 0
    names = [t for t in texts if t[2][1] > hy and 128 <= t[2][0] - g['x'] <= 175]
    for a, b in runs:
        L = b - a
        if L < 6 or L > 30:
            continue
        cy = (a + b) // 2
        band = [g['x'] + 61, cy - 27, 240, 54]
        complete = a > y0 + 1 and b < y1 - 1 and band[1] >= hy - 2 and band[1] + band[3] <= g['y'] + g['h'] + 3
        line = sorted([t for t in names if abs(t[2][1] + t[2][3] / 2 - cy) <= 13], key=lambda t: t[2][0])
        rows.append(dict(name=''.join(t[0].strip() for t in line), text_box=line[0][2] if line else None,
                         band=band, center=(g['x'] + 170, cy), complete=complete,
                         avatar=avatar_crop(arr, g, cy) if complete else None,
                         sig=name_ink(arr, g, cy) if complete else None))
    return dict(top=top, count=int(count[0][0]) if count else None, header_y=hy, rows=rows)


AV_X0, AV_X1, AV_H, AV_MIN, AV_MAX = 86, 116, 30, 27, 32   # window-relative avatar column / height


def avatar_crop(arr, g, cy):
    """Inset avatar pixels (corners excluded: they show the row background)."""
    return arr[cy - 11:cy + 11, g['x'] + AV_X0 + 4:g['x'] + AV_X1 - 4].copy()


def avatar_match(a, b):
    return a is not None and b is not None and a.shape == b.shape and float(np.abs(a - b).mean()) < 10


def name_ink(arr, g, cy):
    """Row fingerprint: text-stroke mask of the name area relative to the row's own background
    (independent of avatar loading, OCR quality, hover or selection colours)."""
    y0, y1 = cy - 15, cy + 15                     # 30 rows; matching uses the inner 24 with +-3 px shift
    reg = arr[y0:y1, g['x'] + 128:g['x'] + 296]
    bg = arr[y0:y1, g['x'] + 63:g['x'] + 64]
    return np.abs(reg - bg).max(axis=2) > 40


def _ink_eq(a, b):
    u = (a | b).sum()
    return u > 15 and (a ^ b).sum() / u < 0.15


def ink_match(a, b, arr=None, g=None, cy=None):
    if a is None or b is None or a.shape != b.shape:
        return False
    return any(_ink_eq(a[3:27], b[3 + d:27 + d]) for d in (0, -1, 1, -2, 2, -3, 3))


def ink_match_at(arr, g, cy, sig):
    return any(ink_match(name_ink(arr, g, cy + dy), sig) for dy in (0, -1, 1, -2, 2))


def link_pages(seen, page_rows):
    """Index in page_rows of the first complete row not yet in `seen`, by avatar overlap (>=2 in order)."""
    comp = [i for i, r in enumerate(page_rows) if r['complete']]

    def same(a, b):
        return ink_match(a['sig'], b['sig']) or bool(canon(a['name']) and canon(b['name']) and similar(a['name'], b['name']))
    # seen[-k:] must equal comp[o:o+k] with k>=2 (o=0) or k>=3 (o>=1: top page rows may be shadowed by the
    # sticky header, or after an in-place relink the processed rows sit mid-page); rows after o+k are new.
    for o in range(len(comp)):
        for k in range(min(len(seen), len(comp) - o), 1 if o == 0 else 2, -1):
            if all(same(seen[-k + j], page_rows[comp[o + j]]) for j in range(k)):
                return comp[o + k] if o + k < len(comp) else len(page_rows)
    # fallback: the last seen row may be unreadable (no name, odd glyphs); anchor on >=3 rows before it
    for o in range(len(comp)):
        for k in range(min(len(seen) - 1, len(comp) - o - 1), 2, -1):
            if all(same(seen[-k - 1 + j], page_rows[comp[o + j]]) for j in range(k)):
                n = o + k + 1
                return comp[n] if n < len(comp) else len(page_rows)
    raise Unknown('page overlap not established: seen tail %r vs page %r'
                  % ([x['name'] for x in seen[-4:]], [r['name'] for r in page_rows]))


class BatchEngine(FastEngine):
    def __init__(self, send, limit, max_rows=None):
        self.send, self.limit, self.after, self.max_rows = send, limit, '*', max_rows
        self.resume_after = 0
        self.from_current = False
        self.ordinal_base = 0
        self.ordinal_offset = 0
        self.run_id = time.strftime('batch_%Y%m%dT%H%M%S') + ('_send' if send else '_nosend')
        self.dir = wxio.OUT / self.run_id
        self.dir.mkdir(mode=0o700)
        self.j = wxfast.Journal(self.dir / 'events.jsonl')
        self.sink = wxfast.DebugSink(self.dir)
        self.x = wxio.X()
        self.q = wxfast.XQ()
        self.epoch = 0
        self.stages = []
        self.ocr_calls = 0
        self.contacts = []          # per-occurrence outcome records
        self.frame_no = 0
        self.seen = []
        self.T0 = time.time()
        self.cold = dict(total_ms=None)

    def dbg(self, tag, im, box=None):
        self.frame_no += 1
        if box is not None:
            x, y, w, h = box['x'], box['y'], box['w'], box['h']
            im = im.crop((x, y, x + w, y + h))
        self.sink.put('%05d_%s.png' % (self.frame_no, tag), im)

    def main_active(self, f):
        o = f['owner']
        if o['active'] != o['main']['id'] or len(o['wechat']) != 1:
            raise Unknown('main not active / transient present')
        return {}

    def scroll(self, st, f, g, button, notches):
        need(f['epoch'] == self.epoch, 'stale frame')
        s = time.time(); live = self.q.observe(self.pid); st.add('window', s)
        need(live['active'] == live['main']['id'] and len(live['wechat']) == 1, 'not on main for scroll')
        self.epoch += 1
        self.j.event(kind='input', stage=st.name, label='scroll%d' % button, notches=notches, epoch=self.epoch)
        s = time.time()
        self.x.move(g['x'] + 180, g['y'] + 450)
        for i in range(notches):
            self.x.xt.XTestFakeButtonEvent(self.x.d, button, 1, 0)
            self.x.xt.XTestFakeButtonEvent(self.x.d, button, 0, 0)
            self.x.x.XSync(self.x.d, 0)
            time.sleep(0.08 if notches <= 10 else 0.003)
        self.x.move(g['x'] + 700, g['y'] + 16)
        st.add('input', s)

    def list_stable(self, g):
        prev = {}

        def cond(f):
            self.main_active(f)
            sig = self.list_sig(f['im'], g)
            same = 'sig' in prev and np.abs(sig - prev['sig']).max() == 0
            prev['sig'] = sig
            if not same:
                raise Unknown('list still changing (scroll/avatars loading)')
            return {}
        return cond

    def list_sig(self, im, g):
        x, y, w, h = absbox(g, (61, 80, 240, 690))
        return np.asarray(im.crop((x, y, x + w, y + h))).astype(np.int16)

    def scan(self, st, f, g):
        texts = self.ocr_box(st, f['im'], absbox(g, W_LIST))
        page = perceive_page(texts, g, f['im'])
        self.dbg('page', f['im'])
        return page

    def read_title(self, im, g):
        """Rec-only OCR of the chat title line, cropped to its ink columns (~50 ms)."""
        x, y, w, h = absbox(g, (314, 40, 560, 28))
        arr = np.asarray(im.crop((x, y, x + w, y + h))).astype(int)
        cols = np.where((arr.max(axis=2) < 170).any(axis=0))[0]
        if not len(cols):
            return ''
        a, b = max(0, cols[0] - 8), min(w, cols[-1] + 9)
        crop = np.asarray(im.crop((x + a, y, x + b, y + h)))[:, :, ::-1].copy()
        res, _ = wxio.ocr_engine()(crop, use_det=False, use_cls=False, use_rec=True)
        self.ocr_calls += 1
        return res[0][0] if res else ''

    def rec_label(self, st, im, box):
        x, y, w, h = box
        crop = np.asarray(im.crop((x - 4, y - 3, x + w + 30, y + h + 3)))[:, :, ::-1].copy()
        s = time.time()
        res, _ = wxio.ocr_engine()(crop, use_det=False, use_cls=False, use_rec=True)
        st.add('ocr', s); st.n['ocr_calls'] += 1; self.ocr_calls += 1
        return res[0][0] if res else ''

    # ------------------------------------------------------------------ one contact
    def process(self, row, prev_band, g, f, ledger, ordinal):
        rec = dict(ordinal=ordinal, row_name=row['name'], stages=[], t0=time.time(), row=row)
        self.contacts.append(rec)
        st = Stage('row_to_profile')
        self.act(st, f, row['center'], 'contact-row', g)
        prev = {}

        def ready(f):
            im = f['im']
            if not row_selected(im, g, row['band']):
                raise Unknown('target row not selected yet')
            if prev_band and prev_band != row['band'] and row_selected(im, g, prev_band):
                raise Unknown('previous row still selected')
            x, y, w, h = absbox(g, (520, 85, 350, 680))
            sig = np.asarray(im.crop((x, y, x + w, y + h)))[::4, ::4].tobytes()
            stable = prev.get('sig') == sig
            prev['sig'] = sig
            if not stable:
                raise Unknown('profile still changing')
            return {}
        f, _ = self.poll(st, 'profile', ready)
        p = None
        for attempt in range(2):
            s = time.time()
            try:
                p = perceive_profile_fast(f['im'], g, row['band'])
                break
            except Unknown as e:
                p_err = str(e)
                st.n['fallbacks'] += 1
            finally:
                st.add('ocr', s); st.n['ocr_calls'] += 1; self.ocr_calls += 1
            time.sleep(0.25); f = self.look(st)
        self.dbg('profile_%04d' % ordinal, f['im'], g)
        rec['stages'].append(self.finish_stage(st))
        if p is None:
            # Not a recognisable friend profile (system/official layouts, deactivated accounts): no send.
            low = re.sub(r'\s+', '', p_err).lower()
            if 'accountisunavailable' in low or 'stoppedusing' in low or 'whohavestopp' in low:
                outcome = 'EXCLUDED_UNAVAILABLE'
            elif any(h in row['name'] for h in SYSTEM_HINTS):
                outcome = 'EXCLUDED_NOT_ORDINARY'
            else:
                outcome = 'SKIPPED_PRE_SEND'
            rec.update(outcome=outcome, reason=p_err[:200])
            return self.close_rec(rec, f)
        rec.update(name=p['name'], weixin_id=p['weixin_id'])
        if fold_wxid(p['weixin_id']) == fold_wxid(ACCOUNT):      # self is decided by Weixin ID only
            rec.update(outcome='EXCLUDED_SELF')
            return self.close_rec(rec, f)
        if not (p['friend_profile'] and p['calls']):
            rec.update(outcome='EXCLUDED_NOT_ORDINARY', reason='no Friend Profile/Voice/Video')
            return self.close_rec(rec, f)
        if p['selected'] and canon(p['name']) and not similar(p['name'], row['name']):
            st2 = Stage('row_reread')
            x0 = g['x'] + 128
            lab = self.rec_label(st2, f['im'], [x0, row['center'][1] - 10, 160, 20])
            self.finish_stage(st2, got=lab)
            if similar(p['name'], lab):
                rec['row_name_reread'] = lab
                row = dict(row, name=lab)
        if p['selected'] and not canon(p['name']) and not canon(row['name']):
            # names made only of emoji/symbols: identity cannot be cross-checked -> never send, but not a fault
            rec.update(outcome='SKIPPED_UNREADABLE_NAME', reason='row and profile names unreadable (emoji/symbols)')
            return self.close_rec(rec, f)
        if not p['selected'] or not (canon(p['name']) and similar(p['name'], row['name'])):
            rec.update(outcome='SKIPPED_PRE_SEND', reason='row/profile association %r vs %r' % (row['name'], p['name']))
            return self.close_rec(rec, f)
        op_key = '%s|%s|wxid:%s' % (REQUEST_ID, ACCOUNT, p['weixin_id'])
        existing = ledger.state(op_key) or self.sent_folded().get(fold_wxid(p['weixin_id']))
        if existing is not None:
            rec.update(outcome='ALREADY_' + existing)
            return self.close_rec(rec, f)
        if self.limit is not None and self.dispatched >= self.limit:
            rec.update(outcome='NOT_ATTEMPTED_LIMIT')
            return self.close_rec(rec, f)

        try:
            f = self.send_chain(rec, p, op_key, g, f, ledger)
        except Unknown as e:
            rec.update(outcome='SKIPPED_PRE_SEND', reason=str(e)[:200])
            f = self.recover(g)
        return self.close_rec(rec, f)

    def sent_folded(self):
        """folded Weixin ID -> ledger state, for every op of this batch (cached; refreshed after each dispatch)."""
        if getattr(self, '_folded', None) is None or self._folded_n != self.dispatched:
            rows = self._ledger.db.execute('SELECT op_key,state FROM ops WHERE request_id=?', (REQUEST_ID,)).fetchall()
            self._folded = {fold_wxid(k.split('|wxid:', 1)[1]): st for k, st in rows}
            self._folded_n = self.dispatched
        return self._folded

    def recover(self, g):
        """Pre-send cleanup only: Escape any panel, return to main."""
        st = Stage('recover')
        o = self.q.observe(self.pid)
        pans = [w for w in o['wechat'] if w['id'] != o['main']['id'] and w['transient'] == o['main']['id']
                and (w['geom']['w'], w['geom']['h']) == PANEL_SIZE]
        if pans:
            # favorites panel still open: press its own Cancel (Escape would go to whichever window is active)
            self.epoch += 1
            pg = pans[0]['geom']
            self.j.event(kind='input', stage='recover', label='panel-cancel', epoch=self.epoch)
            self.x.click(pg['x'] + 520, pg['y'] + 550)
            time.sleep(0.6)
        elif len(o['wechat']) > 1:
            self.epoch += 1
            self.x.key('Escape')
            time.sleep(0.5)
        f, _ = self.poll(st, 'exit', self.main_active)
        self.act(st, f, abspt(self.g, W_CONTACTS_TAB), 'contacts-tab', self.g)
        f, _ = self.poll(st, 'contacts', self.main_active)
        self.finish_stage(st)
        return f

    def profile_settled(self, st, f, p, row):
        """Late-loading sections (e.g. Channels thumbnails) can shift the buttons after the OCR frame.
        Re-look and require the Messages region and profile signature unchanged; else one re-OCR."""
        def region(im):
            x, y = p['messages']
            return np.asarray(im.crop((x - 60, y - 45, x + 60, y + 25))).astype(np.int16)
        time.sleep(0.15)
        f2 = self.look(st)
        if np.abs(region(f2['im']) - region(f['im'])).max() <= 24:
            return f2, p
        st.n['fallbacks'] += 1
        time.sleep(0.4)
        f3 = self.look(st)
        s = time.time()
        try:
            p2 = perceive_profile_fast(f3['im'], self.g, row['band'])
        finally:
            st.add('ocr', s); st.n['ocr_calls'] += 1; self.ocr_calls += 1
        if canon(p2['weixin_id']) != canon(p['weixin_id']):
            raise Unknown('profile identity changed during settle')
        time.sleep(0.15)
        f4 = self.look(st)
        p = dict(p, messages=p2['messages'])
        if np.abs(region(f4['im']) - region(f3['im'])).max() > 24:
            raise Unknown('profile layout still moving')
        return f4, p

    def send_chain(self, rec, p, op_key, g, f, ledger):
        st = Stage('messages_to_chat')
        f, p = self.profile_settled(st, f, p, rec['row'])
        self.act(st, f, p['messages'], 'profile-messages', g)
        try:
            def chat_ready(f):
                self.main_active(f)
                ch = chat_visual(f['im'], g)
                t = self.read_title(f['im'], g)
                if not (canon(t) and (canon(p['name']) in canon(t) or similar(t, p['name']))):
                    raise Unknown('chat title %r not yet %r' % (t, p['name']))
                ch['title'] = t
                return ch
            f, ch = self.poll(st, 'chat', chat_ready)
        except Stop as e:
            raise Unknown(str(e))
        rec['stages'].append(self.finish_stage(st))

        st = Stage('open_favorites')
        self.act(st, f, ch['cube'], 'favorites-entry', g)

        def base(f):
            o = f['owner']
            pans = [w for w in o['wechat'] if w['id'] != o['main']['id']]
            if len(pans) != 1 or pans[0]['transient'] != o['main']['id'] or o['active'] != pans[0]['id'] \
                    or (pans[0]['geom']['w'], pans[0]['geom']['h']) != PANEL_SIZE:
                raise Unknown('panel not yet owned/active')
            v = panel_visual(f['im'], pans[0]['geom'])
            if v['send'] != 'disabled' or any(v['checked']) or not v['all_favorites'] \
                    or not v['search_default'] or not v['first_at_top']:
                raise Unknown('panel not at default zero-select baseline')
            v['panel'] = pans[0]
            return v
        try:
            f, pv = self.poll(st, 'panel', base)
        except Stop as e:
            raise Unknown(str(e))
        panel = pv['panel']; pg = panel['geom']
        rec['stages'].append(self.finish_stage(st))

        st = Stage('select_first')
        first = pv['radios'][0]
        self.act(st, f, (first['x'], first['y']), 'select-first', pg)

        def sel(f):
            o = f['owner']
            if o['active'] != panel['id'] or not any(w['id'] == panel['id'] and w['geom'] == pg for w in o['wechat']):
                raise Unknown('panel identity changed')
            v = panel_visual(f['im'], pg)
            if v['send'] != 'enabled' or v['checked'] != [True] + [False] * (len(v['checked']) - 1) \
                    or abs(v['radios'][0]['y'] - first['y']) > 2:
                raise Unknown('not exactly first selected')
            return v
        try:
            f, sv = self.poll(st, 'selected', sel)
        except Stop as e:
            raise Unknown(str(e))       # recover() Escapes the panel; nothing was sent
        self.dbg('selected_%04d' % rec['ordinal'], f['im'], pg)
        rec['stages'].append(self.finish_stage(st))

        st = Stage('recipient_check')
        s = time.time(); header = read_header_fast(f['im'], pg); st.add('ocr', s)
        st.n['ocr_calls'] += 1; self.ocr_calls += 1
        def ok(h):
            c, pre, nm = canon(h), canon('Sendfavoritesto'), canon(p['name'])
            if not c.startswith(pre) or not nm:
                return False
            rest = c[len(pre):]
            if nm in rest:
                return True
            # one-glyph OCR slips in the header (e.g. 令->合): allow for names >=3 chars, ratio >=0.75
            subst = len(rest) >= len(nm) and sum(a != b for a, b in zip(nm, rest[:len(nm)])) <= 1
            if len(nm) >= 3 and (subst or difflib.SequenceMatcher(None, nm, rest[:len(nm) + 2]).ratio() >= 0.75):
                rec['header_fuzzy'] = True
                return True
            return False
        if not ok(header):
            st.n['fallbacks'] += 1
            header = ' '.join(t[0] for t in self.ocr_box(st, f['im'], absbox(pg, P_HEADER)))
        rec['stages'].append(self.finish_stage(st, header=header))
        if not ok(header):
            raise Unknown('panel header not bound to recipient: %r' % header)
        rec['header'] = header

        if AUTO_RID:
            st = Stage('content_check')
            pt = self.rec_label(st, f['im'], absbox(pg, P_FIRST_TITLE))
            r = title_prefix_ratio(pt, self.fav_title)
            if r < 0.8:
                st.n['fallbacks'] += 1
                pt = ' '.join(t[0] for t in self.ocr_box(st, f['im'], absbox(pg, (255, 85, 380, 36))))
                r = title_prefix_ratio(pt, self.fav_title)
            rec['stages'].append(self.finish_stage(st, title=pt, ratio=round(r, 3)))
            if r < 0.5:
                raise Stop('HALT: first favorite changed during campaign %s: %r vs %r' % (REQUEST_ID, pt, self.fav_title))
            if r < 0.8:
                raise Unknown('panel first favorite title not confirmed: %r' % pt)

        if not self.send:
            st = Stage('cancel_no_send')
            self.act(st, f, abspt(pg, (520, 550)), 'cancel', pg)
            f, _ = self.poll(st, 'exit', self.main_active)
            rec['stages'].append(self.finish_stage(st))
            rec['outcome'] = 'DRY_RUN_PREPARED'
            return self.back_to_list(rec, g, f)

        st = Stage('dispatch')
        intent = dict(request=REQUEST_ID, account=ACCOUNT, mode=MODE, ordinal=rec['ordinal'], row=rec['row_name'],
                      profile=p['name'], weixin_id=p['weixin_id'], panel_id=panel['id'], header=header, run=self.run_id)
        s = time.time(); ledger.put(op_key, 'PREPARED', intent=intent, recipient_ref=json.dumps(intent, ensure_ascii=False)); st.add('ledger', s)
        need(time.time() - f['at'] < 180 and f['epoch'] == self.epoch, 'frame expired/stale before dispatch')
        s = time.time(); live = wxio.observe(); st.add('window', s)
        need(live['active'] == panel['id'] and live['main']['geom'] == g and len(live['wechat']) == 2,
             'context changed before dispatch')
        s = time.time(); ledger.put(op_key, 'DISPATCHING', result=dict(at=time.time())); st.add('ledger', s)
        pt = abspt(pg, P_SEND_CLICK)
        try:
            self.epoch += 1
            self.j.event(kind='input', stage='dispatch', label='SEND', point=pt, op_key=op_key, epoch=self.epoch)
            s = time.time(); self.x.click(*pt); st.add('input', s)
        except BaseException as e:
            ledger.put(op_key, 'UNKNOWN', result=dict(error=repr(e)))
            self.j.event(kind='send_unknown', error=repr(e))
            rec['outcome'] = 'UNKNOWN'
            raise Stop('send outcome unknown: %r' % e)
        s = time.time(); ledger.put(op_key, 'SEND_CLICKED', result=dict(at=time.time(), mode=MODE)); st.add('ledger', s)
        self.dispatched += 1
        rec['outcome'] = 'SEND_CLICKED'
        rec['to_send_clicked_ms'] = round((time.time() - rec['t0']) * 1000, 1)
        self.j.event(kind='send_clicked', op_key=op_key, ordinal=rec['ordinal'])
        rec['stages'].append(self.finish_stage(st))

        st = Stage('panel_exit')
        try:
            f, _ = self.poll(st, 'exit', self.main_active)
            rec['stages'].append(self.finish_stage(st))
        except Stop as e:
            self.j.event(kind='UI_STALLED', reason=str(e))
            rec['stages'].append(self.finish_stage(st, ui_stalled=True))
            raise Stop('UI stalled after send (SEND_CLICKED stands, no re-press): %s' % e)
        if self.dispatched % 25 == 1:
            self.dbg('after_send_%04d' % rec['ordinal'], f['im'], g)
        return self.back_to_list(rec, g, f)

    def campaign(self, g, f, ledger):
        """Favorites tab -> first favorite title -> REQUEST_ID (see module doc)."""
        global REQUEST_ID
        st = Stage('campaign')
        self.act(st, f, abspt(g, W_FAV_TAB), 'favorites-tab', g)

        def all_fav(f):
            self.main_active(f)
            if not close(f['im'].getpixel(abspt(g, W_FAV_ALL_PX)), GREEN_ROW, 12):
                raise Unknown('All Favorites not selected')
            return {}
        f, _ = self.poll(st, 'contacts', all_fav)
        texts = self.ocr_box(st, f['im'], absbox(g, W_FAV_VIEW))
        flat = lambda t: re.sub(r'\s+', '', t[0])
        rel = lambda t: (t[2][0] - g['x'], t[2][1] - g['y'])
        search = any(flat(t) == 'SearchFavorites' for t in texts)
        header = any(flat(t) == 'AllFavorites' and rel(t)[0] > 301 for t in texts)
        first = [t for t in texts if 345 <= rel(t)[0] <= 375 and 100 <= rel(t)[1] <= 130]
        self.dbg('favorites', f['im'], g)
        need(search and header and len(first) == 1 and canon(first[0][0]),
             'favorites view not at default/top: %r' % [t[0] for t in texts])
        self.fav_title = first[0][0].strip()
        rid, new = resolve_campaign(ledger, self.fav_title, create=self.send)
        self.j.event(kind='campaign', title=self.fav_title, request=rid, new=new)
        REQUEST_ID = v1.REQUEST_ID = rid
        self.finish_stage(st, title=self.fav_title, request=rid, new=new)
        return f

    def back_to_list(self, rec, g, f):
        st = Stage('return_to_list')
        self.act(st, f, abspt(g, W_CONTACTS_TAB), 'contacts-tab', g)
        f, _ = self.poll(st, 'contacts', self.main_active)
        rec['stages'].append(self.finish_stage(st))
        return f

    def close_rec(self, rec, f):
        rec.pop('row', None)
        rec['cycle_ms'] = round((time.time() - rec.pop('t0')) * 1000, 1)
        self.j.event(kind='contact', **{k: v for k, v in rec.items() if k != 'stages'})
        self.j.f.flush()
        return f

    # ------------------------------------------------------------------ batch
    def run(self):
        T0 = self.T0 = time.time()
        self.dispatched = 0
        st = Stage('cold_start')
        lockfd = os.open(PROD_LOCK, os.O_RDWR)
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('production controller lock busy')
        s = time.time(); ledger = self._ledger = Ledger(LEDGER)
        need(not ledger.unresolved(), 'ledger has unresolved operations: %r' % ledger.unresolved()); st.add('ledger', s)
        self.j.event(kind='start', mode=MODE, request=REQUEST_ID, send=self.send, limit=self.limit,
                     resume_after=self.resume_after, from_current=self.from_current, ordinal_base=self.ordinal_base)
        s = time.time()
        eng = wxio.ocr_engine()
        warm = np.full((48, 200, 3), 255, np.uint8); cv2.putText(warm, 'warmup', (5, 35), 0, 1, (0, 0, 0), 2)
        eng(warm); eng(warm, use_det=False, use_cls=False, use_rec=True); st.add('ocr', s)
        s = time.time(); full = wxio.observe(); st.add('window', s)
        self.pid = full['pid']; g = self.g = full['main']['geom']
        need((g['w'], g['h']) == MAIN_SIZE, 'main geometry not calibrated')
        if full['active'] != full['main']['id']:
            need(len(full['wechat']) == 1, 'unexpected WeChat transient at start')
            self.epoch += 1
            s = time.time(); self.x.click(*abspt(g, W_ACTIVATE)); st.add('input', s)
        f, _ = self.poll(st, 'popup_gone', self.main_active)
        self.act(st, f, abspt(g, W_AVATAR), 'avatar', g)

        def popup(f):
            pops = [w for w in f['owner']['wechat'] if w['id'] != f['owner']['main']['id']]
            if len(pops) != 1 or f['owner']['active'] != pops[0]['id']:
                raise Unknown('self popup not yet shown')
            return pops[0]['geom']
        f, pgeo = self.poll(st, 'popup', popup)
        acc = None
        for attempt in range(2):
            texts = self.ocr_box(st, f['im'], [pgeo['x'], pgeo['y'], pgeo['w'], pgeo['h']])
            ids = [re.sub(r'\s+', '', t[0]).split(':', 1)[1] for t in texts
                   if re.sub(r'\s+', '', t[0]).lower().startswith('weixinid:')]
            if len(ids) == 1:
                acc = ids[0]; break
            st.n['fallbacks'] += 1; time.sleep(0.2); f = self.look(st)
        self.epoch += 1
        s = time.time(); self.x.key('Escape'); st.add('input', s)
        need(acc == ACCOUNT, 'wrong/unknown account: %r' % acc)
        f, _ = self.poll(st, 'popup_gone', self.main_active)
        self.cold = self.finish_stage(st, account=acc)
        if AUTO_RID:
            f = self.campaign(g, f, ledger)

        # Contacts tab, scroll to top, top proof.
        st = Stage('contacts_top' if not self.from_current else 'contacts_current')
        self.act(st, f, abspt(g, W_CONTACTS_TAB), 'contacts-tab', g)
        f, _ = self.poll(st, 'contacts', self.main_active)
        if self.from_current:
            # Continue from where the list is now: the selected (green) row is the last contact processed.
            f, _ = self.poll(st, 'scroll', self.list_stable(g))
            page = self.scan(st, f, g)
            header_count = page['count']
            comp = [i for i, r in enumerate(page['rows']) if r['complete']]
            sel = [i for i in comp if row_selected(f['im'], g, page['rows'][i]['band'])]
            pre = [page['rows'][i] for i in comp if sel and i <= sel[0]]
            self.seen.extend(dict(name=r['name'], avatar=r['avatar'], sig=r['sig']) for r in pre)
            self.ordinal_offset = self.ordinal_base - len(pre)
            self.current_start = (sel[0] + 1) if sel else (comp[0] if comp else len(page['rows']))
            self.current_prev_band = page['rows'][sel[0]]['band'] if sel else None
            self.j.event(kind='from_current', selected=page['rows'][sel[0]]['name'] if sel else None,
                         ordinal_base=self.ordinal_base, prepopulated=len(pre),
                         page=[r['name'] for r in page['rows']])
            self.finish_stage(st, header_count=header_count, selected=bool(sel))
        for attempt in range(0 if self.from_current else 60):
            if attempt == 0 or still:
                page = self.scan(st, f, g)
                if page['top']:
                    break
            before = self.list_sig(f['im'], g)
            self.scroll(st, f, g, 4, 100)
            f, _ = self.poll(st, 'scroll', self.main_active)
            still = np.abs(self.list_sig(f['im'], g) - before).max() == 0
        if not self.from_current:
            need(page['top'], 'could not establish list top')
            header_count = page['count']
            self.finish_stage(st, header_count=header_count)

        seen = self.seen          # ordered row names (occurrences) of the Contacts group
        prev_band = getattr(self, 'current_prev_band', None)
        page_no = 0
        consecutive_fail = 0
        tail = None
        while True:
            page_no += 1
            if page_no == 1 and self.from_current:
                start = self.current_start
            elif page_no == 1:
                start = next((i for i, r in enumerate(page['rows']) if r['complete']), len(page['rows']))
            else:
                start, err = None, None
                for attempt in range(4):
                    try:
                        start = link_pages(seen, page['rows'])
                        break
                    except Unknown as e:
                        err = e
                        if attempt == 3:
                            break
                        # overshoot (wheel acceleration) or transient render: step back up and re-scan
                        self.j.event(kind='relink_back', attempt=attempt + 1, seen=len(seen))
                        st = Stage('scroll_back')
                        self.scroll(st, f, g, 4, 3)
                        f, _ = self.poll(st, 'scroll', self.list_stable(g))
                        page = self.scan(st, f, g)
                        self.finish_stage(st)
                if start is None:
                    raise Stop(str(err))
            todo = [r for r in page['rows'][start:]]
            relink = False
            for i, r in enumerate(todo):
                if not r['complete']:
                    need(i == len(todo) - 1, 'partial row in the middle of page')
                    break
                occ = dict(name=r['name'], avatar=r['avatar'], sig=r['sig'])
                if len(seen) < self.resume_after:
                    seen.append(occ)            # resume: counted from page linking only, not opened
                    continue
                # cheap re-check that the page is still where we cached it (avatar at the cached position)
                if self.contacts:
                    st = Stage('page_check')
                    s0 = time.time()
                    arr = np.asarray(f['im']).astype(np.int16)
                    ok = ink_match_at(arr, g, r['center'][1], r['sig'])
                    st.add('classify', s0)
                    if not ok and canon(r['name']):
                        lab = self.rec_label(st, f['im'], [g['x'] + 128, r['center'][1] - 10, 160, 20])
                        ok = similar(lab, r['name'])
                    self.finish_stage(st, expect=r['name'], ok=ok)
                    if not ok:
                        relink = True       # list shifted under us: re-scan and re-link in place
                        self.j.event(kind='relink', at=r['name'], seen=len(seen))
                        break
                seen.append(occ)
                f = self.process(r, prev_band, g, f, ledger, self.ordinal_offset + len(seen))
                if self.max_rows is not None and len(seen) >= self.max_rows:
                    return self.finish_batch(T0, seen, dict(stopped='max_rows=%d' % self.max_rows, occurrences=len(seen),
                                                            header_count=header_count, complete=False))
                prev_band = r['band']
                last = self.contacts[-1]['outcome']
                consecutive_fail = consecutive_fail + 1 if last == 'SKIPPED_PRE_SEND' else 0
                need(consecutive_fail < 2, 'two consecutive pre-send failures; pausing page')
                # refresh frame for next row (we are back on the Contacts list)
                st = Stage('look'); f = self.look(st); self.finish_stage(st)
            if relink:
                self.relinks = getattr(self, 'relinks', 0) + 1
                need(self.relinks <= 50, 'too many in-place relinks')
                st = Stage('relink')
                time.sleep(0.3)
                f = self.look(st)
                page = self.scan(st, f, g)
                self.finish_stage(st)
                prev_band = next((r['band'] for r in page['rows'] if row_selected(f['im'], g, r['band'])), None)
                page_no = max(page_no, 1)        # >=1 so the next iteration links against `seen`
                continue
            # next page
            st = Stage('scroll_page')
            before = self.list_sig(f['im'], g)
            self.scroll(st, f, g, 5, SCROLL_NOTCHES)
            f, _ = self.poll(st, 'scroll', self.list_stable(g))
            moved = np.abs(self.list_sig(f['im'], g) - before).max() > 0
            if not moved:
                # confirm with a second scroll attempt
                self.scroll(st, f, g, 5, SCROLL_NOTCHES)
                f, _ = self.poll(st, 'scroll', self.list_stable(g))
                moved = np.abs(self.list_sig(f['im'], g) - before).max() > 0
            if not moved:
                self.finish_stage(st, moved=False)
                tail = dict(scroll_no_change=2, occurrences=self.ordinal_offset + len(seen), header_count=header_count,
                            complete=self.ordinal_offset + len(seen) == header_count,
                            ordinal_note='approx (continued from current position)' if self.from_current else None)
                self.j.event(kind='tail', **tail)
                break
            page = self.scan(st, f, g)
            self.finish_stage(st, moved=True, page=page_no + 1)
            prev_band = None      # positions changed; previous selection may be off-page or moved
            for r in page['rows']:
                if row_selected(f['im'], g, r['band']):
                    prev_band = r['band']
        return self.finish_batch(T0, seen, tail)

    def finish_batch(self, T0, seen, tail):
        wall = time.time() - T0
        by = {}
        for c in self.contacts:
            by.setdefault(c['outcome'], []).append(c.get('name') or c['row_name'])
        sent = [c for c in self.contacts if c['outcome'] == 'SEND_CLICKED']
        agg = {}
        for c in self.contacts:
            for s in c['stages']:
                a = agg.setdefault(s['stage'], dict(n=0, total_ms=0.0, ocr_ms=0.0, wait_ms=0.0))
                a['n'] += 1
                for k in ('total_ms', 'ocr_ms', 'wait_ms'):
                    a[k] += s[k]
        for a in agg.values():
            a.update(avg_ms=round(a['total_ms'] / a['n'], 1), total_ms=round(a['total_ms'], 1),
                     ocr_ms=round(a['ocr_ms'], 1), wait_ms=round(a['wait_ms'], 1))
        out = dict(mode=MODE, send=self.send, wall_s=round(wall, 3), ocr_calls=self.ocr_calls,
                   cold_start_ms=self.cold['total_ms'], occurrences=len(seen), order=[x['name'] for x in seen], tail=tail,
                   outcomes={k: v for k, v in by.items()}, sent=len(sent),
                   avg_cycle_sent_ms=round(sum(c['cycle_ms'] for c in sent) / len(sent), 1) if sent else None,
                   avg_to_send_clicked_ms=round(sum(c['to_send_clicked_ms'] for c in sent) / len(sent), 1) if sent else None,
                   per_stage=agg, contacts=self.contacts, all_stages=self.stages,
                   debug_frames_dropped=self.sink.dropped, evidence=str(self.dir))
        self.j.event(kind='finish', **{k: v for k, v in out.items() if k not in ('contacts', 'all_stages', 'per_stage')})
        self.sink.close(); self.j.close()
        (self.dir / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return out


if __name__ == '__main__':
    send = '--send' in sys.argv
    need(send or '--no-send' in sys.argv, 'specify --send or --no-send')
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    max_rows = int(sys.argv[sys.argv.index('--max-rows') + 1]) if '--max-rows' in sys.argv else None
    eng = BatchEngine(send, limit, max_rows)
    if '--resume-after' in sys.argv:
        eng.resume_after = int(sys.argv[sys.argv.index('--resume-after') + 1])
    if '--from-current' in sys.argv:
        eng.from_current = True
        eng.ordinal_base = int(sys.argv[sys.argv.index('--ordinal-base') + 1]) if '--ordinal-base' in sys.argv else 0
    try:
        r = eng.run()
        print(json.dumps({k: v for k, v in r.items() if k not in ('contacts', 'all_stages')}, ensure_ascii=False, indent=1))
    except (Stop, Unknown, Exception) as e:
        e = Stop('%s: %s' % (type(e).__name__, e)) if not isinstance(e, Stop) else e
        eng.j.event(kind='stop', reason=str(e))
        try:
            eng.finish_batch(eng.T0, eng.seen, dict(stopped=str(e)))
        except Exception as e2:
            print('finish failed', e2)
        print('STOP:', e)
        sys.exit(2)
