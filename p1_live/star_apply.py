"""star_apply: phase 2 of star_v1 -- star the friends that phase 1 (star_v1 --dry-run) classified as STAR.

Starring makes WeChat rebuild the Contacts list (new 'Starred' section) and jump back to the top, so a single
pass cannot keep its place. Phase 1 therefore only classifies (and records the ordered roster of row names);
this phase seeks each candidate in roster order:
  scan page (list OCR) -> align page rows to the roster by name votes -> scroll by the row distance -> repeat
  -> click row -> profile OCR: Weixin ID must equal the phase-1 ID -> profile '...' menu: Star / Unstar
  -> (not starred) row still selected at its band -> right-click -> menu must read Messages / Starred /
     Delete Contact -> hover + click 'Starred' -> profile '...' menu must now read Unstar.
Any unverified star stops the run (a wrong row might have been toggled).

Usage: python3 -I star_apply.py --apply|--dry-run <phase-1 run dir> [<run dir> ...]   (dirs in run order)
"""
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import star_v1 as sv  # noqa: E402  (sets the star request id / ledger env before batch_v2 is imported)
from star_v1 import (StarEngine, Stage, Unknown, Stop, need, wxio, absbox, abspt, canon, similar, fold_wxid,  # noqa: E402
                     row_selected, perceive_profile_fast, name_match, ACCOUNT, W_CONTACTS_TAB, MENU_CLICK)
import batch_v2 as bv  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import fcntl  # noqa: E402

MAX_SEEK_STEPS = 60
FORCE_STAR = {int(v) for v in sys.argv[sys.argv.index('--force-star') + 1].split(',')} if '--force-star' in sys.argv else set()
ALTS = 10 if '--positional' in sys.argv else 4
POSITIONAL = '--positional' in sys.argv    # leftovers pass: accept the row at the expected position (ID checks follow)
STARRED_BEFORE = ('A.阿萌baby', 'Adelaide小北京')   # starred by hand during development (not in the ledger)
RECHECK = ('UNSURE', 'SKIPPED_PRE_SEND', 'STAR_UNVERIFIED')   # phase-1 rows whose chat is classified again here


def load_phase1(dirs):
    """-> (roster names in list order, candidates [dict(idx, row_name, name, weixin_id)])"""
    roster, cands = [], []
    for d in dirs:
        # events.jsonl, not result.json: a killed run (supervisor restart) has no result.json
        cs = [e for e in (json.loads(l) for l in (Path(d) / 'events.jsonl').read_text().splitlines() if l.strip())
              if e.get('kind') == 'contact']
        if roster and cs and canon(cs[0]['row_name']) == canon(roster[-1]['row_name']):
            roster.pop()                   # restart re-processed the selected row: keep the newer record
        roster.extend(cs)
    out = []
    for i, c in enumerate(roster):
        if c['outcome'] == 'DRY_RUN_WOULD_STAR' and '--recheck-all' in sys.argv:
            # classify the chat again with the current code right before starring (classifier fixed mid-run)
            out.append(dict(idx=i, row_name=c['row_name'], name=None, weixin_id=None, recheck='RECHECK_ALL',
                            phase1_weixin_id=c.get('weixin_id')))
        elif c['outcome'] == 'DRY_RUN_WOULD_STAR':
            out.append(dict(idx=i, row_name=c['row_name'], name=c.get('name'), weixin_id=c.get('weixin_id')))
        elif c['outcome'] in RECHECK:
            out.append(dict(idx=i, row_name=c['row_name'], name=None, weixin_id=None, recheck=c['outcome']))
    return [c['row_name'] for c in roster], out


