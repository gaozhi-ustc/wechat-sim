"""fast_v2_checked: simplified single-contact flow per impl.md.

Batch once: lock, ledger, model+warmup, account. Page once: contacts OCR -> PagePlan.
Per contact: profile OCR x1 -> Messages (visual) -> favorites (visual) -> select (visual)
-> panel recipient header OCR x1 (rec-only, one full-OCR fallback) -> durable intent -> Send x1
-> wait for panel exit. Fixed sleeps replaced by short readiness polling. Zero LLM calls.

Usage:
    python3 -I fast_v2.py live --after <NAME> --no-send
    python3 -I fast_v2.py live --after <NAME> --send
"""
import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wxio  # noqa: E402
import wxfast  # noqa: E402
from wxio import Stop, need, ocr, center  # noqa: E402
import ocr_mvp_v1 as v1  # noqa: E402
from ocr_mvp_v1 import (Unknown, Ledger, absbox, abspt, close, norm, match_all, row_selected,  # noqa: E402
                        perceive_contacts, TPL, GREEN_ROW, GREEN_BTN, GRAY_BTN, MAIN_SIZE, PANEL_SIZE,
                        P_HEADER, P_ALLFAV, P_RADIOS, P_SEND, P_SEND_CLICK, P_FIRST_RADIO_Y,
                        W_ACTIVATE, W_AVATAR, W_CONTACTS_TAB, W_TOOLBAR, REQUEST_ID, ACCOUNT,
                        SELF_NAMES, SYSTEM_NAMES, PROD_LOCK, LEDGER)
import numpy as np  # noqa: E402
import cv2  # noqa: E402

MODE = 'fast_v2_checked'
W_PROFILE_FAST = (520, 85, 350, 680)
P_SEARCH_TPL = (38, 36)            # panel-relative top-left of default search box template
TPL_SEARCH = cv2.imread(str(HERE / 'templates' / 'panel_search_default.png'))
POLL = 0.12
# (first wait, hard timeout) seconds, impl.md section 4 initial values
WAITS = dict(popup=(0.25, 1.5), contacts=(0.25, 1.5), profile=(0.25, 1.5), chat=(0.30, 1.8),
             panel=(0.35, 2.0), selected=(0.10, 0.8), exit=(0.15, 1.5), popup_gone=(0.10, 1.0))


class Stage:
    def __init__(self, name):
        self.name = name
        self.t0 = time.time()
        self.c = dict(wait=0.0, capture=0.0, window=0.0, ocr=0.0, classify=0.0, input=0.0, ledger=0.0)
        self.n = dict(polls=0, ocr_calls=0, fallbacks=0)

    def add(self, k, s):
        self.c[k] += time.time() - s

    def done(self):
        self.total = time.time() - self.t0
        out = dict(stage=self.name, total_ms=round(self.total * 1000, 1))
        out.update({k + '_ms': round(v * 1000, 1) for k, v in self.c.items()})
        out['other_ms'] = round((self.total - sum(self.c.values())) * 1000, 1)
        out.update(self.n)
        return out


# ---------------------------------------------------------------- visual/OCR perception

def chat_visual(im, g):
    cubes = match_all(im, absbox(g, W_TOOLBAR), TPL['cube'], 0.80)
    if len(cubes) != 1 or cubes[0][0] < 0.92:
        raise Unknown('favorites toolbar icon not unique: %r' % cubes)
    return dict(cube=cubes[0][1:], cube_score=round(cubes[0][0], 3))


