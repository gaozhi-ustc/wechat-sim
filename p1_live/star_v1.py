"""star_v1: mark as Starred every Contacts friend who has written to the owner since SINCE (default 2026-10-01).

Interaction = at least one left-side (friend) message, or a friend system line (recalled / patted), dated >= SINCE.
Chats where only the owner wrote (right-side bubbles) since SINCE, or with nothing since SINCE, are not starred.

Traversal is batch_v2's (top proof, page linking by name-ink, in-place relink, tail proof, --from-current).
Per Contacts row:
  click row (select) -> right-click -> menu read (rec-only OCR) -> 'Messages' -> chat title check
  -> scan the chat bottom-up (pixel blocks: L/R bubbles, centered lines; rec-OCR of centered lines only),
     scrolling up until decided: a recent timestamp above a friend message -> STAR; an older-than-SINCE
     timestamp or the top of the history -> no star
  -> back to Contacts -> STAR only: profile OCR (self check, Weixin ID) -> right-click -> menu item must read
     'Starred' -> click it -> re-open the menu to verify the item changed.
Zero LLM calls. The menu's third item is 'Delete Contact': every menu click is preceded by an OCR of that item.

Usage: python3 -I star_v1.py --star | --dry-run [--max-rows N] [--from-current [--ordinal-base N]]
Env: WX_STAR_SINCE=2026-10-01, WX_STAR_LEDGER (default p1_live/ledger_star_<account>.sqlite3).
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# a fixed request id disables batch_v2's favorites "campaign" step; the star ledger is separate from send ledgers
os.environ['WX_REQUEST_ID'] = os.environ.get('WX_STAR_ID', 'star_since_' + os.environ.get('WX_STAR_SINCE', '2026-10-01'))
os.environ['WX_LEDGER'] = os.environ.get('WX_STAR_LEDGER') or os.path.join(
    HERE, 'ledger_star_%s.sqlite3' % os.environ.get('WX_ACCOUNT', 'gaozhi-xinshu'))

import batch_v2 as bv  # noqa: E402
from batch_v2 import (BatchEngine, Stage, Unknown, Stop, need, wxio, wxfast, absbox, abspt, canon, similar,  # noqa: E402
                      fold_wxid, row_selected, perceive_profile_fast, SYSTEM_HINTS, ACCOUNT, W_CONTACTS_TAB, WAITS)
import numpy as np  # noqa: E402

MODE = 'star_v1'
SINCE = tuple(int(v) for v in os.environ.get('WX_STAR_SINCE', '2026-10-01').split('-'))   # (y, m, d)
TODAY = time.localtime()
WAITS.update(menu=(0.15, 3.0), chat_open=(0.30, 4.0), chat_scroll=(0.25, 2.5), star=(0.15, 2.5))

# chat message area (window-relative); scrollbar (x>=1075) excluded
CY0, CY1, CX0, CX1, CMID, CBG = 82, 627, 301, 1074, 694.5, 250
CHAT_SCROLL_NOTCHES = 6                  # 10 notches sometimes moved > the 545 px viewport (no overlap to register)
SHORT_SCROLL_PX = 150                # a 6-notch scroll moves ~220+ px; much less means the top was reached
MAX_CHAT_SCROLLS = 40
STABLE_FRAC = float(os.environ.get('WX_STAR_STABLE_FRAC', '0.005'))   # allowed changing pixels (animated stickers)
# right-click menu, relative to the right-click point: rec boxes of the three items and click points
MENU_BOX = dict(messages=(8, 8, 145, 28), starred=(8, 41, 145, 28), delete=(8, 82, 145, 28))
MENU_CLICK = dict(messages=(45, 22), starred=(40, 55))
RCLICK_X = 200                       # window-relative x of the right-click inside a Contacts row
W_PROFILE_MORE = (838, 107)          # profile header '...' button -> Edit Contact / ... / Star|Unstar / Block / Delete
W_PROFILE_MENU = (842, 110, 225, 235)
WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', '星期', '周')
_DIGITS = str.maketrans({'O': '0', 'o': '0', 'D': '0', 'l': '1', 'I': '1', '|': '1', 'i': '1', 'S': '5', 'B': '8', '：': ':'})


# ---------------------------------------------------------------- pure chat perception

def chat_blocks(arr):
    """Vertical blocks of the chat area: side L (friend, avatar column at x~321), R (owner), C (centered line)."""
    reg = arr[CY0:CY1, CX0:CX1]
    ink = np.abs(reg - CBG).max(axis=2) > 8
    rows = ink.any(axis=1)
    out, st, gap = [], None, 0
    for i, v in enumerate(list(rows) + [False] * 5):
        if v:
            if st is None:
                st = i
            gap = 0
        elif st is not None:
            gap += 1
            if gap > 3:
                e = i - gap + 1
                cols = np.where(ink[st:e].any(axis=0))[0]
                x0, x1 = CX0 + int(cols[0]), CX0 + int(cols[-1])
                side = 'L' if x0 <= 380 else 'R' if x1 >= 1010 else 'C'
                if side == 'L' and e - st < 30 and st > 0 and e < CY1 - CY0:
                    # friend messages are at least avatar-tall (36 px); a short full-width line starting at the left
                    # edge is a system notice (e.g. "...开启了朋友验证，你还不是他（她）朋友...")
                    side = 'C'
                out.append(dict(y0=CY0 + st, y1=CY0 + e, x0=x0, x1=x1, side=side,
                                top_cut=st == 0, centered=abs((x0 + x1) / 2 - CMID) <= 20))
                st, gap = None, 0
    return out


def classify_line(text):
    """Centered chat line -> ('ts', recent: bool) | ('friend', None) | ('sys', None) | ('unknown', None)."""
    s = re.sub(r'\s+', ' ', (text or '').strip())
    low = s.lower()
    t = s.translate(_DIGITS)
    if re.fullmatch(r'\d{1,2}:\d{2}', t):
        return 'ts', True
    if low.startswith('yesterday') or s.startswith('昨天'):
        return 'ts', True
    if any(low.startswith(w) for w in WEEKDAYS) and re.search(r'\d{1,2}:\d{2}', t):
        # weekday form = within the last week but before yesterday: resolve the actual date
        import datetime
        today = datetime.date(TODAY.tm_year, TODAY.tm_mon, TODAY.tm_mday)
        wd = next((i for i, w in enumerate(WEEKDAYS[:7]) if low.startswith(w)), None)
        if wd is None:
            return 'ts', SINCE <= (today.year, today.month, today.day)      # 星期/周 forms: be conservative
        d = today - datetime.timedelta(days=((today.weekday() - wd) % 7) or 7)
        return 'ts', (d.year, d.month, d.day) >= SINCE
    m = re.match(r'^(\d{4})[/年.-](\d{1,2})[/月.-](\d{1,2})', t.replace(' ', ''))
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return 'ts', (y, mo, int(m.group(3))) >= SINCE
    m = re.match(r'^(\d{2})/(\d{1,2})/(\d{1,2})', t.replace(' ', ''))
    if m:
        y, mo = 2000 + int(m.group(1)), int(m.group(2))
        return 'ts', (y, mo, int(m.group(3))) >= SINCE
    m = re.match(r'^(\d{1,2})[/月](\d{1,2})', t.replace(' ', ''))
    if m and re.search(r'\d{1,2}:\d{2}$', t.replace(' ', '')):
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            # no year shown: the current year; a month after the current one cannot be this year
            y = TODAY.tm_year if mo <= TODAY.tm_mon else TODAY.tm_year - 1
            return 'ts', (y, mo, d) >= SINCE
    if ('recalled a message' in low and not low.startswith('you')) or \
            ('撤回了一条消息' in s and not s.startswith('你')):
        return 'friend', None
    if ('patted' in low and not low.startswith(('you', 'i '))) or ('拍了拍' in s and not s.startswith(('我', '你'))):
        return 'friend', None
    if re.search(r'\d{1,2}:\d{2}', t) and len(s) <= 24:
        return 'unknown', None        # looks like a timestamp but did not parse
    return 'sys', None


def row_hashes(arr):
    reg = np.ascontiguousarray(arr[CY0:CY1, CX0:CX1])
    return np.array([hash(reg[i].tobytes()) for i in range(reg.shape[0])], dtype=np.int64)


BLANK_ROW = None


def scroll_shift(old, new):
    """Content shift d (>0: content moved down) such that new[d:] ~ old[:-d]; 0 if unchanged; None if no match.
    Tolerant: animated stickers / hover effects change a few rows, so >=85% of the non-blank rows must match."""
    global BLANK_ROW
    if BLANK_ROW is None:
        BLANK_ROW = hash(np.full((CX1 - CX0, 3), CBG, np.int16).tobytes())
    n = len(old)
    ink = old != BLANK_ROW
    if not ink.any():
        return 0 if np.array_equal(old, new) else None
    if (old == new)[ink].mean() >= 0.97:
        return 0
    best, bd = 0.0, None
    for d in range(1, n - 40):
        m = ink[:n - d]
        if m.sum() < 10:
            continue
        fr = (new[d:] == old[:n - d])[m].mean()
        if fr > best:
            best, bd = fr, d
            if fr == 1.0:
                break
    return bd if best >= 0.85 else None


def sig_stable(a, b):
    """two subsampled chat-area signatures equal up to small animated regions (<0.5% of pixels)"""
    if a is None or b is None or a.shape != b.shape:
        return False
    return (np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=-1) > 8).mean() < STABLE_FRAC


def name_match(row_name, title):
    r, t = canon(row_name), canon(title)
    if not r or not t:
        return bool(t)                 # emoji/symbol-only names: any title (row -> Messages is direct)
    if r == t or similar(row_name, title) or (len(r) >= 2 and t.startswith(r)):
        return True
    import difflib                     # row names are often truncated with '...'
    return len(r) >= 3 and difflib.SequenceMatcher(None, r, t[:len(r)]).ratio() >= 0.75


# ---------------------------------------------------------------- engine

class StarEngine(BatchEngine):
    def __init__(self, star, max_rows=None):
        super().__init__(star, None, max_rows)
        old = self.dir
        self.run_id = time.strftime('star_%Y%m%dT%H%M%S') + ('_star' if star else '_dry')
        self.dir = wxio.OUT / self.run_id
        old.rename(self.dir)           # BatchEngine already opened its journal / sink inside `old`
        self.j.f.close()
        self.j = wxfast.Journal(self.dir / 'events.jsonl')
        self.sink.dir = self.dir
        self.starred = 0
        self.resume_name = None
        self._resumed = False
        self.redo_current = True       # --from-current re-checks the selected row (it may have been interrupted)

    # -- resume positioning: entering the Contacts tab scrolls the list back to the top, so the position has to
    #    be restored *after* that, from the list_stable() hook the from_current path calls exactly once.
    def on_contacts_tab(self):
        g = self.g
        im = wxio.ImageGrab.grab(xdisplay=':1').convert('RGB')
        return any('contacts' in canon(t[0]) for t in wxio.ocr(im, [g['x'] + 50, g['y'] + 30, 300, 80]))

    def list_stable(self, g):
        if self.resume_name and not self._resumed:
            self._resumed = True
            try:
                self.position_at(self.resume_name, g)
            except Exception as e:
                self.j.event(kind='resume_position_failed', name=self.resume_name, error=str(e)[:120])
        return super().list_stable(g)

    def position_at(self, name, g):
        """Scroll the Contacts list until `name` is visible, then click it (used to resume a stopped sweep).

        Uses its own screen grabs: the engine's frame cache does not always show the effect of a wheel burst.
        """
        st = Stage('resume_position')
        X = self.x
        target = canon(name)

        def rows():
            im = wxio.ImageGrab.grab(xdisplay=':1').convert('RGB')
            out = []
            for t, _s, b in wxio.ocr(im, absbox(g, bv.W_LIST)):
                if 128 <= b[0] - g['x'] <= 175:
                    out.append((t.strip(), b[1] + b[3] // 2))
            return out

        def wheel(n, button):
            X.move(g['x'] + 180, g['y'] + 450)
            for _ in range(n):
                X.xt.XTestFakeButtonEvent(X.d, button, 1, 0)
                X.xt.XTestFakeButtonEvent(X.d, button, 0, 0)
                X.x.XSync(X.d, 0)
                time.sleep(0.003)
            X.move(g['x'] + 700, g['y'] + 16)
            time.sleep(1.0)

        # Clicking a contact row opens its profile and moves the scroll focus away from the list, so focus is
        # taken on a letter header instead (single character) — and only if the first wheel burst does nothing.
        def focus_list():
            rs = rows()
            heads = [(n, y) for n, y in rs if len(canon(n)) == 1 or canon(n) in ('sep.', 'starred', 'tarred')]
            if heads:
                X.click(g['x'] + 170, g['y'] + heads[0][1])
                time.sleep(0.6)
                return True
            return False
        button, stuck, flips = 5, 0, 0
        deadline = time.time() + 300
        while time.time() < deadline:
            rs = rows()
            hit = [y for n, y in rs if canon(n) == target or (target and target in canon(n))]
            if hit:
                X.click(g['x'] + 170, g['y'] + hit[0])
                time.sleep(0.9)
                self.j.event(kind='resume_positioned', name=name, y=hit[0])
                return
            before = [n for n, _ in rs]
            wheel(1500, button)
            if [n for n, _ in rows()] == before:
                if not focus_list():
                    break
                wheel(1500, button)
            if [n for n, _ in rows()] == before:
                stuck += 1
                if stuck >= 2:
                    button = 4 if button == 5 else 5
                    stuck, flips = 0, flips + 1
                    if flips >= 3:
                        break
            else:
                stuck = 0
        raise Stop('could not position at %r' % name)

    def scan(self, st, f, g):
        """Drop only the 'Starred' section's label/unnamed rows; starred friends themselves are scanned like
        everyone else (their re-verification ends in ALREADY_STARRED, never re-clicked).

        The old window-based drop (label .. first letter header) broke when the section grew longer than one
        viewport: with no letter header in view it wiped the whole first page, leaving `seen` empty, and the
        page-2 overlap then failed with 'page overlap not established: seen tail [] vs page []'."""
        texts = self.ocr_box(st, f['im'], absbox(g, bv.W_LIST))
        # rapidocr occasionally returns a box whose coordinates are not numeric (one frame, hard to reproduce):
        # coerce them so a single odd entry cannot kill a whole sweep. Non-numeric geometry -> drop the entry.
        clean = []
        for t in texts:
            try:
                x, y, w, h = (int(v) for v in t[2])
            except (TypeError, ValueError):
                continue
            clean.append((t[0], t[1], [x, y, w, h]))
        texts = clean
        try:
            page = bv.perceive_page(texts, g, f['im'])
        except Unknown as e:
            # a scroll animation can render the sticky 'Contacts' header twice (or a search view slips in):
            # take a fresh frame once instead of aborting the whole run
            if 'header not unique' not in str(e):
                raise
            time.sleep(0.4)
            f = self.look(st)
            texts = self.ocr_box(st, f['im'], absbox(g, bv.W_LIST))
            page = bv.perceive_page(texts, g, f['im'])
        self.dbg('page', f['im'])
        rel = lambda t: (t[2][0] - g['x'], t[2][1] + t[2][3] / 2)       # (window x, absolute y centre)
        star_h = [rel(t)[1] for t in texts if canon(t[0]) in ('starred', 'tarred') and 100 <= rel(t)[0] < 128]
        if star_h:
            y0 = star_h[0] - 14
            nxt = [rel(t)[1] for t in texts
                   if re.fullmatch(r'[A-Z#]', t[0].strip()) and rel(t)[0] < 110 and rel(t)[1] > star_h[0]]
            y1 = nxt[0] if nxt else 10 ** 6
            drop = [r for r in page['rows'] if y0 <= r['center'][1] <= y1 and not canon(r['name'])]
            if drop:
                self.j.event(kind='skip_starred_section', rows=[r['name'] for r in drop])
                page['rows'] = [r for r in page['rows'] if r not in drop]
        return page

    # -- menu
    def menu_text(self, st, im, p, item):
        x, y, w, h = MENU_BOX[item]
        return self.rec_label(st, im, [p[0] + x, p[1] + y, w - 30, h])

    def open_menu(self, st, f, row, g):
        p = (g['x'] + RCLICK_X, row['center'][1])
        self.menu_probes = [(p[0] + 150, p[1] + 8)]
        need(f['epoch'] == self.epoch, 'stale frame')
        s = time.time(); live = self.q.observe(self.pid); st.add('window', s)
        need(live['active'] == live['main']['id'] and len(live['wechat']) == 1, 'not on main for right-click')
        self.epoch += 1
        self.j.event(kind='input', stage=st.name, label='row-menu', point=p, epoch=self.epoch)
        s = time.time(); self.x.click(p[0], p[1], 3); st.add('input', s)

        def shown(f):
            t = self.menu_text(st, f['im'], p, 'messages')
            if canon(t) != canon('Messages'):
                raise Unknown('menu not shown: %r' % t)
            return dict(starred=self.menu_text(st, f['im'], p, 'starred'),
                        delete=self.menu_text(st, f['im'], p, 'delete'))
        f, m = self.poll(st, 'menu', shown)
        if not canon(m['starred']) and not canon(m['delete']):
            m['self'] = True               # the owner's own row: the menu has only 'Messages'
        else:
            need(canon(m['delete']) == canon('DeleteContact'), 'unexpected menu layout: %r' % m)
        return f, p, m

    def close_menu(self, st, probes=None):
        self.epoch += 1
        s = time.time(); self.x.key('Escape'); st.add('input', s)
        return self.wait_menu_closed(st, probes or self.menu_probes)

    def wait_menu_closed(self, st, probes):
        """Popup menus are not client windows: wait until the probe pixels (inside the menu, on the empty
        profile pane when closed) show the pane background 250 instead of the menu background 247."""
        def closed(f):
            self.main_active(f)
            if any(f['im'].getpixel(pt)[:3] != (250, 250, 250) for pt in probes):
                raise Unknown('menu still open')
            return {}
        f, _ = self.poll(st, 'exit', closed)
        return f

    # -- chat analysis
    def scan_chat(self, st, g, rec):
        """-> (decision, evidence). decision: STAR | OWNER_ONLY | NONE_SINCE | NO_MESSAGES | UNSURE"""
        pending = False                # friend message(s) seen whose governing timestamp is not yet known
        seen_any = False
        lines = []
        old_h = None
        boundary = CY1                 # blocks with y0 <= boundary are new in the current frame
        prev_arr = rec.pop('_chat_arr')
        short_top = False
        for n in range(MAX_CHAT_SCROLLS + 1):
            arr = prev_arr
            bl = chat_blocks(arr)
            seen_any = seen_any or bool(bl)
            for b in sorted([b for b in bl if b['y0'] <= boundary], key=lambda b: -b['y0']):
                if b['top_cut']:
                    break              # partially visible at the top: handled after the next scroll
                if b['side'] == 'L':
                    pending = True
                    continue
                if b['side'] != 'C':
                    continue
                if not b['centered']:
                    continue
                crop = arr[b['y0'] - 4:b['y1'] + 4, b['x0'] - 10:b['x1'] + 11]
                s = time.time()
                if b['y1'] - b['y0'] <= 22:
                    res, _ = wxio.ocr_engine()(crop[:, :, ::-1].astype(np.uint8).copy(), use_det=False, use_cls=False, use_rec=True)
                    text = res[0][0] if res else ''
                else:
                    res, _ = wxio.ocr_engine()(crop[:, :, ::-1].astype(np.uint8).copy())
                    text = ' '.join(r[1] for r in sorted(res or [], key=lambda r: r[0][0][1]))
                st.add('ocr', s); st.n['ocr_calls'] += 1; self.ocr_calls += 1
                kind, recent = classify_line(text)
                lines.append((text, kind, recent))
                if kind == 'ts':
                    if recent and pending:
                        return 'STAR', dict(at=text, lines=lines[-6:], scrolls=n)
                    if not recent:
                        return ('OWNER_ONLY' if any(l[2] for l in lines) else 'NONE_SINCE'), dict(at=text, scrolls=n)
                    pending = False
                elif kind == 'friend':
                    pending = True
                elif kind == 'unknown':
                    rec.setdefault('unparsed', []).append(text)
            # not decided yet: is the whole history visible? (content top-aligned with blank space below)
            if n == 0 and bl and bl[0]['y0'] > CY0 + 2 and bl[-1]['y1'] < CY1 - 40:
                break
            if not bl or short_top:
                break
            # scroll the chat up
            h = row_hashes(arr) if old_h is None else old_h
            s = time.time()
            self.epoch += 1
            self.x.move(g['x'] + 700, g['y'] + 350)
            for i in range(CHAT_SCROLL_NOTCHES):
                self.x.xt.XTestFakeButtonEvent(self.x.d, 4, 1, 0)
                self.x.xt.XTestFakeButtonEvent(self.x.d, 4, 0, 0)
                self.x.x.XSync(self.x.d, 0)
                time.sleep(0.01)
            self.x.move(g['x'] + 700, g['y'] + 16)
            st.add('input', s)
            moved = None
            for attempt in range(2):
                f, _ = self.poll(st, 'chat_scroll', self.chat_stable(g))
                arr = np.asarray(f['im'].crop((g['x'], g['y'], g['x'] + g['w'], g['y'] + g['h']))).astype(np.int16)
                nh = row_hashes(arr)
                moved = scroll_shift(h, nh)
                if moved:              # > 0
                    break
                time.sleep(0.35)       # history may still be loading at the top
            if moved is None:
                return 'UNSURE', dict(reason='scroll registration failed', lines=lines[-6:], scrolls=n)
            rec.setdefault('moved', []).append(moved)
            if moved == 0:
                break                  # top of the local history
            boundary = CY0 + moved
            old_h = nh
            prev_arr = arr
            nb = chat_blocks(arr)
            if moved < SHORT_SCROLL_PX and nb and nb[0]['y0'] > CY0 + 2:
                short_top = True       # the scroll stopped early with the first message fully visible: top

        else:
            return 'UNSURE', dict(reason='too many scrolls', lines=lines[-6:])
        if not seen_any:
            return 'NO_MESSAGES', {}
        if pending:
            return 'UNSURE', dict(reason='friend message above the first timestamp', lines=lines[-6:])
        return ('OWNER_ONLY' if any(l[2] for l in lines) else 'NONE_SINCE'), dict(top=True, lines=lines[-4:])

    def chat_stable(self, g):
        prev = {}

        def cond(f):
            self.main_active(f)
            x, y = g['x'], g['y']
            sig = np.asarray(f['im'].crop((x + CX0, y + CY0, x + CX1, y + CY1)))[::3, ::3]
            same = sig_stable(prev.get('sig'), sig)
            prev['sig'] = sig
            if not same:
                raise Unknown('chat still changing')
            return {}
        return cond

    # -- one Contacts row
    def process(self, row, prev_band, g, f, ledger, ordinal):
        rec = dict(ordinal=ordinal, row_name=row['name'], stages=[], t0=time.time(), row=row)
        self.contacts.append(rec)
        st = Stage('row_select')
        self.act(st, f, row['center'], 'contact-row', g)

        def ready(f):
            im = f['im']
            if not row_selected(im, g, row['band']):
                raise Unknown('target row not selected yet')
            if prev_band and prev_band != row['band'] and row_selected(im, g, prev_band):
                raise Unknown('previous row still selected')
            return {}
        f, _ = self.poll(st, 'profile', ready)
        rec['stages'].append(self.finish_stage(st))
        if any(h in row['name'] for h in SYSTEM_HINTS):
            rec.update(outcome='EXCLUDED_NOT_ORDINARY')
            return self.close_rec(rec, f)

        # ---- row menu -> Messages -> chat
        st = Stage('open_chat')
        try:
            f, p, m = self.open_menu(st, f, row, g)
        except Stop as e:
            raise Unknown('menu: %s' % e)
        rec['menu_starred_item'] = m['starred']
        if m.get('self'):
            rec.update(outcome='EXCLUDED_SELF', reason='row menu has only Messages')
            return self.close_rec(rec, self.close_menu(st))
        # The row menu's star item is state-dependent ('Unstar' = already starred). Reading it here lets an
        # already-starred friend skip the whole chat-history scan (the expensive part) -- ~6 s saved per friend.
        # The profile menu in star() still re-verifies the state before any click, so a misread only costs a skip.
        if canon(m['starred']) == canon('Unstar'):
            rec.update(outcome='ALREADY_STARRED', state_before='starred', reason='row menu reads Unstar')
            return self.close_rec(rec, self.close_menu(st))
        self.menu_click(st, (p[0] + MENU_CLICK['messages'][0], p[1] + MENU_CLICK['messages'][1]), 'menu-messages')
        prev = {}

        def chat_ready(f):
            self.main_active(f)
            t = self.read_title(f['im'], g)
            if not name_match(row['name'], t):
                raise Unknown('chat title %r not yet %r' % (t, row['name']))
            x, y = g['x'], g['y']
            sig = np.asarray(f['im'].crop((x + CX0, y + CY0, x + CX1, y + CY1)))[::3, ::3]
            same = sig_stable(prev.get('sig'), sig)
            prev['sig'] = sig
            if not same:
                raise Unknown('chat still rendering')
            # The header repaints before the message pane: a stale body from the previous chat is also "stable".
            # Require the title to have been right for a short settle time and the body to stay stable across
            # two polls, so the pane cannot be read while it still shows the previously opened chat.
            if 't_title' not in prev:
                prev['t_title'] = time.time()
                raise Unknown('chat just switched')
            if time.time() - prev['t_title'] < 0.6:
                raise Unknown('chat still settling')
            if not sig_stable(prev.get('sig2'), sig):
                prev['sig2'] = sig
                raise Unknown('chat body still settling')
            return t
        try:
            f, title = self.poll(st, 'chat_open', chat_ready)
        except Stop as e:
            rec['stages'].append(self.finish_stage(st))
            rec.update(outcome='SKIPPED_PRE_SEND', reason='chat: %s' % str(e)[:200])
            return self.close_rec(rec, self.recover(g))
        rec['title'] = title
        rec['_chat_arr'] = np.asarray(f['im'].crop((g['x'], g['y'], g['x'] + g['w'], g['y'] + g['h']))).astype(np.int16)
        rec['stages'].append(self.finish_stage(st, title=title))

        st = Stage('scan_chat')
        decision, ev = self.scan_chat(st, g, rec)
        if decision == 'NO_MESSAGES':
            # an empty chat may still be loading: one more look after a short wait
            time.sleep(0.5)
            f2 = self.look(st)
            rec['_chat_arr'] = np.asarray(f2['im'].crop((g['x'], g['y'], g['x'] + g['w'], g['y'] + g['h']))).astype(np.int16)
            decision, ev = self.scan_chat(st, g, rec)
        rec.pop('_chat_arr', None)
        rec.update(decision=decision, evidence=ev)
        if decision in ('STAR', 'UNSURE', 'NO_MESSAGES'):
            self.dbg('chat_%s_%04d' % (decision.lower(), ordinal), self.look(st)['im'], g)
        rec['stages'].append(self.finish_stage(st, decision=decision))

        f = self.back_to_list(rec, g, self.look(Stage('look')))
        if decision != 'STAR':
            rec['outcome'] = decision
            return self.close_rec(rec, f)
        return self.close_rec(rec, self.star(rec, row, g, f, ledger))

    def star(self, rec, row, g, f, ledger):
        # the row must still be where we left it (selected) before touching its menu
        st = Stage('star')
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
        except Stop as e:
            rec['stages'].append(self.finish_stage(st))
            rec.update(outcome='SKIPPED_PRE_SEND', reason='star: %s' % str(e)[:200])
            return self.look(st)
        p = None
        for attempt in range(2):
            s = time.time()
            try:
                p = perceive_profile_fast(f['im'], g, row['band'])
                break
            except Unknown as e:
                p_err = str(e)
            finally:
                st.add('ocr', s); st.n['ocr_calls'] += 1; self.ocr_calls += 1
            time.sleep(0.25); f = self.look(st)
        if p is None:
            rec['stages'].append(self.finish_stage(st))
            rec.update(outcome='SKIPPED_PRE_SEND', reason='profile: %s' % p_err[:200])
            return f
        rec.update(name=p['name'], weixin_id=p['weixin_id'])
        if fold_wxid(p['weixin_id']) == fold_wxid(ACCOUNT):
            rec['stages'].append(self.finish_stage(st))
            rec.update(outcome='EXCLUDED_SELF')
            return f
        if not (p['selected'] and (not canon(p['name']) or not canon(row['name']) or name_match(row['name'], p['name'])
                                   or name_match(p['name'], rec.get('title', '')))):
            rec['stages'].append(self.finish_stage(st))
            rec.update(outcome='SKIPPED_PRE_SEND', reason='row/profile association %r vs %r' % (row['name'], p['name']))
            return f
        op_key = '%s|%s|wxid:%s' % (bv.REQUEST_ID, ACCOUNT, p['weixin_id'])
        # the row menu's 'Starred' item is a toggle with a fixed label: read the real state from the profile menu
        f, state = self.star_state(st, f, g)
        rec['state_before'] = state
        if state == 'starred':
            rec['stages'].append(self.finish_stage(st))
            rec['outcome'] = 'ALREADY_STARRED'
            return f
        if state != 'not_starred':
            rec['stages'].append(self.finish_stage(st))
            rec.update(outcome='SKIPPED_PRE_SEND', reason='star state unreadable: %r' % state)
            return f
        if not self.send:
            rec['stages'].append(self.finish_stage(st))
            rec['outcome'] = 'DRY_RUN_WOULD_STAR'
            return f
        f, pt, m = self.open_menu(st, f, row, g)
        if canon(m['starred']) != canon('Starred'):
            f = self.close_menu(st)
            rec['stages'].append(self.finish_stage(st, menu=m['starred']))
            rec.update(outcome='SKIPPED_PRE_SEND', reason='row menu item %r' % m['starred'])
            return f
        ledger.put(op_key, 'STAR_CLICKING', intent=dict(row=row['name'], name=p['name'], weixin_id=p['weixin_id'],
                                                        title=rec.get('title'), evidence=rec.get('evidence'), run=self.run_id))
        cpt = (pt[0] + MENU_CLICK['starred'][0], pt[1] + MENU_CLICK['starred'][1])
        self.menu_click(st, cpt, 'menu-starred')
        f = self.wait_menu_closed(st, self.menu_probes)
        f, after = self.star_state(st, f, g)
        rec['state_after'] = after
        if after == 'starred':
            ledger.put(op_key, 'STARRED', result=dict(at=time.time()))
            self.starred += 1
            rec['outcome'] = 'STARRED'
        else:
            ledger.put(op_key, 'STAR_UNVERIFIED', result=dict(at=time.time(), state=after))
            rec['outcome'] = 'STAR_UNVERIFIED'
        rec['stages'].append(self.finish_stage(st))
        return f

    def menu_click(self, st, pt, label):
        """Hover first: the Qt popup menus ignore a press that arrives with the pointer motion."""
        self.epoch += 1
        self.j.event(kind='input', stage=st.name, label=label, point=pt, epoch=self.epoch)
        s = time.time()
        self.x.move(pt[0] - 12, pt[1] - 3)
        time.sleep(0.12)
        self.x.move(*pt)
        time.sleep(0.15)
        need(self.x.xt.XTestFakeButtonEvent(self.x.d, 1, 1, 0), 'press failed')
        self.x.x.XSync(self.x.d, 0)
        time.sleep(0.06)
        need(self.x.xt.XTestFakeButtonEvent(self.x.d, 1, 0, 0), 'release failed')
        self.x.x.XSync(self.x.d, 0)
        st.add('input', s)

    def star_state(self, st, f, g):
        """Open the profile's '...' menu, read its Star / Unstar item, close it (Escape). Read-only."""
        self.act(st, f, abspt(g, W_PROFILE_MORE), 'profile-more', g)

        def shown(f):
            texts = self.ocr_box(st, f['im'], absbox(g, W_PROFILE_MENU))
            c = [canon(t[0]) for t in texts]
            if canon('EditContact') not in c:
                raise Unknown('profile menu not shown: %r' % [t[0] for t in texts])
            return 'starred' if 'unstar' in c else 'not_starred' if 'star' in c else repr([t[0] for t in texts])
        try:
            f, state = self.poll(st, 'menu', shown)
        except Stop as e:
            state = 'unknown: %s' % e
        f = self.close_menu(st, [abspt(g, q) for q in ((1000, 180), (1000, 255), (1050, 340))])
        return f, state

    def finish_batch(self, T0, seen, tail):
        for c in self.contacts:               # a row interrupted by a stop has no outcome yet
            c.setdefault('outcome', 'INTERRUPTED')
            c.setdefault('cycle_ms', None)
            c.pop('row', None); c.pop('_chat_arr', None); c.pop('t0', None)
        out = super().finish_batch(T0, seen, tail)
        print('STARRED this run:', self.starred)
        return out


if __name__ == '__main__':
    star = '--star' in sys.argv
    need(star or '--dry-run' in sys.argv, 'specify --star or --dry-run')
    max_rows = int(sys.argv[sys.argv.index('--max-rows') + 1]) if '--max-rows' in sys.argv else None
    eng = StarEngine(star, max_rows)
    if '--resume-from' in sys.argv:
        eng.resume_name = sys.argv[sys.argv.index('--resume-from') + 1]
        eng.from_current = True
        eng.g = wxio.observe()['main']['geom']
        eng.keep_position = eng.on_contacts_tab()     # already on Contacts: skip the tab click, keep the scroll
        print('resume-from %r keep_position=%s' % (eng.resume_name, eng.keep_position), flush=True)
    if '--from-current' in sys.argv:
        eng.from_current = True
        eng.ordinal_base = int(sys.argv[sys.argv.index('--ordinal-base') + 1]) if '--ordinal-base' in sys.argv else 0
    import json
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