def align(page_rows, names, hint, skip_names=()):
    """Offset o such that page row k (complete rows only) is about names[o + k]. Name votes: exact (canonical)
    matches over the whole list, fuzzy ones near `hint`; votes are pooled over +-2 because the live list can lag
    behind the effective roster by a few not-yet-refreshed stars."""
    idx = {}
    for j, n in enumerate(names):
        if canon(n):
            idx.setdefault(canon(n), []).append(j)
    comp = [r for r in page_rows if r['complete']]
    votes = {}
    for k, r in enumerate(comp):
        c = canon(r['name'])
        if not c or c in skip_names:       # starred friends sit in the Starred section: no vote
            continue
        js = set(idx.get(c, []))
        for j in range(max(0, hint - 60), min(len(names), hint + 60)):
            if j not in js and canon(names[j]) and similar(names[j], r['name']):
                js.add(j)
        for j in js:
            votes[j - k] = votes.get(j - k, 0) + 1
    if not votes:
        return None, comp
    score = {o: sum(votes.get(o + d, 0) for d in (-2, -1, 0, 1, 2)) for o in votes}
    best = max(score, key=lambda o: (score[o], votes[o], -abs(o - hint)))
    named = sum(1 for r in comp if canon(r['name']) and canon(r['name']) not in skip_names)
    if score[best] < 3 or score[best] < named / 2:
        return None, comp
    return best, comp