def panel_visual(im, p):
    send_px = im.getpixel(abspt(p, P_SEND))
    send = 'enabled' if close(send_px, GREEN_BTN, 25) else 'disabled' if close(send_px, GRAY_BTN, 8) else 'unknown'
    empty = match_all(im, absbox(p, P_RADIOS), TPL['radio_empty'], 0.85)
    checked = match_all(im, absbox(p, P_RADIOS), TPL['radio_checked'], 0.85)
    radios = sorted([dict(y=y, x=x, checked=False) for s, x, y in empty]
                    + [dict(y=y, x=x, checked=True) for s, x, y in checked], key=lambda r: r['y'])
    for a, b in zip(radios, radios[1:]):
        if abs(a['y'] - b['y']) < 30:
            raise Unknown('ambiguous radio state')
    if not radios:
        raise Unknown('no favorite items visible (loading?)')
    sx, sy = abspt(p, P_SEARCH_TPL)
    th, tw = TPL_SEARCH.shape[:2]
    hay = np.asarray(im.crop((sx - 4, sy - 4, sx + tw + 4, sy + th + 4)))[:, :, ::-1].copy()
    search_score = float(cv2.minMaxLoc(cv2.matchTemplate(hay, TPL_SEARCH, cv2.TM_CCOEFF_NORMED))[1])
    return dict(send=send, radios=radios, checked=[r['checked'] for r in radios],
                all_favorites=close(im.getpixel(abspt(p, P_ALLFAV)), GREEN_ROW, 12),
                search_default=search_score >= 0.90, search_score=round(search_score, 3),
                first_at_top=abs(radios[0]['y'] - (p['y'] + P_FIRST_RADIO_Y)) <= 4)


def read_header_fast(im, p):
    """Rec-only OCR of the panel header line, tightly cropped to its ink columns."""
    x, y, w, h = absbox(p, (215, 36, 525, 26))
    arr = np.asarray(im.crop((x, y, x + w, y + h))).astype(int)
    cols = np.where((arr.max(axis=2) < 170).any(axis=0))[0]
    if not len(cols):
        return ''
    a, b = max(0, cols[0] - 8), min(w, cols[-1] + 9)
    crop = np.asarray(im.crop((x + a, y, x + b, y + h)))[:, :, ::-1].copy()
    res, _ = wxio.ocr_engine()(crop, use_det=False, use_cls=False, use_rec=True)
    return res[0][0] if res else ''


ID_RE = re.compile(r'^weixin[il1|]d[:：](.+)$')


def perceive_profile_fast(im, g, band):
    texts = ocr(im, absbox(g, W_PROFILE_FAST))
    texts.sort(key=lambda t: (t[2][1], t[2][0]))
    flat = lambda t: re.sub(r'\s+', '', t[0])
    idt = [t for t in texts if ID_RE.match(flat(t).lower())]
    if len(idt) != 1:
        raise Unknown('profile Weixin ID not unique: %r' % [t[0] for t in texts])
    wid = ID_RE.match(flat(idt[0]).lower()).group(1)
    wid = flat(idt[0])[len(flat(idt[0])) - len(wid):]          # keep original case
    # Title = topmost line of the header block above the ID line (remark if set); skip Name:/Region: lines.
    col = [t for t in texts if idt[0][2][1] - 70 < t[2][1] < idt[0][2][1] and idt[0][2][0] - 15 < t[2][0] < idt[0][2][0] + 260]
    names = [t for t in col if not re.match(r'^(name|nickname|region)[:：]', flat(t).lower())]
    if names:
        # title may be split into several boxes (emoji between words): join the topmost line by x
        y0 = min(t[2][1] + t[2][3] / 2 for t in names)
        line = sorted([t for t in names if abs(t[2][1] + t[2][3] / 2 - y0) <= 8], key=lambda t: t[2][0])
        names = [(''.join(t[0].strip() for t in line), 1.0, line[0][2])]
    nick = [flat(t).split(':', 1)[-1].split('：', 1)[-1] for t in col if re.match(r'^(name|nickname)[:：]', flat(t).lower())]
    if not names:
        # title unread (rare glyphs): fall back to the Remark value when one is set
        rem = [flat(t)[6:] for t in texts if flat(t).lower().startswith('remark') and len(flat(t)) > 6
               and flat(t)[6:].lower() != 'addalias']
        if rem:
            names = [(rem[0], 1.0, None)]
    msg = [t for t in texts if t[0].strip() in ('Messages', 'Messag', '发消息')]
    if len(msg) != 1:
        raise Unknown('Messages control not unique: %r' % [t[0] for t in texts])
    return dict(selected=row_selected(im, g, band), name=names[0][0].strip() if names else '', weixin_id=wid,
                nickname=nick[0] if nick else None,
                friend_profile=any(flat(t).lower() == 'friendprofile' for t in texts),
                calls=any(t[0].strip() == 'Voice' for t in texts) and any(t[0].strip() == 'Video' for t in texts),
                messages=center(msg[0][2]), texts=[t[0] for t in texts])


