"""send_groups: push the current first native favorite into every chat GROUP with >=20 members,
except groups whose name contains 科大 or 65周年 (user instruction 2026-10-31).

Source of truth for the group list: the Chats list (conversations) -- this WeChat build has no
"Group Chats" section under Contacts, so every conversation row is opened once and the chat header
is read. The header of a group chat is `group name(N)` where N is the member count; 1:1 chats carry
no count. A candidate with N >= 20 is additionally confirmed to be a group by opening the chat's
"..." info panel and requiring its group-only fields ("Group Name" / "My Alias in Group").

Service / Official Accounts rows (and their containers) are ignored, as instructed; "Minimized
Groups" is entered and enumerated too (folded groups are still groups). Chats of deleted contacts
("You've deleted ..." preview) are skipped without opening.

Per qualifying group: chat -> cube (favorites) -> panel zero-select baseline -> select first ->
panel header must read "Send favorites to <group name>" -> campaign first-favorite title check ->
durable intent (do-not-send guard) -> exactly one Send click -> panel exit.

DRY RUN BY DEFAULT (--no-send): the panel is opened, checked and Cancelled.
Ledger: WX_LEDGER (ledger_ocr_mvp_v1.sqlite3), key '<REQUEST_ID>|<ACCOUNT>|group:<name>'.

Usage: python3 -I send_groups.py --send | --no-send [--max-groups N] [--max-rows N]
Env: as batch_v2 (WX_LEDGER, WX_ACCOUNT, WX_SITE, WX_REQUEST_ID=auto); WX_STAR_LEDGER unused.
"""
import difflib
import unicodedata
import ctypes as C
import fcntl
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import batch_v2 as bv  # noqa: E402
import ocr_mvp_v1 as v1  # noqa: E402
from batch_v2 import BatchEngine, Stage, Unknown, Stop, need, absbox, abspt, canon, wxio, wxfast  # noqa: E402
from fast_v2 import chat_visual, panel_visual, read_header_fast  # noqa: E402
from ocr_mvp_v1 import (PANEL_SIZE, W_ACTIVATE, W_AVATAR, P_HEADER, P_SEND, P_SEND_CLICK)  # noqa: E402
import do_not_send  # noqa: E402
import numpy as np  # noqa: E402

MODE = 'send_groups'
bv.WAITS['chat'] = (0.15, 3.0)      # the chat header paints fast; keep the per-row cost low
bv.WAITS['info'] = (0.40, 6.0)      # inline info panel: OCR of the panel is slow, give it room
bv.WAITS['search'] = (0.50, 8.0)    # Chats search: results (and the 'Group Chats' section) take a moment
bv.WAITS['minimized'] = (0.40, 5.0) # opening the Minimized Groups container
W_CHATS_TAB = (31, 113)              # sidebar Chats icon (main window relative)
CHAT_MORE = (1057, 56)               # chat header '...' -> inline info panel (toggle)
SEARCH_BOX = (170, 57)               # Chats tab search box
SEARCH_CLEAR = (275, 57)             # its clear (x) button
SENT_FILE = os.path.join(HERE, 'sent_groups.json')   # local (git-ignored): groups already sent per campaign
ROSTER_FILE = os.path.join(HERE, 'groups_roster.json')  # local (git-ignored): known 20+ member groups
LIST = (61, 81, 240, 689)            # chat list area (window relative), as chatlist_scan
MIN_MEMBERS = 20
EXCLUDE_SUBSTR = ('科大', '65周年')
# conversation containers / system chats that are not group chats and are never opened
CONTAINERS = ('officialaccounts', 'serviceaccounts', 'minimizedgroups', 'weixinteam')
DELETED_PREVIEW = re.compile(r"you.?ve\s*deleted", re.I)
INFO_PANEL = (860, 80, 228, 690)     # window-relative region of the inline info panel