class ApplyEngine(StarEngine):
    def __init__(self, star, roster, cands):
        super().__init__(star, None)
        old = self.dir
        self.run_id = time.strftime('apply_%Y%m%dT%H%M%S') + ('_star' if star else '_dry')
        self.dir = wxio.OUT / self.run_id
        old.rename(self.dir)
        self.j.f.close()
        self.j = bv.wxfast.Journal(self.dir / 'events.jsonl')
        self.sink.dir = self.dir
        self.roster, self.cands = roster, cands
        self.rows_per_notch = 2.5
        self.results = []

    def cold_start(self):
        st = Stage('cold_start')
        lockfd = os.open(bv.PROD_LOCK, os.O_RDWR)
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('production controller lock busy')
        self._lockfd = lockfd
        self.ledger = bv.Ledger(bv.LEDGER)
        eng = wxio.ocr_engine()
        warm = np.full((48, 200, 3), 255, np.uint8); cv2.putText(warm, 'warmup', (5, 35), 0, 1, (0, 0, 0), 2)
        eng(warm); eng(warm, use_det=False, use_cls=False, use_rec=True)
        full = wxio.observe()
        self.pid = full['pid']; g = self.g = full['main']['geom']
        need((g['w'], g['h']) == bv.MAIN_SIZE, 'main geometry not calibrated')
        f, _ = self.poll(st, 'popup_gone', self.main_active)
        self.act(st, f, abspt(g, bv.W_AVATAR), 'avatar', g)

        def popup(f):
            pops = [w for w in f['owner']['wechat'] if w['id'] != f['owner']['main']['id']]
            if len(pops) != 1 or f['owner']['active'] != pops[0]['id']:
                raise Unknown('self popup not yet shown')
            return pops[0]['geom']
        f, pg = self.poll(st, 'popup', popup)
        texts = self.ocr_box(st, f['im'], [pg['x'], pg['y'], pg['w'], pg['h']])
        ids = [re.sub(r'\s+', '', t[0]).split(':', 1)[1] for t in texts
               if re.sub(r'\s+', '', t[0]).lower().startswith('weixinid:')]
        self.epoch += 1
        self.x.key('Escape')
        need(ids == [ACCOUNT], 'wrong/unknown account: %r' % ids)
        f, _ = self.poll(st, 'popup_gone', self.main_active)
        # every star of every round sits in the Starred section (S rows, names); roster indices only of this round
        self.S = len(STARRED_BEFORE) + self.ledger.db.execute(
            "SELECT count(*) FROM ops WHERE state='STARRED'").fetchone()[0]
        self.starred_names = {canon(n) for n in STARRED_BEFORE}
        self.starred_idx = {i for i, n in enumerate(self.roster) if n in STARRED_BEFORE}
        for rid, intent in self.ledger.db.execute("SELECT request_id,intent FROM ops WHERE state='STARRED'"):
            d = json.loads(intent or '{}')
            self.starred_names |= {canon(d.get('row') or ''), canon(d.get('name') or '')} - {''}
            if rid == bv.REQUEST_ID and d.get('phase1_idx') is not None:
                self.starred_idx.add(d['phase1_idx'])
        self.j.event(kind='start', mode='star_apply', send=self.send, candidates=len(self.cands), roster=len(self.roster))
        self.finish_stage(st, account=ids[0])
        return f

    def to_contacts(self, st, f):
        g = self.g
        self.act(st, f, abspt(g, W_CONTACTS_TAB), 'contacts-tab', g)
        f, _ = self.poll(st, 'scroll', self.list_stable(g))
        return f

    # -- list positioning: scrollbar thumb drag for long jumps, paced wheel notches for the rest
    SB_X, SB_Y0, SB_Y1 = 296, 33, 770          # window-relative scrollbar column / track

    def thumb(self, st):
        """Hover the list so the overlay scrollbar shows; -> (top, bottom) of the thumb (window-relative y)."""
        g = self.g
        self.x.move(g['x'] + 180, g['y'] + 400); time.sleep(0.15)
        self.x.move(g['x'] + 200, g['y'] + 410); time.sleep(0.35)
        f = self.look(st)
        col = np.asarray(f['im'].crop((g['x'] + self.SB_X - 1, g['y'] + self.SB_Y0, g['x'] + self.SB_X,
                                       g['y'] + self.SB_Y1 - 3))).astype(int)[:, 0]
        on = list((col.max(axis=1) <= 185) & (col.min(axis=1) >= 130)) + [False]
        best, st0 = (0, 0), None                # longest contiguous gray run = the thumb
        for i, v in enumerate(on):
            if v and st0 is None:
                st0 = i
            elif not v and st0 is not None:
                if i - st0 > best[1] - best[0]:
                    best = (st0, i)
                st0 = None
        if not 12 <= best[1] - best[0] <= 120:
            return None
        return self.SB_Y0 + best[0], self.SB_Y0 + best[1] - 1

    def drag_thumb(self, st, frac):
        g = self.g
        th = self.thumb(st)
        if th is None:
            return False
        t0, t1 = th
        h = t1 - t0
        y_to = self.SB_Y0 + frac * (self.SB_Y1 - self.SB_Y0 - h) + h / 2
        y_from = (t0 + t1) / 2
        self.epoch += 1
        self.j.event(kind='input', stage=st.name, label='thumb-drag', frm=y_from, to=y_to, epoch=self.epoch)
        X = self.x
        X.move(g['x'] + self.SB_X, g['y'] + int(y_from)); time.sleep(0.1)
        X.xt.XTestFakeButtonEvent(X.d, 1, 1, 0); X.x.XSync(X.d, 0); time.sleep(0.08)
        steps = 12
        for i in range(1, steps + 1):
            X.move(g['x'] + self.SB_X, g['y'] + int(y_from + (y_to - y_from) * i / steps)); time.sleep(0.02)
        time.sleep(0.08)
        X.xt.XTestFakeButtonEvent(X.d, 1, 0, 0); X.x.XSync(X.d, 0)
        X.move(g['x'] + 700, g['y'] + 16)
        return True

    def wheel(self, st, notches):
        """paced wheel: ~1.7 rows/notch at 30 ms; faster bursts are partly dropped by the client"""
        g = self.g
        s = time.time(); live = self.q.observe(self.pid); st.add('window', s)
        need(live['active'] == live['main']['id'] and len(live['wechat']) == 1, 'not on main for scroll')
        self.epoch += 1
        self.j.event(kind='input', stage=st.name, label='wheel', notches=notches, epoch=self.epoch)
        b = 5 if notches > 0 else 4
        X = self.x
        X.move(g['x'] + 180, g['y'] + 450)
        for i in range(abs(notches)):
            X.xt.XTestFakeButtonEvent(X.d, b, 1, 0); X.xt.XTestFakeButtonEvent(X.d, b, 0, 0); X.x.XSync(X.d, 0)
            time.sleep(0.03)
        X.move(g['x'] + 700, g['y'] + 16)

    def effective(self):
        """roster positions still in the alphabetical list (a starred friend leaves it for the Starred section)"""
        eff = [i for i in range(len(self.roster)) if i not in self.starred_idx]
        return eff, [self.roster[i] for i in eff], {i: p for p, i in enumerate(eff)}

    def seek(self, st, f, target):
        """Bring roster[target] onto the page as a complete row; -> (f, row)."""
        g = self.g
        eff, names, pos = self.effective()
        if target not in pos:
            raise Unknown('target already starred')
        te = pos[target]
        want = self.roster[target]
        self.seek_alts = []
        hint, misses, samples = te, 0, []          # samples: (thumb fraction, aligned effective position)
        for step in range(MAX_SEEK_STEPS):
            page = self.scan(st, f, g)
            if page.get('count'):
                self.total = page['count']         # Contacts header count (list length in rows)
            o, comp = align(page['rows'], names, hint, self.starred_names)
            if o is None and page['top']:
                o = 0                              # list top: the first complete Contacts row
            if o is None:
                named = [r for r in page['rows'] if r['complete'] and canon(r['name'])]
                in_starred = len(named) >= 3 and all(canon(r['name']) in self.starred_names for r in named)
                if in_starred:                     # inside the Starred section: just move down
                    self.wheel(st, 15)
                    f, _ = self.poll(st, 'scroll', self.list_stable(g))
                    continue
                misses += 1
                need(misses < 8, 'seek: list position not recognised')
                n = max(getattr(self, 'total', 0), len(names), 1) + self.S
                if misses <= 2 and self.drag_thumb(st, min(1.0, max(0, te - 120 + self.S) / n)):
                    pass
                else:
                    self.wheel(st, 6 if misses % 2 else -12)
            else:
                hint = o
                k0 = te - o
                if -3 <= k0 < len(comp) + 3:
                    w = 6 if POSITIONAL else 3
                    near = sorted(range(max(0, k0 - w), min(len(comp), k0 + w + 1)), key=lambda k: abs(k - k0))
                    named = [k for k in near if canon(want) and similar(comp[k]['name'], want)]
                    order = named + [k for k in near if k not in named]
                    # alternatives for the Weixin ID check (duplicate names, OCR-misread roster names)
                    self.seek_alts = [comp[k] for k in order[1:]]
                    if named or (0 <= k0 < len(comp) and (not canon(want) or POSITIONAL)):
                        return f, comp[order[0]]
                    if 1 <= k0 < len(comp) - 1:
                        raise Unknown('row %r not found near its position (page %r)' % (want, [r['name'] for r in comp]))
                mid = o + len(comp) // 2
                if abs(te - mid) > 250:
                    th = self.thumb(st)
                    if th is not None:
                        span = self.SB_Y1 - self.SB_Y0 - (th[1] - th[0])
                        samples.append(((th[0] - self.SB_Y0) / span, mid))
                    # aim short of the target (overshooting past the roster end cannot be aligned); wheel the rest
                    aim = te - 80 if te > mid else te + 80
                    n = max(getattr(self, 'total', 0), len(names), 1) + self.S
                    if len(samples) >= 2 and abs(samples[-1][1] - samples[-2][1]) > 20:
                        (f1, r1), (f2, r2) = samples[-2], samples[-1]
                        frac = f1 + (aim - r1) * (f2 - f1) / (r2 - r1)
                    elif samples:
                        # measured ~1.1 x list length rows per full thumb travel (sections/headers add height)
                        frac = samples[-1][0] + (aim - samples[-1][1]) / (1.1 * n)
                    else:
                        frac = (aim + self.S) / n
                    self.j.event(kind='seek', target=target, te=te, mid=mid, thumb=th, samples=samples[-2:], frac=frac)
                    if not self.drag_thumb(st, min(1.0, max(0.0, frac))):
                        self.wheel(st, int((te - mid) / 1.7))
                else:
                    d = te - mid
                    self.wheel(st, int(round(d / 1.7)) or (1 if d > 0 else -1))
            f, _ = self.poll(st, 'scroll', self.list_stable(g))
        raise Unknown('seek: %r not reached in %d steps' % (want, MAX_SEEK_STEPS))

    def apply_one(self, f, c):
        g = self.g
        rec = dict(c, stages=[])
        self.results.append(rec)
        st = Stage('seek')
        f = self.to_contacts(st, f)
        f, row = self.seek(st, f, c['idx'])
        rec['stages'].append(self.finish_stage(st, row=row['name']))

        st = Stage('select')
        if c.get('recheck'):
            f = self.select_row(st, f, row)
            rec['stages'].append(self.finish_stage(st))
            if c['idx'] in FORCE_STAR:
                decision = 'STAR'              # chat inspected by eye (animated stickers defeat the scroll scan)
                rec['title'] = row['name']
            else:
                f, decision = self.classify(rec, row, f)
            rec['decision'] = decision
            if decision != 'STAR':
                rec['outcome'] = decision
                return f
            st = Stage('select2')
            f = self.select_row(st, self.look(st), row)
            f, p = self.read_profile(st, f, row)
            rec['profile_id'] = p['weixin_id']
            need(fold_wxid(p['weixin_id']) != fold_wxid(ACCOUNT), 'recheck row is self')
            if canon(p['name']) and canon(row['name']) and not (name_match(row['name'], p['name'])
                                                               or name_match(p['name'], rec.get('title', ''))):
                raise Unknown('row/profile association %r vs %r' % (row['name'], p['name']))
        else:
            # same/similar display names are common: try the nearby candidate rows until the Weixin ID matches
            tried = []
            for cand in [row] + self.seek_alts[:ALTS]:
                f = self.select_row(st, self.look(st) if tried else f, cand)
                f, p = self.read_profile(st, f, cand)
                tried.append(p['weixin_id'])
                if fold_wxid(p['weixin_id']) == fold_wxid(c['weixin_id'] or ''):
                    row = cand
                    break
            else:
                rec['stages'].append(self.finish_stage(st))
                raise Unknown('profile %r is not candidate %r' % (tried, c['weixin_id']))
            rec['profile_id'] = p['weixin_id']
        f, state = self.star_state(st, f, g)
        rec['state_before'] = state
        rec['stages'].append(self.finish_stage(st, state=state))
        if state == 'starred':
            rec['outcome'] = 'ALREADY_STARRED'
            self.starred_idx.add(c['idx'])
            return f
        need(state == 'not_starred', 'star state unreadable: %r' % state)
        if not self.send:
            rec['outcome'] = 'DRY_RUN_WOULD_STAR'
            return f

        st = Stage('star')
        # the list may rebuild at any time after an earlier star: the target must still be the selected row here
        f = self.look(st)
        need(row_selected(f['im'], g, row['band']), 'row moved before right-click')
        self.menu_probes = None
        f, pt, m = self.open_menu(st, f, row, g)
        if m.get('self') or canon(m['starred']) != canon('Starred'):
            self.close_menu(st)
            raise Unknown('row menu item %r' % m['starred'])
        op_key = '%s|%s|wxid:%s' % (bv.REQUEST_ID, ACCOUNT, p['weixin_id'])
        self.ledger.put(op_key, 'STAR_CLICKING', intent=dict(row=row['name'], name=p['name'], weixin_id=p['weixin_id'],
                                                             phase1_idx=c['idx'], run=self.run_id))
        self.menu_click(st, (pt[0] + MENU_CLICK['starred'][0], pt[1] + MENU_CLICK['starred'][1]), 'menu-starred')
        f = self.wait_menu_closed(st, self.menu_probes)
        f, after = self.star_state(st, f, g)
        rec['state_after'] = after
        rec['stages'].append(self.finish_stage(st, state=after))
        if after != 'starred':
            self.ledger.put(op_key, 'STAR_UNVERIFIED', result=dict(at=time.time(), state=after))
            rec['outcome'] = 'STAR_UNVERIFIED'
            raise Stop('HALT: star not verified for %r (%s): %r' % (p['name'], p['weixin_id'], after))
        self.ledger.put(op_key, 'STARRED', result=dict(at=time.time()))
        self.starred_names |= {canon(row['name']), canon(p['name'])} - {''}
        self.starred_idx.add(c['idx'])
        self.S += 1
        rec['outcome'] = 'STARRED'
        self.starred += 1
        return f

    def select_row(self, st, f, row):
        g = self.g
        self.act(st, f, row['center'], 'contact-row', g)
        prev = {}

        def ready(f):
            self.main_active(f)
            if not row_selected(f['im'], g, row['band']):
                raise Unknown('row not selected')
            x, y, w, h = absbox(g, (520, 85, 350, 680))
            sig = np.asarray(f['im'].crop((x, y, x + w, y + h)))[::4, ::4].tobytes()
            same = prev.get('sig') == sig
            prev['sig'] = sig
            if not same:
                raise Unknown('profile still changing')
            return {}
        f, _ = self.poll(st, 'profile', ready)
        return f

    def read_profile(self, st, f, row):
        p, err = None, ''
        for attempt in range(2):
            try:
                p = perceive_profile_fast(f['im'], self.g, row['band'])
                break
            except Unknown as e:
                err = str(e)
            time.sleep(0.25); f = self.look(st)
        if p is None:
            raise Unknown('profile unreadable: %s' % err)
        return f, p

    def classify(self, rec, row, f):
        """row menu -> Messages -> chat -> scan (star_v1 logic) -> back to Contacts; -> (f, decision)"""
        g = self.g
        st = Stage('open_chat')
        f, p, m = self.open_menu(st, f, row, g)
        if m.get('self'):
            self.close_menu(st)
            return self.look(st), 'EXCLUDED_SELF'
        self.menu_click(st, (p[0] + MENU_CLICK['messages'][0], p[1] + MENU_CLICK['messages'][1]), 'menu-messages')
        prev = {}

        t_open = time.time()

        def chat_ready(f):
            self.main_active(f)
            t = self.read_title(f['im'], g)
            # recheck rows often failed phase 1 on a one-glyph title OCR slip: also accept a title that has stayed
            # the same for >=1.2 s after the row-menu 'Messages' click (the chat opened from this very row)
            settled = time.time() - t_open > 1.2 and prev.get('title') == t
            prev['title'] = t
            if not (name_match(row['name'], t) or settled):
                raise Unknown('chat title %r not yet %r' % (t, row['name']))
            x, y = g['x'], g['y']
            sig = np.asarray(f['im'].crop((x + sv.CX0, y + sv.CY0, x + sv.CX1, y + sv.CY1)))[::3, ::3]
            same = sv.sig_stable(prev.get('sig'), sig)
            prev['sig'] = sig
            if not same:
                raise Unknown('chat still rendering')
            return t
        try:
            f, title = self.poll(st, 'chat_open', chat_ready)
        except Stop as e:
            raise Unknown('chat: %s' % e)
        rec['title'] = title
        crop = lambda im: np.asarray(im.crop((g['x'], g['y'], g['x'] + g['w'], g['y'] + g['h']))).astype(np.int16)
        rec['_chat_arr'] = crop(f['im'])
        rec['stages'].append(self.finish_stage(st, title=title))
        st = Stage('scan_chat')
        decision, ev = self.scan_chat(st, g, rec)
        if decision == 'NO_MESSAGES':
            time.sleep(0.5)
            rec['_chat_arr'] = crop(self.look(st)['im'])
            decision, ev = self.scan_chat(st, g, rec)
        if decision == 'UNSURE' and 'registration' in str(ev.get('reason')):
            # tall items made a 6-notch scroll jump past the viewport: back to the bottom, rescan with small steps
            X = self.x
            X.move(g['x'] + 700, g['y'] + 350)
            for i in range(80):
                X.xt.XTestFakeButtonEvent(X.d, 5, 1, 0); X.xt.XTestFakeButtonEvent(X.d, 5, 0, 0); X.x.XSync(X.d, 0)
                time.sleep(0.01)
            X.move(g['x'] + 700, g['y'] + 16)
            self.epoch += 1
            f, _ = self.poll(st, 'chat_scroll', self.chat_stable(g))
            rec['_chat_arr'] = crop(f['im'])
            saved = sv.CHAT_SCROLL_NOTCHES, sv.SHORT_SCROLL_PX, sv.MAX_CHAT_SCROLLS
            sv.CHAT_SCROLL_NOTCHES, sv.SHORT_SCROLL_PX, sv.MAX_CHAT_SCROLLS = 2, 40, 120
            try:
                decision, ev = self.scan_chat(st, g, rec)
            finally:
                sv.CHAT_SCROLL_NOTCHES, sv.SHORT_SCROLL_PX, sv.MAX_CHAT_SCROLLS = saved
            ev['small_steps'] = True
        rec.pop('_chat_arr', None)
        rec['evidence'] = ev
        self.dbg('recheck_%s_%04d' % (decision.lower(), rec['idx']), self.look(st)['im'], g)
        rec['stages'].append(self.finish_stage(st, decision=decision))
        st = Stage('return')
        self.act(st, self.look(st), abspt(g, W_CONTACTS_TAB), 'contacts-tab', g)
        f, _ = self.poll(st, 'contacts', self.main_active)
        rec['stages'].append(self.finish_stage(st))
        return f, decision

    def run_all(self):
        f = self.cold_start()
        done = {fold_wxid(k.split('|wxid:', 1)[1]) for k, s in self.ledger.db.execute(
            "SELECT op_key,state FROM ops WHERE state='STARRED'")}
        fails = 0
        for c in self.cands:
            if (c['weixin_id'] and fold_wxid(c['weixin_id']) in done) or c['idx'] in self.starred_idx:
                self.results.append(dict(c, outcome='ALREADY_STARRED_LEDGER'))
                continue
            t0 = time.time()
            try:
                f = self.apply_one(f, c)
                fails = 0
            except Unknown as e:
                self.results[-1].update(outcome='SKIPPED', reason=str(e)[:200]) if self.results and self.results[-1].get('idx') == c['idx'] \
                    else self.results.append(dict(c, outcome='SKIPPED', reason=str(e)[:200]))
                fails += 1
                need(fails < 3, 'three consecutive candidates failed')
                f = self.recover(self.g)
            self.results[-1]['cycle_ms'] = round((time.time() - t0) * 1000, 1)
            self.j.event(kind='candidate', **{k: v for k, v in self.results[-1].items() if k != 'stages'})
        return self.finish_apply()

    def finish_apply(self, stopped=None):
        from collections import Counter
        out = dict(mode='star_apply', send=self.send, wall_s=round(time.time() - self.T0, 1), stopped=stopped,
                   outcomes=dict(Counter(r.get('outcome', 'INTERRUPTED') for r in self.results)),
                   results=self.results, evidence=str(self.dir))
        self.j.event(kind='finish', outcomes=out['outcomes'], stopped=stopped)
        self.sink.close(); self.j.close()
        (self.dir / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return out


if __name__ == '__main__':
    star = '--apply' in sys.argv
    need(star or '--dry-run' in sys.argv, 'specify --apply or --dry-run')
    dirs = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith('--') and sys.argv[i - 1] not in ('--limit', '--only', '--force-star')]
    roster, cands = load_phase1(dirs)
    print('roster %d rows, %d candidates' % (len(roster), len(cands)))
    if '--only' in sys.argv:
        keep = {int(v) for v in sys.argv[sys.argv.index('--only') + 1].split(',')}
        cands = [c for c in cands if c['idx'] in keep]
    if '--limit' in sys.argv:
        cands = cands[:int(sys.argv[sys.argv.index('--limit') + 1])]
    eng = ApplyEngine(star, roster, cands)
    try:
        if '--select-last' in sys.argv:
            # leave the last phase-1 row selected so star_v1 --from-current can resume after it
            f = eng.cold_start()
            st = Stage('select_last')
            f = eng.to_contacts(st, f)
            f, row = eng.seek(st, f, len(roster) - 1)
            eng.act(st, f, row['center'], 'contact-row', eng.g)
            time.sleep(0.6)
            eng.results.append(dict(selected=row['name'], idx=len(roster) - 1, outcome='SELECTED'))
            r = eng.finish_apply()
        else:
            r = eng.run_all()
    except (Stop, Unknown, Exception) as e:
        eng.j.event(kind='stop', reason='%s: %s' % (type(e).__name__, e))
        r = eng.finish_apply(stopped='%s: %s' % (type(e).__name__, e))
    print(json.dumps({k: v for k, v in r.items() if k != 'results'}, ensure_ascii=False, indent=1))
    sys.exit(0 if not r['stopped'] else 2)