# ---------------------------------------------------------------- engine

class FastEngine:
    def __init__(self, send, after):
        self.send, self.after = send, after
        self.run_id = time.strftime('fast_%Y%m%dT%H%M%S') + ('_send' if send else '_nosend')
        self.dir = wxio.OUT / self.run_id
        self.dir.mkdir(mode=0o700)
        self.j = wxfast.Journal(self.dir / 'events.jsonl')
        self.sink = wxfast.DebugSink(self.dir)
        self.x = wxio.X()
        self.q = wxfast.XQ()
        self.epoch = 0
        self.stages = []
        self.ocr_calls = 0

    # -- primitives (each charges its time to the current stage)
    def look(self, st):
        s = time.time(); o = self.q.observe(self.pid); st.add('window', s)
        s = time.time(); at, im = wxfast.grab(); st.add('capture', s)
        return dict(at=at, im=im, owner=o, epoch=self.epoch)

    def ocr_box(self, st, im, box):
        s = time.time(); r = ocr(im, box); st.add('ocr', s)
        st.n['ocr_calls'] += 1; self.ocr_calls += 1
        return r

    def poll(self, st, key, cond):
        first, timeout = WAITS[key]
        s = time.time(); time.sleep(first); st.add('wait', s)
        deadline = time.time() + timeout
        last = None
        while True:
            f = self.look(st); st.n['polls'] += 1
            s = time.time()
            try:
                v = cond(f)
                st.add('classify', s)
                return f, v
            except Unknown as e:
                st.add('classify', s)
                last = str(e)
            if time.time() > deadline:
                self.sink.put('%s_timeout_%d.png' % (st.name, int(time.time() * 1000)), f['im'])
                raise Stop('%s not ready within %.1fs: %s' % (st.name, timeout, last))
            s = time.time(); time.sleep(POLL); st.add('wait', s)

    def act(self, st, f, point, label, owner_win):
        need(time.time() - f['at'] < 180 and f['epoch'] == self.epoch, 'stale frame/epoch')
        s = time.time(); live = self.q.observe(self.pid); st.add('window', s)
        need(live['active'] == f['owner']['active'] and live['main']['geom'] == f['owner']['main']['geom'],
             'live window context changed since frame')
        g = owner_win
        need(g['x'] <= point[0] < g['x'] + g['w'] and g['y'] <= point[1] < g['y'] + g['h'], 'target outside owning window')
        self.epoch += 1
        self.j.event(kind='input', stage=st.name, label=label, point=point, epoch=self.epoch)
        s = time.time(); self.x.click(*point); st.add('input', s)

    def finish_stage(self, st, **info):
        d = st.done(); d.update(info)
        self.stages.append(d)
        self.j.event(kind='stage', **d)
        return d

    # -- flow
    def run(self):
        T0 = time.time()
        # ---- cold start (batch once)
        st = Stage('cold_start')
        lockfd = os.open(PROD_LOCK, os.O_RDWR)
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('production controller lock busy')
        s = time.time()
        ledger = Ledger(LEDGER)
        need(not ledger.unresolved(), 'ledger has unresolved operations: %r' % ledger.unresolved())
        st.add('ledger', s)
        self.j.event(kind='start', mode=MODE, request=REQUEST_ID, send=self.send, after=self.after)
        s = time.time()
        eng = wxio.ocr_engine()
        warm = np.full((48, 200, 3), 255, np.uint8); cv2.putText(warm, 'warmup', (5, 35), 0, 1, (0, 0, 0), 2)
        eng(warm); eng(warm, use_det=False, use_cls=False, use_rec=True)
        st.add('ocr', s)
        s = time.time(); full = wxio.observe(); st.add('window', s)   # full subprocess audit once
        self.pid = full['pid']
        g = full['main']['geom']
        need((g['w'], g['h']) == MAIN_SIZE, 'main geometry not calibrated')
        main = full['main']
        if full['active'] != main['id']:
            need(len(full['wechat']) == 1, 'unexpected WeChat transient at start')
            self.epoch += 1
            s = time.time(); self.x.click(*abspt(g, W_ACTIVATE)); st.add('input', s)
            self.j.event(kind='input', stage=st.name, label='activate', epoch=self.epoch)

        def main_active(f):
            o = f['owner']
            if o['active'] != o['main']['id'] or len(o['wechat']) != 1:
                raise Unknown('main not active / transient present')
            return {}
        f, _ = self.poll(st, 'popup_gone', main_active)
        self.act(st, f, abspt(g, W_AVATAR), 'avatar', g)

        def popup(f):
            pops = [w for w in f['owner']['wechat'] if w['id'] != f['owner']['main']['id']]
            if len(pops) != 1 or f['owner']['active'] != pops[0]['id']:
                raise Unknown('self popup not yet shown')
            return pops[0]['geom']
        f, pg = self.poll(st, 'popup', popup)
        # popup content may still be painting: OCR once, one re-look if ID not read yet
        acc = None
        for attempt in range(2):
            texts = self.ocr_box(st, f['im'], [pg['x'], pg['y'], pg['w'], pg['h']])
            ids = [re.sub(r'\s+', '', t[0]).split(':', 1)[1] for t in texts
                   if re.sub(r'\s+', '', t[0]).lower().startswith('weixinid:')]
            if len(ids) == 1:
                acc = ids[0]; break
            st.n['fallbacks'] += 1
            time.sleep(0.2); f = self.look(st)
        self.epoch += 1
        s = time.time(); self.x.key('Escape'); st.add('input', s)
        self.sink.put('01_account.png', f['im'])
        need(acc == ACCOUNT, 'wrong/unknown account: %r' % acc)
        f, _ = self.poll(st, 'popup_gone', main_active)
        self.finish_stage(st, account=acc)

        # ---- contacts scan (page once)
        st = Stage('contacts_scan')
        self.act(st, f, abspt(g, W_CONTACTS_TAB), 'contacts-tab', g)
        f, _ = self.poll(st, 'contacts', main_active)
        plan = None
        for attempt in range(2):
            s = time.time()
            try:
                plan = perceive_contacts(f['im'], g)
                st.n['ocr_calls'] += 1; self.ocr_calls += 1
                if not plan['top_proof']:
                    raise Unknown('no top proof')
                break
            except Unknown as e:
                st.n['ocr_calls'] += 1; self.ocr_calls += 1
                st.n['fallbacks'] += 1
                plan = None
                time.sleep(0.3); f = self.look(st)
            finally:
                st.add('ocr', s)
        need(plan is not None, 'contacts page not recognised')
        self.sink.put('02_contacts.png', f['im'])
        rows = plan['rows']
        anchor = [i for i, r in enumerate(rows) if norm(r['name']) == norm(self.after)]
        need(len(anchor) == 1, 'anchor row %r not unique on page: %r' % (self.after, [r['name'] for r in rows]))
        target = None
        for r in rows[anchor[0] + 1:]:
            if r['name'] in SELF_NAMES or r['name'] in SYSTEM_NAMES:
                self.j.event(kind='excluded', name=r['name']); continue
            need(r['complete'], 'next candidate row partial')
            target = r; break
        need(target is not None, 'no ordinary row after anchor on this page')
        anchor_band = rows[anchor[0]]['band']
        self.finish_stage(st, rows=[r['name'] for r in rows], anchor=self.after, target=target['name'])

        # ---- per contact: row -> profile
        st = Stage('row_to_profile')
        self.act(st, f, target['center'], 'contact-row', g)
        prev = {}

        def profile_ready(f):
            im = f['im']
            if not row_selected(im, g, target['band']) or row_selected(im, g, anchor_band):
                raise Unknown('target row not selected yet')
            x, y, w, h = absbox(g, W_PROFILE_FAST)
            sig = np.asarray(im.crop((x, y, x + w, y + h)))[::4, ::4].tobytes()
            stable = prev.get('sig') == sig
            prev['sig'] = sig
            if not stable:
                raise Unknown('profile still changing')
            return {}
        f, _ = self.poll(st, 'profile', profile_ready)
        p = None
        for attempt in range(2):
            try:
                s = time.time(); p = perceive_profile_fast(f['im'], g, target['band']); st.add('ocr', s)
                st.n['ocr_calls'] += 1; self.ocr_calls += 1
                break
            except Unknown:
                st.add('ocr', s); st.n['ocr_calls'] += 1; self.ocr_calls += 1; st.n['fallbacks'] += 1
                time.sleep(0.2); f = self.look(st)
        need(p is not None, 'profile not recognised')
        self.sink.put('03_profile.png', f['im'])
        need(p['selected'], 'row not selected in profile frame')
        need(p['weixin_id'] != ACCOUNT and p['name'] not in SELF_NAMES, 'profile is self')
        need(p['friend_profile'] and p['calls'], 'not a clearly ordinary friend')
        need(norm(p['name']) and norm(p['name']) == norm(target['name']),
             'row/profile mismatch: %r vs %r' % (target['name'], p['name']))
        op_key = '%s|%s|wxid:%s' % (REQUEST_ID, ACCOUNT, p['weixin_id'])
        s = time.time(); existing = ledger.state(op_key); st.add('ledger', s)
        need(existing is None, 'already in ledger: %s' % existing)
        self.finish_stage(st, name=p['name'], weixin_id=p['weixin_id'])

        # ---- Messages -> chat (visual)
        st = Stage('messages_to_chat')
        self.act(st, f, p['messages'], 'profile-messages', g)
        f, ch = self.poll(st, 'chat', lambda f: (main_active(f), chat_visual(f['im'], g))[1])
        self.sink.put('04_chat.png', f['im'])
        self.finish_stage(st, **ch)

        # ---- favorites entry -> panel baseline (visual)
        st = Stage('open_favorites')
        self.act(st, f, ch['cube'], 'favorites-entry', g)

        def panel_base(f):
            o = f['owner']
            pans = [w for w in o['wechat'] if w['id'] != o['main']['id']]
            if len(pans) != 1 or pans[0]['transient'] != o['main']['id'] or o['active'] != pans[0]['id'] \
                    or (pans[0]['geom']['w'], pans[0]['geom']['h']) != PANEL_SIZE:
                raise Unknown('favorites panel not yet owned/active')
            v = panel_visual(f['im'], pans[0]['geom'])
            if v['send'] != 'disabled' or any(v['checked']) or not v['all_favorites'] \
                    or not v['search_default'] or not v['first_at_top']:
                raise Unknown('panel not at default zero-select baseline: %r' % v)
            v['panel'] = pans[0]
            return v
        f, pv = self.poll(st, 'panel', panel_base)
        panel = pv['panel']; pg = panel['geom']
        self.sink.put('05_panel.png', f['im'])
        self.finish_stage(st, panel_id=panel['id'], checked=pv['checked'], search_score=pv['search_score'])

        # ---- select first (visual)
        st = Stage('select_first')
        first = pv['radios'][0]
        self.act(st, f, (first['x'], first['y']), 'select-first', pg)

        def selected(f):
            o = f['owner']
            pans = [w for w in o['wechat'] if w['id'] == panel['id']]
            if not pans or o['active'] != panel['id'] or pans[0]['geom'] != pg:
                raise Unknown('panel identity changed')
            v = panel_visual(f['im'], pg)
            if v['send'] != 'enabled' or v['checked'] != [True] + [False] * (len(v['checked']) - 1) \
                    or abs(v['radios'][0]['y'] - first['y']) > 2:
                raise Unknown('not exactly first selected yet: %r' % v['checked'])
            return v
        f, sv = self.poll(st, 'selected', selected)
        self.sink.put('06_selected.png', f['im'])
        self.finish_stage(st, checked=sv['checked'])

        # ---- checked mode: final recipient header OCR (rec-only, one full fallback)
        st = Stage('recipient_check')
        s = time.time(); header = read_header_fast(f['im'], pg); st.add('ocr', s)
        st.n['ocr_calls'] += 1; self.ocr_calls += 1
        ok = lambda h: norm(h).startswith('Sendfavoritesto') and norm(p['name']) in norm(h)
        if not ok(header):
            st.n['fallbacks'] += 1
            texts = self.ocr_box(st, f['im'], absbox(pg, P_HEADER))
            header = ' '.join(t[0] for t in texts)
        need(ok(header), 'panel header not bound to recipient: %r' % header)
        self.finish_stage(st, header=header)

        intent = dict(request=REQUEST_ID, account=ACCOUNT, mode=MODE, row=target['name'], profile=p['name'],
                      weixin_id=p['weixin_id'], panel_id=panel['id'], header=header, run=self.run_id)
        if not self.send:
            st = Stage('cancel_no_send')
            self.act(st, f, abspt(pg, (520, 550)), 'cancel', pg)
            f, _ = self.poll(st, 'exit', main_active)
            self.finish_stage(st)
            return self.finish('dry_run_prepared_no_send', T0, intent)

        # ---- dispatch
        st = Stage('dispatch')
        s = time.time(); ledger.put(op_key, 'PREPARED', intent=intent, recipient_ref=json.dumps(intent, ensure_ascii=False)); st.add('ledger', s)
        need(time.time() - f['at'] < 180 and f['epoch'] == self.epoch, 'frame expired/stale before dispatch')
        s = time.time(); live = wxio.observe(); st.add('window', s)       # full audit at the send boundary
        need(live['active'] == panel['id'] and live['main']['geom'] == g
             and len(live['wechat']) == 2, 'context changed before dispatch')
        s = time.time(); ledger.put(op_key, 'DISPATCHING', result=dict(at=time.time())); st.add('ledger', s)
        send_pt = abspt(pg, P_SEND_CLICK)
        try:
            self.epoch += 1
            self.j.event(kind='input', stage='dispatch', label='SEND', point=send_pt, op_key=op_key, epoch=self.epoch)
            s = time.time(); self.x.click(*send_pt); st.add('input', s)
        except BaseException as e:
            ledger.put(op_key, 'UNKNOWN', result=dict(error=repr(e)))
            self.j.event(kind='send_unknown', error=repr(e))
            raise
        s = time.time(); ledger.put(op_key, 'SEND_CLICKED', result=dict(at=time.time(), mode=MODE)); st.add('ledger', s)
        self.j.event(kind='send_clicked', op_key=op_key)
        self.t_send_clicked = time.time() - T0
        self.finish_stage(st)

        st = Stage('panel_exit')
        try:
            f, _ = self.poll(st, 'exit', main_active)
            self.sink.put('07_after_send_debug.png', f['im'])
            self.finish_stage(st)
        except Stop as e:
            self.j.event(kind='UI_STALLED', reason=str(e))   # SEND_CLICKED stands; never re-press
            self.finish_stage(st, ui_stalled=True)
        return self.finish('send_clicked', T0, intent)

    def finish(self, outcome, T0, intent):
        out = dict(outcome=outcome, mode=MODE, total_ms=round((time.time() - T0) * 1000, 1),
                   to_send_clicked_ms=round(getattr(self, 't_send_clicked', 0) * 1000, 1) or None,
                   ocr_calls=self.ocr_calls, stages=self.stages, debug_frames_dropped=self.sink.dropped,
                   batch='incomplete (one contact; tail UNKNOWN)', intent=intent, evidence=str(self.dir))
        self.j.event(kind='finish', **{k: v for k, v in out.items() if k != 'stages'})
        self.sink.close(); self.j.close()
        (self.dir / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return out


if __name__ == '__main__':
    need(len(sys.argv) >= 2 and sys.argv[1] == 'live', 'usage: live --after NAME --send|--no-send')
    after = sys.argv[sys.argv.index('--after') + 1]
    send = '--send' in sys.argv
    need(send or '--no-send' in sys.argv, 'specify --send or --no-send')
    eng = FastEngine(send, after)
    try:
        r = eng.run()
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    except Stop as e:
        eng.j.event(kind='stop', reason=str(e), stages=eng.stages)
        eng.sink.close(); eng.j.close()
        print('STOP:', e)
        sys.exit(2)