def load_json_list(path):
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def save_json_list(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def plain(s):
    """lowercase letters/digits/CJK only -- NO confusable folding (canon() turns o->0, i->1, so it must not
    be used against literal UI labels such as 'Group Chats' or 'Minimized Groups')."""
    return ''.join(ch for ch in (s or '').lower() if unicodedata.category(ch)[0] in 'LN')


def is_minimized(name):
    c = plain(name)
    return 'minimized' in c and len(c) <= 22


def is_container(name):
    """container rows (Service/Official Accounts, Minimized Groups, Weixin Team) incl. OCR slips -- never opened."""
    c = plain(name)
    for k in CONTAINERS:
        if c == k:
            return True
        if c and len(c) <= len(k) + 2 and difflib.SequenceMatcher(None, c, k).ratio() >= 0.82:
            return True
    return False

_DIG = str.maketrans({'O': '0', 'o': '0', '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
                      '５': '5', '６': '6', '７': '7', '８': '8', '９': '9', 'l': '1', 'I': '1', '|': '1'})
COUNT_RE = re.compile(r'[（(]\s*([0-9Oo０-９lI|]{1,5})\s*[）)]')


def members_of(title):
    """-> (member_count or None, name_without_count). The count is the trailing `(N)` of a group header."""
    t = (title or '').strip()
    for m in COUNT_RE.finditer(t):
        if len(t) - m.end() <= 3:                 # trailing `(N)` (allow 1-3 OCR junk chars after it)
            n = m.group(1).translate(_DIG)
            if n.isdigit() and 0 < int(n) <= 5000:
                return int(n), (t[:m.start()] + t[m.end():]).strip()
    return None, t


def name_has(blob, needle):
    return needle in re.sub(r'\s+', '', blob or '')


def row_name_match(row_name, title):
    """the chat header must be the row we clicked. List names are truncated ('...') and can carry trailing
    icon noise, so a prefix match (with at most one OCR slip inside that prefix) is accepted -- but two
    different groups whose names differ early (037... vs 016...) must never match."""
    a, b = canon(row_name), canon(title)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    if b.startswith(a):
        return True
    k = min(len(a), len(b))
    return k >= 6 and sum(x != y for x, y in zip(a[:k], b[:k])) <= 1


TIME_TAIL = re.compile(r'\s*(?:[0-9OolI|]{1,2}[:：.．][0-9OolI|]{1,2}'
                        r'|(?:Yesterday|Today|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\s*$', re.I)


def parse_rows(texts, g, y_min=85):
    """Chat-list rows of one page -> [{name, time, preview, y, key}].

    A row is normally anchored on its time stamp (same line as the name, x >= 190). Two cases need care:
      * an emoji at the start of the name can make the OCR detector merge name+time into ONE box
        ('<name>..02:42') -- split the trailing time off and keep the row;
      * the time may not be read at all -- a name-column line with a preview line right below is a row.
    Boxes that share a line inside the name column (e.g. emoji read separately) are joined by x.
    """
    rel = [(t[0].strip(), t[2][0] - g['x'], t[2][1] - g['y'], t[2][2]) for t in texts]
    times = [r for r in rel if r[1] >= 190]
    rows, seen_y = [], []

    def add(name, y, tm=None):
        name = (name or '').strip()
        if not name or any(abs(y - v) <= 12 for v in seen_y):
            return
        tm = tm if tm is not None else ' '.join(sorted({r[0] for r in times if abs(r[2] - y) <= 9}))
        pv = [r for r in rel if 100 <= r[1] < 200 and 11 <= r[2] - y <= 34]
        prev = ' '.join(r[0] for r in sorted(pv, key=lambda r: (r[2], r[1])))
        seen_y.append(y)
        rows.append(dict(name=name, time=tm, preview=prev, y=y,
                         key='%s|%s' % (canon(name), canon(prev)[:24])))

    # name-column boxes grouped into text lines
    lines = []
    for name, x, y, w in sorted(rel, key=lambda r: (r[2], r[1])):
        if not (112 <= x <= 175) or y < y_min or y > LIST[1] + LIST[3] - 22:
            continue
        if lines and abs(lines[-1][0] - y) <= 9:
            lines[-1][1].append((x, name, w))
        else:
            lines.append([y, [(x, name, w)]])
    for y, parts in lines:
        parts.sort()
        name = ''.join(p[1] for p in parts)
        x0, w_end = parts[0][0], parts[-1][0] + parts[-1][2]
        if any(abs(t[2] - y) <= 9 for t in times):
            add(name, y)
            continue
        m = TIME_TAIL.search(name)
        if m and m.start() > 0 and w_end > 200:            # name+time merged into one OCR box
            add(name[:m.start()], y, tm=m.group(0).strip())
            continue
        if any(100 <= r[1] < 200 and 11 <= r[2] - y <= 34 for r in rel):
            add(name, y)                                    # time unreadable, but it is a chat row
    for name, x, y, w in rel:                               # container row without a time stamp
        if plain(name) == 'minimizedgroups' and 80 <= y <= 115:
            add(name, y)
    return sorted(rows, key=lambda r: r['y'])


class GroupSendEngine(BatchEngine):
    def __init__(self, send, max_groups=None, max_rows=None):
        super().__init__(send, None, max_rows)
        old = self.dir
        self.run_id = time.strftime('groups_%Y%m%dT%H%M%S') + ('_send' if send else '_dry')
        self.dir = wxio.OUT / self.run_id
        old.rename(self.dir)
        self.j.f.close()
        self.j = wxfast.Journal(self.dir / 'events.jsonl')
        self.sink.dir = self.dir
        self.max_groups = max_groups
        self.groups = []            # report rows: every conversation classified
        self.sent_groups = 0        # real Send clicks
        self.qualifying = 0         # groups that reached the send step (dry run included)
        self.done_names = set()     # canonical row names already opened (guards against re-opened rows)
        self.attempts = {}          # row key -> failed attempts (list moved under us / header mismatch)
        self.done_titles = set()    # canonical chat titles already classified in this run
        self.sent_log = load_json_list(SENT_FILE)   # [{name, members, request, at}]
        self.sent_names = {}        # canon(name) -> entry, for the CURRENT campaign
        self.roster = {canon(e['name']): e.get('members') for e in load_json_list(ROSTER_FILE)
                       if e.get('name') and e.get('members')}   # known groups -> member count
        self.known_at_start = set(self.roster)
        self.new_groups = []        # groups sent in this run that were not in the roster before
        xx = self.x.x
        xx.XRaiseWindow.argtypes = [C.c_void_p, C.c_ulong]
        xx.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
        xx.XFlush.argtypes = [C.c_void_p]
        self.rep = open(os.path.join(str(self.dir), 'groups.jsonl'), 'a')

    # ---------------------------------------------------------------- perception
    def list_sig(self, im, g):
        x, y, w, h = absbox(g, LIST)
        return np.asarray(im.crop((x, y, x + w, y + h))).astype(np.int16)

    def scan(self, st, f, g, sub=False):
        texts = self.ocr_box(st, f['im'], absbox(g, LIST))
        rows = parse_rows(texts, g, y_min=120 if sub else 85)
        self.j.event(kind='page', sub=sub, rows=[r['name'] for r in rows])
        return rows

    def title_of(self, st, im, g):
        """chat header text; a group header ends with `(N)`, so retry with a full OCR when the count is
        missing (a rec-only read sometimes drops the trailing `(500)`)."""
        t = self.read_title(im, g)
        if not canon(t) or members_of(t)[0] is None:
            st.n['fallbacks'] += 1
            texts = self.ocr_box(st, im, absbox(g, (301, 33, 640, 48)))
            t2 = ' '.join(x[0] for x in sorted(texts, key=lambda r: r[2][0])).strip()
            if not canon(t) or members_of(t2)[0] is not None:
                t = t2
        return t.strip()

    def info_panel(self, st, f, g):
        """OCR the inline info panel; -> dict(texts, group, not_group, name)."""
        texts = self.ocr_box(st, f['im'], [g['x'] + INFO_PANEL[0], g['y'] + INFO_PANEL[1],
                                           INFO_PANEL[2], INFO_PANEL[3]])
        flat = [re.sub(r'\s+', '', t[0]).lower() for t in texts]
        group = any(x in ('groupname', 'myaliasingroup', 'groupqrcode') for x in flat)
        not_group = any(x in ('moments', 'addtocontacts', 'region:', 'sendmessage', 'charset') or
                        x.startswith('region') for x in flat)
        nm = ''
        for i, x in enumerate(flat):
            if x == 'groupname' and i + 1 < len(texts):
                nm = texts[i + 1][0].strip()
                break
        return dict(texts=[t[0] for t in texts], group=group, not_group=not_group, name=nm)

    def panel_open(self, f):
        o = f['owner']
        return [w for w in o['wechat'] if w['id'] != o['main']['id']]

    def info_open(self, st, f, g):
        """is the inline chat info panel open? (group-only fields in the right-hand panel)"""
        v = self.info_panel(st, f, g)
        return v['group']

    # ---------------------------------------------------------------- focus / input robustness
    def x_activate(self, wid):
        """raise + focus a window of ours without any mouse click (screen-position independent)."""
        x = self.x.x
        x.XRaiseWindow(self.x.d, wid)
        x.XSetInputFocus(self.x.d, wid, 2, 0)      # RevertToParent, CurrentTime
        x.XFlush(self.x.d)

    def main_active(self, f):
        """main window alone and focused. A WeChat notification window (WeChatAppEx process) can steal the
        focus at any time: take it back instead of stopping."""
        o = f['owner']
        if len(o['wechat']) != 1:
            raise Unknown('WeChat transient present')
        if o['active'] != o['main']['id']:
            self.x_activate(o['main']['id'])
            raise Unknown('main window not focused yet (re-activated)')
        return {}

    def ensure_active(self, wid, tries=6):
        """a WeChat notification popup or another app can steal focus; take it back."""
        for i in range(tries):
            o = self.q.observe(self.pid)
            if o['active'] == wid:
                return o
            self.x_activate(wid)
            time.sleep(0.35)
        return self.q.observe(self.pid)

    def act(self, st, f, point, label, owner_win):
        o = self.q.observe(self.pid)
        if o['active'] != f['owner']['active'] or o['main']['geom'] != f['owner']['main']['geom']:
            st.n['fallbacks'] += 1
            self.ensure_active(f['owner']['active'])
            f = self.look(st)
        return super().act(st, f, point, label, owner_win)

    def scroll(self, st, f, g, button, notches):
        for attempt in range(3):
            try:
                return super().scroll(st, f, g, button, notches)
            except Stop:
                if attempt == 2:
                    raise
                st.n['fallbacks'] += 1
                self.ensure_active(self.q.observe(self.pid)['main']['id'])
                f = self.look(st)

    # ---------------------------------------------------------------- campaign (first favorite)
    def campaign(self, g, f, ledger):
        """Favorites tab -> the newest favorite's title -> REQUEST_ID (batch_v2's rule, with a tolerant read:
        the first card's title and its snippet line both sit in the calibrated band, so take the TOP line)."""
        st = Stage('campaign')
        self.act(st, f, abspt(g, bv.W_FAV_TAB), 'favorites-tab', g)

        def all_fav(f):
            self.main_active(f)
            if not bv.close(f['im'].getpixel(abspt(g, bv.W_FAV_ALL_PX)), bv.GREEN_ROW, 12):
                raise Unknown('All Favorites not selected')
            return {}
        f, _ = self.poll(st, 'contacts', all_fav)
        title, texts = None, []
        for attempt in range(3):
            texts = self.ocr_box(st, f['im'], absbox(g, bv.W_FAV_VIEW))
            flat = lambda t: re.sub(r'\s+', '', t[0])
            rel = lambda t: (t[2][0] - g['x'], t[2][1] - g['y'])
            search = any(flat(t) == 'SearchFavorites' for t in texts)
            header = any(flat(t) == 'AllFavorites' and rel(t)[0] > 301 for t in texts)
            band = [t for t in texts if 340 <= rel(t)[0] <= 430 and 95 <= rel(t)[1] <= 128]
            if search and header and band:
                y0 = min(rel(t)[1] + t[2][3] / 2 for t in band)
                line = sorted([t for t in band if abs(rel(t)[1] + t[2][3] / 2 - y0) <= 8], key=lambda t: rel(t)[0])
                title = ''.join(t[0].strip() for t in line).strip()
                if canon(title):
                    break
            st.n['fallbacks'] += 1
            time.sleep(0.3); f = self.look(st)
        need(title and canon(title), 'favorites view not at default/top: %r' % [t[0] for t in texts])
        self.fav_title = title
        rid, new = bv.resolve_campaign(ledger, title, create=self.send)
        self.j.event(kind='campaign', title=title, request=rid, new=new)
        bv.REQUEST_ID = rid
        v1.REQUEST_ID = rid
        self.finish_stage(st, title=title, request=rid, new=new)
        return f

    # ---------------------------------------------------------------- navigation
    def recover(self, g):
        """Pre-send cleanup: cancel any favorites panel, back to the chat list. An inline info panel does
        not block the list and is replaced as soon as another conversation is opened."""
        st = Stage('recover')
        o = self.q.observe(self.pid)
        pans = [w for w in o['wechat'] if w['id'] != o['main']['id']
                and (w['geom']['w'], w['geom']['h']) == PANEL_SIZE]
        if pans:
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
        self.act(st, f, abspt(g, W_CHATS_TAB), 'chats-tab', g)
        f, _ = self.poll(st, 'contacts', self.main_active)
        self.finish_stage(st)
        return f

    def scroll_to_top(self, st, f, g):
        for attempt in range(120):
            before = self.list_sig(f['im'], g)
            self.scroll(st, f, g, 4, 100)
            f, _ = self.poll(st, 'scroll', self.list_stable(g))
            if np.abs(self.list_sig(f['im'], g) - before).max() == 0:
                return f
        raise Stop('could not reach the top of the chat list')

    def sublist_header(self, st, f, g):
        """-> (x, y) of a container header (e.g. 'Minimized Groups') when a sub-list is open, else None."""
        for t in self.ocr_box(st, f['im'], absbox(g, LIST)):
            x, y = t[2][0] - g['x'], t[2][1] - g['y']
            c = plain(t[0])
            if 70 <= x <= 112 and 80 <= y <= 115 and any(c == k or c.startswith(k) for k in CONTAINERS):
                return x, y
        return None

    def leave_sublist(self, st, f, g):
        """If a container sub-list (Minimized Groups / Service Accounts ...) is open, click its back arrow."""
        hdr = self.sublist_header(st, f, g)
        if not hdr:
            return f

        def back(f):
            if self.sublist_header(st, f, g):
                raise Unknown('still inside a sub-list')
            return {}
        for attempt in range(2):
            self.j.event(kind='leave_sublist', at=hdr, attempt=attempt)
            self.act(st, f, (g['x'] + hdr[0] - 14 - 8 * attempt, g['y'] + hdr[1] + 3), 'sublist-back', g)
            try:
                f, _ = self.poll(st, 'contacts', back)
                return f
            except Stop:
                if attempt == 1:
                    raise
                f = self.look(st)
                hdr = self.sublist_header(st, f, g) or hdr
        return f

    # ---------------------------------------------------------------- one conversation
    def load_sent(self):
        """(re)load the local record of groups already sent for the current campaign."""
        self.sent_log = load_json_list(SENT_FILE)
        rid = bv.REQUEST_ID
        self.sent_names = {canon(e['name']): e for e in self.sent_log if e.get('request') == rid}

    def sent_hit(self, row_name):
        """a list row name (truncated) that unambiguously identifies a group already sent in this campaign."""
        c = canon(row_name)
        if len(c) < 4:
            return None
        hits = {k: e for k, e in self.sent_names.items() if k == c or k.startswith(c)}
        return next(iter(hits.values())) if len(hits) == 1 else None

    def record_sent(self, name, members):
        rid = bv.REQUEST_ID
        self.sent_log = [e for e in self.sent_log
                         if not (e.get('request') == rid and canon(e['name']) == canon(name))]
        entry = dict(name=name, members=members, request=rid, at=time.time())
        if canon(name) not in self.known_at_start:
            self.new_groups.append(dict(name=name, members=members))
        self.sent_log.append(entry)
        save_json_list(SENT_FILE, self.sent_log)
        self.sent_names[canon(name)] = entry

    def row_still(self, st, im, g, row):
        """rec-only OCR of the cached name line: is this row still where the last scan put it?"""
        lab = self.rec_label(st, im, [g['x'] + 112, g['y'] + row['y'] - 4, 190, 22])
        a, b = canon(lab), canon(row['name'])
        if not a or not b:
            return False
        if a in b or b in a:
            return True
        return difflib.SequenceMatcher(None, a, b[:len(a)]).ratio() >= 0.6

    def process(self, row, g, f, ledger):
        """Open the row's chat and hand its header to classify_and_send()."""
        rec = dict(row_name=row['name'], row_key=row['key'], stages=[], t0=time.time())
        st = Stage('open_chat')
        t_before = self.title_of(st, f['im'], g)       # header before the click (stale-read guard)
        self.act(st, f, (g['x'] + 170, g['y'] + row['y'] + 6), 'chat-row', g)
        t_click = time.time()

        def ready(f):
            t = self.title_of(st, f['im'], g)
            if not canon(t):
                raise Unknown('chat header not read yet')
            if canon(t) == canon(t_before) and not row_name_match(rec['row_name'], t) \
                    and time.time() - t_click < 3.0:
                raise Unknown('chat header unchanged since before the click: %r' % t)
            if not row_name_match(rec['row_name'], t) and time.time() - t_click < 1.5:
                raise Unknown('chat header still the previous one: %r' % t)
            return t
        try:
            f, title = self.poll(st, 'chat', ready)
        except Stop as e:
            rec.update(outcome='CHAT_NOT_OPENED', retryable=True, reason=str(e)[:160])
            return self.close_row(rec, f), rec
        rec['stages'].append(self.finish_stage(st))
        return self.classify_and_send(rec, title, g, f, ledger)

    def classify_and_send(self, rec, title, g, f, ledger, assumed_members=None):
        """Classify the chat that is open (its header is `title`) and send the first favorite when it is a
        group with >=20 members whose name is not excluded. `assumed_members` (roster mode) fills in the
        member count when the header OCR drops the trailing `(N)`."""
        rec['title'] = title
        if is_container(title):
            # the list re-sorted and the click landed on a container row: its sub-list is now open
            rec.update(outcome='CONTAINER_OPENED', retryable=True)
            st2 = Stage('leave_container')
            f = self.leave_sublist(st2, f, g)
            self.finish_stage(st2)
            return self.close_row(rec, f), rec
        n, base = members_of(title)
        if n is None:
            m = assumed_members or self.roster.get(canon(base))
            if m:
                n = int(m)                    # count from the roster (verified on an earlier run)
                rec['members_source'] = 'roster'
        if canon(base) in self.done_titles:
            rec.update(outcome='ALREADY_VISITED')
            return self.close_row(rec, f), rec
        self.done_titles.add(canon(base))
        rec['_title_key'] = canon(base)
        if not row_name_match(rec['row_name'], title):
            # the list re-sorted between the scan and the click; the opened chat is still a real
            # conversation, so classify it by its own header (never by the row we aimed at)
            rec['row_mismatch'] = True
        rec.update(members=n, group_name=base)
        if name_has(base, EXCLUDE_SUBSTR[0]) or name_has(base, EXCLUDE_SUBSTR[1]) or \
                name_has(title, EXCLUDE_SUBSTR[0]) or name_has(title, EXCLUDE_SUBSTR[1]):
            rec.update(outcome='EXCLUDED_NAME', reason='name contains 科大 / 65周年')
            return self.close_row(rec, f), rec
        why = do_not_send.blocked(None, title, rec['row_name'])
        if why:
            rec.update(outcome='EXCLUDED_DO_NOT_SEND', reason=why)
            return self.close_row(rec, f), rec
        if n is None:
            # 1:1 chats and service chats carry no member count; a truncated group header loses it
            trunc = title.rstrip().endswith(('...', '…'))
            rec.update(outcome='TITLE_TRUNCATED' if trunc else 'NOT_A_GROUP')
            return self.close_row(rec, f), rec
        if n < MIN_MEMBERS:
            rec.update(outcome='BELOW_THRESHOLD')
            return self.close_row(rec, f), rec

        # a member count is only trusted for candidates: confirm group-ness in the chat's own info panel
        st = Stage('group_check')
        self.act(st, f, abspt(g, CHAT_MORE), 'chat-more', g)

        def info(f):
            if len(self.panel_open(f)) != 0:
                raise Unknown('transient window present')
            v = self.info_panel(st, f, g)
            if not (v['group'] or v['not_group']):
                raise Unknown('info panel not shown yet')
            return v
        try:
            f, iv = self.poll(st, 'info', info)
            rec['stages'].append(self.finish_stage(st, info_name=iv['name'][:60], is_group=iv['group']))
        except Stop as e:
            rec.update(outcome='INFO_PANEL_UNREAD', reason=str(e)[:160])
            return self.close_row(rec, f), rec
        if not iv['group']:
            rec.update(outcome='NOT_A_GROUP', reason='chat info panel has no group fields')
            return self.close_row(rec, f), rec
        rec['info_group_name'] = iv['name'][:80]
        # qualifying group: close the info panel and send
        st = Stage('close_info')
        self.act(st, f, abspt(g, CHAT_MORE), 'chat-more-close', g)
        time.sleep(0.7)
        f = self.look(st)
        try:
            if self.info_open(st, f, g):                 # still open: toggle once more (best effort)
                st.n['fallbacks'] += 1
                self.act(st, f, abspt(g, CHAT_MORE), 'chat-more-close2', g)
                time.sleep(0.7)
                f = self.look(st)
        except Unknown:
            pass
        self.finish_stage(st)
        op_key = '%s|%s|group:%s' % (bv.REQUEST_ID, bv.ACCOUNT, base)
        existing = ledger.state(op_key)
        if existing is not None:
            if existing == 'SEND_CLICKED' and canon(base) not in self.sent_names:
                self.record_sent(base, n)          # keep the local record in step with the ledger
            rec.update(outcome='ALREADY_' + existing)
            return self.close_row(rec, f), rec
        try:
            f = self.send_in_chat(rec, base, op_key, g, f, ledger)
            self.qualifying += 1
        except Unknown as e:
            rec.update(outcome='SKIPPED_PRE_SEND', reason=str(e)[:200])
            f = self.recover(g)
        return self.close_row(rec, f), rec

    def close_row(self, rec, f):
        key = rec.pop('_title_key', None)
        if key and (rec.get('retryable') or rec.get('outcome') in
                    ('SKIPPED_PRE_SEND', 'CONTAINER_OPENED', 'CHAT_NOT_OPENED')):
            self.done_titles.discard(key)      # not really visited: allow a later retry
        rec.pop('stages_tmp', None)
        rec['cycle_ms'] = round((time.time() - rec.pop('t0')) * 1000, 1)
        self.groups.append(rec)
        self.rep.write(json.dumps(rec, ensure_ascii=False) + '\n')
        self.rep.flush()
        self.j.event(kind='conversation', **{k: v for k, v in rec.items() if k != 'stages'})
        self.j.f.flush()
        print('%-26s %-22s %s' % ((rec.get('group_name') or rec['row_name'])[:26],
                                  rec.get('outcome'), rec.get('members') if rec.get('members') is not None else '-'),
              flush=True)
        return f

    # ---------------------------------------------------------------- send in the open chat
    def send_in_chat(self, rec, gname, op_key, g, f, ledger):
        st = Stage('chat_settle')
        time.sleep(0.2)
        f2 = self.look(st)
        t2 = self.title_of(st, f2['im'], g)
        if not (canon(gname) in canon(t2) or canon(t2) in canon(gname)):
            # the pane finished switching late: if it is the row we clicked, send to THAT chat
            n2, base2 = members_of(t2)
            if not row_name_match(rec['row_name'], t2) or not canon(base2):
                raise Unknown('chat changed before opening favorites: %r vs %r' % (t2, gname))
            rec['settle_retarget'] = True
            gname = base2
            if n2 is not None:
                rec['members'] = n2
            rec['group_name'] = base2
            op_key = '%s|%s|group:%s' % (bv.REQUEST_ID, bv.ACCOUNT, base2)
            self.j.event(kind='settle_retarget', group=base2, members=n2)
            if ledger.state(op_key) is not None:
                rec.update(outcome='ALREADY_SEND_CLICKED')
                self.finish_stage(st, retarget=base2)
                return f2
        f = f2
        self.finish_stage(st)

        st = Stage('open_favorites')
        try:
            ch = chat_visual(f['im'], g)
        except Unknown as e:
            raise Unknown('favorites cube not found: %s' % e)
        self.act(st, f, ch['cube'], 'favorites-entry', g)

        def base(f):
            o = f['owner']
            pans = [w for w in o['wechat'] if w['id'] != o['main']['id']]
            if len(pans) != 1 or pans[0]['transient'] != o['main']['id'] or o['active'] != pans[0]['id'] \
                    or (pans[0]['geom']['w'], pans[0]['geom']['h']) != PANEL_SIZE:
                raise Unknown('favorites panel not yet owned/active')
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
            raise Unknown(str(e))
        self.dbg('selected_%04d' % len(self.groups), f['im'], pg)
        rec['stages'].append(self.finish_stage(st))

        st = Stage('recipient_check')
        header = read_header_fast(f['im'], pg)
        st.n['ocr_calls'] += 1; self.ocr_calls += 1

        def ok(h):
            c, pre, n = canon(h), canon('Send favorites to'), canon(gname)
            if not c.startswith(pre) or not n:
                return False
            rest = c[len(pre):]
            if n in rest or rest in n:
                return True
            if len(n) >= 4 and len(rest) >= 4 and difflib.SequenceMatcher(None, n, rest).ratio() >= 0.6:
                rec['header_fuzzy'] = True
                return True
            return False
        if not ok(header):
            st.n['fallbacks'] += 1
            header = ' '.join(t[0] for t in self.ocr_box(st, f['im'], absbox(pg, P_HEADER)))
        rec['stages'].append(self.finish_stage(st, header=header))
        if not ok(header):
            raise Unknown('panel header not bound to the group: %r' % header)
        rec['header'] = header

        if bv.AUTO_RID:
            st = Stage('content_check')
            pt = self.rec_label(st, f['im'], absbox(pg, bv.P_FIRST_TITLE))
            r = bv.title_prefix_ratio(pt, self.fav_title)
            if r < 0.8:
                st.n['fallbacks'] += 1
                pt = ' '.join(t[0] for t in self.ocr_box(st, f['im'], absbox(pg, (255, 85, 380, 36))))
                r = bv.title_prefix_ratio(pt, self.fav_title)
            rec['stages'].append(self.finish_stage(st, title=pt, ratio=round(r, 3)))
            if r < 0.5:
                raise Stop('HALT: first favorite changed during campaign %s: %r vs %r'
                           % (bv.REQUEST_ID, pt, self.fav_title))
            if r < 0.8:
                raise Unknown('panel first favorite title not confirmed: %r' % pt)

        if not self.send:
            st = Stage('cancel_no_send')
            self.act(st, f, abspt(pg, (520, 550)), 'cancel', pg)
            f, _ = self.poll(st, 'exit', self.main_active)
            rec['stages'].append(self.finish_stage(st))
            rec['outcome'] = 'DRY_RUN_PREPARED'
            return f

        st = Stage('dispatch')
        intent = dict(request=bv.REQUEST_ID, account=bv.ACCOUNT, mode=MODE, row=rec['row_name'],
                      profile=gname, group_members=rec.get('members'), panel_id=panel['id'],
                      header=header, run=self.run_id)
        s = time.time(); ledger.put(op_key, 'PREPARED', intent=intent,
                                    recipient_ref=json.dumps(intent, ensure_ascii=False)); st.add('ledger', s)
        need(time.time() - f['at'] < 180 and f['epoch'] == self.epoch, 'frame expired/stale before dispatch')
        s = time.time(); live = wxio.observe(); st.add('window', s)
        if live['active'] != panel['id']:
            self.ensure_active(panel['id'])          # a notification may have stolen the focus
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
        self.sent_groups += 1
        rec['outcome'] = 'SEND_CLICKED'
        self.record_sent(gname, rec.get('members'))
        self.j.event(kind='send_clicked', op_key=op_key, group=gname, members=rec.get('members'))
        rec['stages'].append(self.finish_stage(st))

        st = Stage('panel_exit')
        try:
            f, _ = self.poll(st, 'exit', self.main_active)
            rec['stages'].append(self.finish_stage(st))
        except Stop as e:
            self.j.event(kind='UI_STALLED', reason=str(e))
            rec['stages'].append(self.finish_stage(st, ui_stalled=True))
            raise Stop('UI stalled after send (SEND_CLICKED stands, no re-press): %s' % e)
        return f

    # ---------------------------------------------------------------- enumeration
    def enumerate_list(self, st, f, g, ledger, done, sub=False):
        """Walk one chat list (main list or the Minimized Groups sub-list) top -> bottom.

        The page OCR is cached: each row is re-checked with a cheap rec-only read of its own line
        before it is clicked (the list re-sorts whenever a message arrives), and the page is re-scanned
        only when that check fails or the page is exhausted.
        """
        idle, rows, steps, scrolls = 0, 0, 0, 0
        page, i = None, 0
        while True:
            steps += 1
            need(steps <= 20000, 'chat list does not terminate')
            if page is None:
                if not sub and self.sublist_header(st, f, g):
                    f = self.leave_sublist(st, f, g)
                page, i = self.scan(st, f, g, sub=sub), 0
            if i >= len(page):
                # bottom test: the last two visible rows must stay the same while scrolling down (new
                # messages arriving at the top shift the rest of the list, so pixels are not reliable)
                tail = tuple(canon(r['name']) for r in page[-2:])
                self.scroll(st, f, g, 5, bv.SCROLL_NOTCHES)
                f, _ = self.poll(st, 'scroll', self.list_stable(g))
                page, i = self.scan(st, f, g, sub=sub), 0
                scrolls += 1
                if page and tuple(canon(r['name']) for r in page[-2:]) == tail:
                    idle += 1
                    if idle >= 3:
                        self.finish_stage(st, rows=rows, sub=sub, bottom=True)
                        return f
                else:
                    idle = 0
                if scrolls > 260:
                    self.finish_stage(st, rows=rows, sub=sub, bottom=False, scroll_cap=scrolls)
                    return f
                continue
            row = page[i]
            i += 1
            if row['key'] in done:
                continue
            if is_minimized(row['name']):
                done.add(row['key'])
                if not sub:
                    f = self.enter_minimized(st, f, g, ledger, done)
                    page = None
                continue
            if self.skip_row(row):
                done.add(row['key'])
                self.j.event(kind='skip_row', name=row['name'], preview=row['preview'][:40])
                continue
            if canon(row['name']) in self.done_names:
                done.add(row['key'])
                self.j.event(kind='duplicate_name', name=row['name'])
                continue
            if self.max_rows is not None and len(self.groups) >= self.max_rows:
                self.finish_stage(st, rows=rows, sub=sub, stopped='max_rows')
                return f
            hit = self.sent_hit(row['name'])
            if hit:
                done.add(row['key'])
                self.done_names.add(canon(row['name']))
                self.j.event(kind='already_sent_fast', name=row['name'], hit=hit['name'])
                continue
            if self.attempts.get(row['key'], 0) >= 4:
                done.add(row['key'])
                self.j.event(kind='give_up', name=row['name'])
                continue
            # the list re-sorts when a message arrives: re-read this row's line before clicking it
            if not self.row_still(st, f['im'], g, row):
                self.attempts[row['key']] = self.attempts.get(row['key'], 0) + 1
                self.j.event(kind='row_moved', name=row['name'])
                page = None
                f = self.look(st)
                continue
            rows += 1
            f, rec = self.process(row, g, f, ledger)
            if rec.get('retryable') or rec.get('row_mismatch'):
                self.attempts[row['key']] = self.attempts.get(row['key'], 0) + 1
                page = None
            else:
                done.add(row['key'])
                self.done_names.add(canon(row['name']))
            if self.max_groups is not None and self.qualifying >= self.max_groups:
                self.finish_stage(st, rows=rows, sub=sub, stopped='max_groups=%d' % self.max_groups)
                return f
            f = self.look(st)

    def skip_row(self, row):
        if is_container(row['name']):
            return True
        if DELETED_PREVIEW.search(row['preview'] or ''):
            return True
        return False

    def enter_minimized(self, st, f, g, ledger, done):
        """Open the 'Minimized Groups' container, enumerate the folded groups, then go back."""
        f = self.leave_sublist(st, f, g)               # defensive: never nest two sub-lists
        row = next((r for r in parse_rows(self.ocr_box(st, f['im'], absbox(g, LIST)), g)
                    if is_minimized(r['name'])), None)
        if row is None:
            self.j.event(kind='minimized_row_missing')
            return f
        self.act(st, f, (g['x'] + 170, g['y'] + row['y'] + 6), 'minimized-groups', g)
        def opened(f):
            t = self.ocr_box(st, f['im'], absbox(g, LIST))
            hit = [x for x in t if plain(x[0]) == 'minimizedgroups' and x[2][1] - g['y'] < 120]
            if not hit:
                raise Unknown('minimized groups list not shown')
            return hit[0][2]
        try:
            f, tb = self.poll(st, 'minimized', opened)
        except Stop:
            # the click may have landed elsewhere (list re-sorted): skip the container, keep going
            self.j.event(kind='minimized_not_opened')
            return self.look(st)
        self.j.event(kind='enter_minimized')
        f = self.enumerate_list(st, f, g, ledger, done, sub=True)
        # back arrow sits just left of the sub-list title
        try:
            f = self.leave_sublist(st, f, g)
        except Stop:
            self.j.event(kind='minimized_stuck')
        self.j.event(kind='exit_minimized')
        return f

    # ---------------------------------------------------------------- search by name (targeted / roster)
    def set_clipboard(self, text):
        """GTK clipboard; the GLib loop must run while another app asks for the selection."""
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, Gdk
        self._clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._clip.set_text(text, -1)

    def key(self, name, mods=()):
        x = self.x
        codes = [x.x.XKeysymToKeycode(x.d, x.x.XStringToKeysym(m.encode())) for m in mods]
        need(all(codes), 'no keycode for %r' % (mods,))
        for c in codes:
            x.xt.XTestFakeKeyEvent(x.d, c, 1, 0)
        kc = x.x.XKeysymToKeycode(x.d, x.x.XStringToKeysym(name.encode()))
        need(kc, 'no keycode for %r' % name)
        x.xt.XTestFakeKeyEvent(x.d, kc, 1, 0)
        x.xt.XTestFakeKeyEvent(x.d, kc, 0, 0)
        for c in reversed(codes):
            x.xt.XTestFakeKeyEvent(x.d, c, 0, 0)
        x.x.XSync(x.d, 0)
        time.sleep(0.04)

    def paste(self, text):
        """type `text` into the focused field: ASCII by keycode, anything else by clipboard paste."""
        if text and all(ch.isascii() and (ch.isalnum() or ch in '.-_@ ') for ch in text):
            for ch in text:
                if ch == ' ':
                    self.key('space')
                elif ch == '.':
                    self.key('period')
                elif ch == '-':
                    self.key('minus')
                elif ch == '_':
                    self.key('underscore', ('Shift_L',))
                elif ch == '@':
                    self.key('at', ('Shift_L',))
                elif ch.isdigit():
                    self.key(ch)
                else:
                    self.key(ch.lower(), ('Shift_L',) if ch.isupper() else ())
            return
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import GLib
        import threading
        self.set_clipboard(text)
        loop = GLib.MainLoop()
        threading.Timer(0.4, lambda: (self.key('v', ('Control_L',)), loop.quit())).start()
        GLib.timeout_add(2500, loop.quit)
        loop.run()                     # serve the selection while Ctrl+V is delivered

    def search_open(self, st, f, g, name):
        """Chats search box <- name -> click the best match inside the results' 'Group Chats' section.
        The full name sometimes does not hit (a leading 'A', a remark, odd spacing): retry with the
        longest CJK/alnum run of the name."""
        if self.sublist_header(st, f, g):
            f = self.leave_sublist(st, f, g)
        runs = re.findall(r'[\u4e00-\u9fff]{2,}', name) + re.findall(r'[A-Za-z0-9]{3,}', name)
        queries = [name]
        if runs:
            longest = max(runs, key=len)
            for q in (longest, longest[:6], longest[:4], longest[:3], longest[:2]):
                if len(q) >= 2 and plain(q) != plain(name) and q not in queries:
                    queries.append(q)
        err = None
        for q in queries:
            try:
                return self._search_once(st, f, g, name, q)
            except (Stop, Unknown) as e:
                err = e
                f = self.look(st)
        raise err

    def _search_once(self, st, f, g, name, query):
        self.act(st, f, abspt(g, SEARCH_BOX), 'search-box', g)
        time.sleep(0.3)
        self.key('a', ('Control_L',)); self.key('BackSpace')       # clear a previous query
        time.sleep(0.3)
        self.paste(query)
        time.sleep(1.0)

        def score(a, b):
            ca, cb = canon(a), canon(b)
            if not ca or not cb:
                return 0.0
            if ca == cb:
                return 1.0
            if ca in cb or cb in ca:
                return 0.9
            return difflib.SequenceMatcher(None, ca, cb).ratio()

        def found(f):
            texts = self.ocr_box(st, f['im'], absbox(g, LIST))
            rel = [(t[0].strip(), t[2][0] - g['x'], t[2][1] - g['y']) for t in texts]
            hdr = [r for r in rel if plain(r[0]) == 'groupchats']
            if not hdr:
                raise Unknown('"Group Chats" result section not shown yet')
            y0 = hdr[0][2]
            times = [r for r in rel if r[1] >= 190]
            cand = []
            for t, x, y in sorted(rel, key=lambda r: r[2]):
                if y <= y0 + 12:
                    continue
                c = plain(t)
                if c.startswith('viewall') or c in ('internetsearchresults', 'groupchats', 'contacts',
                                                    'chathistory', 'officialaccounts', 'serviceaccounts'):
                    break
                if any(abs(tm[2] - y) <= 9 for tm in times):
                    break                                     # the normal chat list resumed: section ended
                if 105 <= x <= 190:
                    cand.append((t, x, y))
            if not cand:
                raise Unknown('no group result under "Group Chats"')
            best = max(cand, key=lambda c: score(c[0], name))
            if score(best[0], name) < 0.55:
                raise Unknown('no group result matching %r (got %r)' % (name, [c[0] for c in cand]))
            return dict(name=best[0], y=best[2], score=round(score(best[0], name), 3))
        f, row = self.poll(st, 'search', found)
        t_before = self.title_of(st, f['im'], g)
        self.act(st, f, (g['x'] + 170, g['y'] + row['y'] + 6), 'search-result', g)
        t_click = time.time()

        def ready(f):
            t = self.title_of(st, f['im'], g)
            if not canon(t):
                raise Unknown('chat header not read yet')
            if canon(t) == canon(t_before) and not row_name_match(name, t) \
                    and time.time() - t_click < 3.0:
                raise Unknown('chat header unchanged since before the click: %r' % t)
            if not row_name_match(name, t):
                raise Unknown('chat header is %r, not %r' % (t, name))
            return t
        f, title = self.poll(st, 'chat', ready)
        self.j.event(kind='search_open', want=name, query=query, got=row['name'], score=row['score'], title=title)
        return f, title

    def run_list(self, entries, tag='only'):
        """Targeted pass: for each group (name or {name, members}), find it with the Chats search box and send.
        A few misses are acceptable -- the search box is a shortcut, not a proof of coverage."""
        T0 = self.T0 = time.time()
        self.dispatched = 0
        f, g, ledger = self.cold_start()
        if bv.AUTO_RID:
            f = self.campaign(g, f, ledger)
        self.load_sent()
        st = Stage('chats')
        self.act(st, f, abspt(g, W_CHATS_TAB), 'chats-tab', g)
        f, _ = self.poll(st, 'contacts', self.main_active)
        self.finish_stage(st)
        for ent in entries:
            name = ent['name'] if isinstance(ent, dict) else str(ent)
            members = ent.get('members') if isinstance(ent, dict) else None
            st = Stage('search')
            rec = dict(row_name=name, row_key='%s:%s' % (tag, name), stages=[], t0=time.time())
            try:
                f, title = self.search_open(st, f, g, name)
                rec['stages'].append(self.finish_stage(st))
            except (Stop, Unknown) as e:
                rec.update(outcome='SEARCH_FAILED', reason=str(e)[:160])
                self.close_row(rec, f)
                try:
                    f = self.recover(g)
                except Stop:
                    raise
                continue
            if not row_name_match(name, title):
                rec.update(outcome='SEARCH_MISMATCH', reason='opened %r for %r' % (title, name))
                self.close_row(rec, f)
                f = self.recover(g)
                continue
            f, rec = self.classify_and_send(rec, title, g, f, ledger, assumed_members=members)
            f = self.recover(g)
        return self.finish_batch(T0, [], dict(targeted=len(entries), sent=self.sent_groups))

    # ---------------------------------------------------------------- cold start (from batch_v2.run)
    def cold_start(self):
        st = Stage('cold_start')
        lockfd = os.open(bv.PROD_LOCK, os.O_RDWR)
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('production controller lock busy')
        s = time.time(); ledger = self._ledger = bv.Ledger(bv.LEDGER)
        need(not ledger.unresolved(), 'ledger has unresolved operations: %r' % ledger.unresolved()); st.add('ledger', s)
        self.j.event(kind='start', mode=MODE, request=bv.REQUEST_ID, send=self.send,
                     max_groups=self.max_groups, max_rows=self.max_rows)
        s = time.time()
        eng = wxio.ocr_engine()
        import cv2
        warm = np.full((48, 200, 3), 255, np.uint8); cv2.putText(warm, 'warmup', (5, 35), 0, 1, (0, 0, 0), 2)
        eng(warm); eng(warm, use_det=False, use_cls=False, use_rec=True); st.add('ocr', s)
        s = time.time(); full = wxio.observe(); st.add('window', s)
        self.pid = full['pid']; g = self.g = full['main']['geom']
        # all calibrated points are anchored at the window's top-left, so a couple of pixels of window
        # manager drift is harmless; anything bigger means the layout cannot be trusted
        need(abs(g['w'] - bv.MAIN_SIZE[0]) <= 4 and abs(g['h'] - bv.MAIN_SIZE[1]) <= 4,
             'main geometry not calibrated: %r vs %r' % ((g['w'], g['h']), bv.MAIN_SIZE))
        if len(full['wechat']) > 1:                 # a popup left over from an earlier run
            self.epoch += 1
            s = time.time(); self.x.key('Escape'); st.add('input', s)
            time.sleep(0.6)
            s = time.time(); full = wxio.observe(); st.add('window', s)
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
        need(acc == bv.ACCOUNT, 'wrong/unknown account: %r' % acc)
        f, _ = self.poll(st, 'popup_gone', self.main_active)
        self.cold = self.finish_stage(st, account=acc)
        return f, g, ledger

    def run(self):
        T0 = self.T0 = time.time()
        self.dispatched = 0
        f, g, ledger = self.cold_start()
        if bv.AUTO_RID:
            f = self.campaign(g, f, ledger)            # first favorite title -> REQUEST_ID (leaves Favorites tab)
        self.load_sent()
        st = Stage('chats_top')
        self.act(st, f, abspt(g, W_CHATS_TAB), 'chats-tab', g)
        f, _ = self.poll(st, 'contacts', self.main_active)
        f = self.leave_sublist(st, f, g)
        f = self.scroll_to_top(st, f, g)
        f = self.leave_sublist(st, f, g)
        self.finish_stage(st)
        done = set()
        f = self.enumerate_list(st, f, g, ledger, done)
        return self.finish_batch(T0, [], dict(groups=len(self.groups), sent=self.sent_groups))

    def finish_batch(self, T0, seen, tail):
        out = dict(mode=MODE, send=self.send, wall_s=round(time.time() - T0, 3), ocr_calls=self.ocr_calls,
                   sent=self.sent_groups, conversations=len(self.groups), tail=tail,
                   new_groups=self.new_groups, groups=self.groups, evidence=str(self.dir),
                   debug_frames_dropped=self.sink.dropped)
        (self.dir / 'new_groups.json').write_text(json.dumps(self.new_groups, ensure_ascii=False, indent=1))
        # keep the local roster in step with everything sent so far
        ros = {canon(e['name']): e for e in load_json_list(ROSTER_FILE) if e.get('name')}
        for e in self.sent_log:
            if e.get('members') and canon(e['name']) not in ros:
                ros[canon(e['name'])] = dict(name=e['name'], members=e['members'])
        save_json_list(ROSTER_FILE, sorted(ros.values(), key=lambda e: -(e.get('members') or 0)))
        self.j.event(kind='finish', **{k: v for k, v in out.items() if k != 'groups'})
        self.sink.close(); self.j.close(); self.rep.close()
        (self.dir / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return out


if __name__ == '__main__':
    send = '--send' in sys.argv
    need(send or '--no-send' in sys.argv, 'specify --send or --no-send')
    mg = int(sys.argv[sys.argv.index('--max-groups') + 1]) if '--max-groups' in sys.argv else None
    mr = int(sys.argv[sys.argv.index('--max-rows') + 1]) if '--max-rows' in sys.argv else None
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
    roster = sys.argv[sys.argv.index('--roster') + 1] if '--roster' in sys.argv else None
    eng = GroupSendEngine(send, mg, mr)
    try:
        if only:
            ents = []
            for line in open(only, encoding='utf-8'):
                line = line.rstrip('\n')
                if not line.strip():
                    continue
                parts = line.split('\t')
                ents.append(dict(name=parts[0].strip(), members=int(parts[1]))
                            if len(parts) > 1 and parts[1].strip().isdigit() else parts[0].strip())
            r = eng.run_list(ents, tag='only')
        elif roster:
            data = load_json_list(roster)
            if not data:
                data = [l.strip() for l in open(roster, encoding='utf-8') if l.strip()]
            r = eng.run_list(data, tag='roster')
        else:
            r = eng.run()
        print(json.dumps({k: v for k, v in r.items() if k not in ('groups',)}, ensure_ascii=False, indent=1, default=str))
    except (Stop, Unknown, Exception) as e:
        e = Stop('%s: %s' % (type(e).__name__, e)) if not isinstance(e, Stop) else e
        eng.j.event(kind='stop', reason=str(e))
        try:
            eng.finish_batch(eng.T0, [], dict(stopped=str(e)))
        except Exception as e2:
            print('finish failed', e2)
        print('STOP:', e)
        sys.exit(2)
