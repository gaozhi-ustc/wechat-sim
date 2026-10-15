"""ocr_mvp_v1: single-contact native-favorite flow driven by OCR + OpenCV rules.

Policy (wechat_ocr_mvp_plan.md section 3):
    content_mode=current_first_native_favorite, runtime_llm_calls=0, max_contacts=1,
    require_top_for_ordered_scope=true, require_tail_before_first_send=false,
    success_level=send_clicked, post_send_proof=false, observation_retries_per_state=3,
    send_dispatches_per_logical_operation=1

Usage:
    python3 -I ocr_mvp_v1.py replay            # offline replay on real P0 frames
    python3 -I ocr_mvp_v1.py live --no-send    # navigate to SELECTED then Cancel
    python3 -I ocr_mvp_v1.py live --send       # P1: one real send_clicked
"""
import fcntl
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wxio  # noqa: E402
from wxio import Stop, need, ocr, center  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402

POLICY = dict(policy_version='ocr_mvp_v1', content_mode='current_first_native_favorite',
              runtime_llm_calls=0, max_contacts=1, require_top_for_ordered_scope=True,
              require_full_roster_before_first_send=False, require_tail_before_first_send=False,
              success_level='send_clicked', post_send_proof=False, auxiliary_label_ocr='advisory_once',
              observation_retries_per_state=3, send_dispatches_per_logical_operation=1,
              capture_max_age_s=180)
# Per-host overrides (defaults = zcx-la original values).
REQUEST_ID = os.environ.get('WX_REQUEST_ID', 'ocr_mvp_v1_first_real_flow_20261014')
ACCOUNT = os.environ.get('WX_ACCOUNT', 'gaozhi-xinshu')
SELF_NAMES = set(filter(None, os.environ.get('WX_SELF_NAMES', '实事求是,gaozhi-xinshu').split(','))) | {ACCOUNT}
SYSTEM_NAMES = {'File Transfer', 'Weixin Team', '文件传输助手', '微信团队', 'Official Accounts'}
MAIN_SIZE = (1088, 770)        # calibrated window configuration (fixed, not auto-adapted)
PANEL_SIZE = (770, 610)
PROD_LOCK = os.environ.get('WX_LOCK', '/home/gaozhi/fav_forward_20261010/upgrade_20261010T1529/controller.lock')
LEDGER = Path(os.environ.get('WX_LEDGER', str(HERE / 'ledger_ocr_mvp_v1.sqlite3')))

# Window-relative calibrated points/ROIs (main window 1088x770, light theme, 100% scale).
W_ACTIVATE = (600, 16)
W_AVATAR = (31, 62)
W_CONTACTS_TAB = (31, 162)
W_LIST = (61, 33, 240, 737)
W_PROFILE = (312, 33, 776, 737)
W_CHAT_TITLE = (301, 33, 600, 48)
W_COMPOSER = (320, 640, 640, 75)
W_TOOLBAR = (305, 718, 230, 42)
W_CHAT_SEND = (1028, 733)
# Panel-relative (770x610 window incl. ~25px shadow margin).
P_HEADER = (200, 30, 540, 40)
P_ALLFAV = (40, 80)
P_SEARCH = (30, 30, 155, 40)
P_RADIOS = (212, 70, 44, 440)
P_SEND = (630, 540)
P_SEND_CLICK = (665, 550)
P_FIRST_RADIO_Y = 135

GREEN_ROW = (21, 172, 112)
GREEN_BTN = (0, 195, 117)
GRAY_BTN = (237, 237, 237)
TPL = {k: cv2.imread(str(HERE / 'templates' / (k + '.png'))) for k in ('cube', 'radio_empty', 'radio_checked')}


class Unknown(Exception):
    """Recoverable observation failure: re-observe, never re-click."""


def close(px, ref, tol=18):
    return all(abs(int(a) - int(b)) <= tol for a, b in zip(px[:3], ref))


def norm(s):
    return re.sub(r'[\s"“”\'‘’()（）<>《》:：,，.。>V]+', '', s or '')


def absbox(g, r):
    return [g['x'] + r[0], g['y'] + r[1], r[2], r[3]]


def abspt(g, p):
    return g['x'] + p[0], g['y'] + p[1]


def match_all(image, roi, tpl, thresh):
    x, y, w, h = roi
    hay = np.asarray(image.crop((x, y, x + w, y + h)))[:, :, ::-1].copy()
    res = cv2.matchTemplate(hay, tpl, cv2.TM_CCOEFF_NORMED)
    th, tw = tpl.shape[:2]
    peaks = []
    r = res.copy()
    while True:
        _, mx, _, loc = cv2.minMaxLoc(r)
        if mx < thresh:
            break
        peaks.append((float(mx), x + loc[0] + tw // 2, y + loc[1] + th // 2))
        cv2.rectangle(r, (loc[0] - tw, loc[1] - th), (loc[0] + tw, loc[1] + th), -1, -1)
    return peaks


# ---------------------------------------------------------------- perception (pure)

def perceive_account(image, popup):
    texts = ocr(image, [popup['x'], popup['y'], popup['w'], popup['h']])
    ids = [re.sub(r'\s+', '', t[0]).split(':', 1)[1] for t in texts
           if re.sub(r'\s+', '', t[0]).lower().startswith('weixinid:')]
    if len(ids) != 1:
        raise Unknown('account id not uniquely read: %r' % [t[0] for t in texts])
    return dict(weixin_id=ids[0], texts=[t[0] for t in texts])


def perceive_contacts(image, g):
    texts = ocr(image, absbox(g, W_LIST))
    texts.sort(key=lambda t: t[2][1])
    find = lambda pat: [t for t in texts if re.search(pat, re.sub(r'\s+', '', t[0]))]
    search, manage = find(r'^\W?Q?Search$'), find(r'ManageContacts$')
    official, header = find(r'OfficialAccounts'), find(r'^\W?V?Contacts$')
    if not (search and manage and header):
        raise Unknown('contacts pane markers missing: %r' % [t[0] for t in texts])
    hy = header[0][2][1] + header[0][2][3]
    # Top proof: Search then Manage Contacts are the first two items, nothing hidden above;
    # between Manage Contacts and the Contacts header only the collapsed Official Accounts header.
    top = (search[0] is texts[0] and manage[0] is texts[1]
           and manage[0][2][1] - g['y'] < 120
           and all(t in official or t in header for t in texts[2:texts.index(header[0]) + 1]))
    rows = []
    for t in texts:
        if t[2][1] <= hy:
            continue
        tx = t[2][0] - g['x']
        if tx < 100 and re.fullmatch(r'[A-Z#]', t[0].strip()):
            continue  # letter index
        if tx < 70:
            continue
        cy = t[2][1] + t[2][3] // 2
        band = [g['x'] + 61, cy - 27, 240, 54]
        complete = band[1] >= hy + 4 and band[1] + band[3] <= g['y'] + g['h'] - 2
        rows.append(dict(name=t[0].strip(), score=t[1], text_box=t[2], band=band, complete=complete,
                         center=(g['x'] + 170, cy)))
    return dict(top_proof=top, header_count=[t[0] for t in texts if re.fullmatch(r'\d+', t[0])],
                rows=rows, texts=[t[0] for t in texts])


def row_selected(image, g, band):
    return close(image.getpixel((g['x'] + 70, band[1] + band[3] // 2)), GREEN_ROW, 12)


def perceive_profile(image, g, band):
    texts = ocr(image, absbox(g, W_PROFILE))
    texts.sort(key=lambda t: (t[2][1], t[2][0]))
    ids = [re.sub(r'\s+', '', t[0]).split(':', 1)[1] for t in texts
           if re.sub(r'\s+', '', t[0]).lower().startswith('weixinid:')]
    if len(ids) != 1:
        raise Unknown('profile Weixin ID not unique: %r' % [t[0] for t in texts])
    idbox = next(t for t in texts if re.sub(r'\s+', '', t[0]).lower().startswith('weixinid:'))[2]
    names = [t for t in texts if t[2][1] < idbox[1] and abs(t[2][0] - idbox[0]) < 15]
    msg = [t for t in texts if t[0].strip() in ('Messages', 'Messag', '发消息')]
    voice = [t for t in texts if t[0].strip() == 'Voice']
    video = [t for t in texts if t[0].strip() == 'Video']
    friend = any(t[0].strip() == 'Friend Profile' for t in texts)
    if len(msg) != 1:
        raise Unknown('Messages control not unique: %r' % [t[0] for t in texts])
    return dict(selected=row_selected(image, g, band), name=names[-1][0].strip() if names else '',
                weixin_id=ids[0], friend_profile=friend, messages=center(msg[0][2]),
                calls=bool(voice and video), texts=[t[0] for t in texts])


def perceive_chat(image, g):
    title = ocr(image, absbox(g, W_CHAT_TITLE))
    comp = np.asarray(image.crop(tuple(absbox(g, W_COMPOSER)[:2]) + (
        g['x'] + W_COMPOSER[0] + W_COMPOSER[2], g['y'] + W_COMPOSER[1] + W_COMPOSER[3])))
    nonbg = int((np.abs(comp.astype(int) - 250).max(axis=2) > 12).sum())
    send_px = image.getpixel(abspt(g, W_CHAT_SEND))
    cubes = match_all(image, absbox(g, W_TOOLBAR), TPL['cube'], 0.80)
    if len(cubes) != 1 or cubes[0][0] < 0.92:
        raise Unknown('favorites toolbar icon not unique: %r' % cubes)
    return dict(title=' '.join(t[0] for t in title), composer_nonbg=nonbg,
                composer_empty=nonbg <= 60, send_disabled=close(send_px, GRAY_BTN, 8),
                send_px=send_px, cube=cubes[0][1:], cube_score=cubes[0][0])


def perceive_panel(image, p):
    header = ocr(image, absbox(p, P_HEADER))
    search = ocr(image, absbox(p, P_SEARCH))
    send_px = image.getpixel(abspt(p, P_SEND))
    send = 'enabled' if close(send_px, GREEN_BTN, 25) else 'disabled' if close(send_px, GRAY_BTN, 8) else 'unknown'
    empty = match_all(image, absbox(p, P_RADIOS), TPL['radio_empty'], 0.85)
    checked = match_all(image, absbox(p, P_RADIOS), TPL['radio_checked'], 0.85)
    radios = sorted([dict(y=y, x=x, checked=False, score=s) for s, x, y in empty]
                    + [dict(y=y, x=x, checked=True, score=s) for s, x, y in checked], key=lambda r: r['y'])
    for a, b in zip(radios, radios[1:]):
        if abs(a['y'] - b['y']) < 30:
            raise Unknown('ambiguous radio state at y=%d' % a['y'])
    if not radios:
        raise Unknown('no favorite items visible (loading?)')
    first = radios[0]
    title = ocr(image, [first['x'] + 30, first['y'] - 45, 360, 30])
    return dict(header=' '.join(t[0] for t in header), search_text=' '.join(t[0] for t in search),
                all_favorites=close(image.getpixel(abspt(p, P_ALLFAV)), GREEN_ROW, 12),
                send=send, send_px=send_px, radios=radios,
                first_at_top=abs(first['y'] - (p['y'] + P_FIRST_RADIO_Y)) <= 4,
                first_title=' '.join(t[0] for t in title))


# ---------------------------------------------------------------- ledger

class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS ops(op_key TEXT PRIMARY KEY, request_id TEXT, '
                        'account TEXT, recipient_ref TEXT, state TEXT, intent TEXT, result TEXT, updated REAL)')
        os.chmod(path, 0o600)

    def unresolved(self):
        return self.db.execute("SELECT op_key,state FROM ops WHERE state IN ('PREPARED','DISPATCHING','UNKNOWN')").fetchall()

    def state(self, key):
        r = self.db.execute('SELECT state FROM ops WHERE op_key=?', (key,)).fetchone()
        return r[0] if r else None

    def put(self, key, state, intent=None, result=None, recipient_ref=None):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.state(key) is None:
                self.db.execute('INSERT INTO ops VALUES(?,?,?,?,?,?,?,?)',
                                (key, REQUEST_ID, ACCOUNT, recipient_ref, state,
                                 json.dumps(intent, ensure_ascii=False), None, time.time()))
            else:
                self.db.execute('UPDATE ops SET state=?, result=?, updated=? WHERE op_key=?',
                                (state, json.dumps(result, ensure_ascii=False, default=str), time.time(), key))


# ---------------------------------------------------------------- live engine

class Engine:
    def __init__(self, send):
        self.send = send
        self.run_id = time.strftime('run_%Y%m%dT%H%M%S') + ('_send' if send else '_nosend')
        self.rec = wxio.Recorder(self.run_id)
        self.x = wxio.X()
        self.timing = []
        self.epoch = 0                 # ui_epoch: bumps on every input
        self.chain = {}                # recipient causal chain

    def t(self, phase, start):
        self.timing.append((phase, round(time.time() - start, 3)))

    def observe(self, tag, want_panel=False):
        f = self.rec.capture(tag)
        f['epoch'] = self.epoch
        o = f['owner']
        g = o['main']['geom']
        need((g['w'], g['h']) == MAIN_SIZE, 'main window geometry not calibrated: %r' % g)
        others = [w for w in o['wechat'] if w['id'] != o['main']['id']]
        if want_panel:
            need(len(others) == 1 and others[0]['transient'] == o['main']['id']
                 and (others[0]['geom']['w'], others[0]['geom']['h']) == PANEL_SIZE
                 and o['active'] == others[0]['id'], 'favorites panel window not uniquely owned/active')
            f['panel'] = others[0]
        else:
            need(not others, 'unexpected WeChat transient window: %r' % others)
            need(o['active'] == o['main']['id'], 'WeChat main not active (external focus change?)')
        return f

    def act(self, frame, point, label, window_rect):
        """Single click bound to the frame it was decided on."""
        need(time.time() - frame['at'] < POLICY['capture_max_age_s'], 'frame expired before input')
        need(frame['epoch'] == self.epoch, 'stale ui_epoch')
        live = wxio.observe()
        need(live['active'] == frame['owner']['active'] and live['main']['geom'] == frame['owner']['main']['geom'],
             'live window context changed since frame')
        x, y = point
        rx, ry, rw, rh = window_rect
        need(rx <= x < rx + rw and ry <= y < ry + rh, 'target outside owning window')
        self.epoch += 1
        self.rec.event(kind='input', label=label, point=point, frame=frame['id'], epoch=self.epoch)
        self.x.click(x, y)

    def perceive(self, tag, fn, want_panel=False, check=None, wait=1.0):
        last = None
        for attempt in range(POLICY['observation_retries_per_state']):
            time.sleep(wait if attempt == 0 else 1.0)
            s = time.time()
            f = self.observe(tag + ('' if attempt == 0 else '_r%d' % attempt), want_panel)
            try:
                v = fn(f)
                if check:
                    check(v)
                self.t('perceive:' + tag, s)
                self.rec.event(kind='observation', tag=tag, frame=f['id'],
                               value={k: v[k] for k in v if k != 'texts'})
                return f, v
            except Unknown as e:
                last = str(e)
                self.rec.event(kind='unknown', tag=tag, frame=f['id'], reason=last)
        raise Stop('needs_review after %d observations at %s: %s' % (POLICY['observation_retries_per_state'], tag, last))

    def run(self):
        T0 = time.time()
        lockfd = os.open(PROD_LOCK, os.O_RDWR)
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('production controller lock busy; unique controller not available')
        ledger = Ledger(LEDGER)
        need(not ledger.unresolved(), 'ledger has unresolved operations: %r' % ledger.unresolved())
        self.rec.event(kind='start', policy=POLICY, request=REQUEST_ID, send=self.send)
        s = time.time(); wxio.ocr_engine(); self.t('init:ocr_model', s)

        # READY: activate, verify account.
        o = wxio.observe()
        g = o['main']['geom']
        need((g['w'], g['h']) == MAIN_SIZE, 'main geometry not calibrated')
        if not o['active_is_wechat'] or o['active'] != o['main']['id']:
            need(len(o['wechat']) == 1, 'unexpected WeChat transient at start')
            self.epoch += 1
            self.rec.event(kind='input', label='activate', point=abspt(g, W_ACTIVATE), epoch=self.epoch)
            self.x.click(*abspt(g, W_ACTIVATE))
        f = self.perceive('ready', lambda f: {}, wait=0.8)[0]
        self.act(f, abspt(g, W_AVATAR), 'avatar', [g['x'], g['y'], g['w'], g['h']])

        def account(f):
            pops = [w for w in f['owner']['wechat'] if w['id'] != f['owner']['main']['id']]
            if len(pops) != 1 or pops[0]['type'] != '_NET_WM_WINDOW_TYPE_UTILITY,':
                raise Unknown('self profile popup not unique')
            return perceive_account(f['image'], pops[0]['geom'])
        time.sleep(1.0)
        s = time.time()
        f = self.rec.capture('account'); v = None
        try:
            v = account(f)
        finally:
            self.epoch += 1
            self.x.key('Escape')   # dismiss popup regardless
        self.t('perceive:account', s)
        self.rec.event(kind='observation', tag='account', value=v)
        need(v['weixin_id'] == ACCOUNT, 'wrong account: %r' % v['weixin_id'])

        # CONTACTS
        f = self.perceive('ready2', lambda f: {}, wait=0.8)[0]
        self.act(f, abspt(g, W_CONTACTS_TAB), 'contacts-tab', [g['x'], g['y'], g['w'], g['h']])
        f, c = self.perceive('contacts', lambda f: perceive_contacts(f['image'], f['owner']['main']['geom']),
                             check=lambda c: None if c['top_proof'] and c['rows'] else (_ for _ in ()).throw(Unknown('no top proof/rows')))
        target = None
        for r in c['rows']:
            if r['name'] in SELF_NAMES or r['name'] in SYSTEM_NAMES:
                self.rec.event(kind='excluded', name=r['name'], reason='self/system')
                continue
            need(r['complete'], 'first candidate row is partial; would need scroll (not in P1)')
            target = r
            break
        need(target is not None, 'no ordinary candidate in first viewport')
        self.chain = dict(row_frame=f['id'], row_name_ocr=target['name'], row_band=target['band'], ordinal=c['rows'].index(target))
        self.act(f, target['center'], 'contact-row', [g['x'], g['y'], g['w'], g['h']])

        # PROFILE
        def prof_check(p):
            if not p['selected']:
                raise Unknown('clicked row not shown selected')
        f, p = self.perceive('profile', lambda f: perceive_profile(f['image'], g, target['band']), check=prof_check)
        need(p['weixin_id'] != ACCOUNT and p['name'] not in SELF_NAMES, 'profile is self')
        need(p['friend_profile'] and p['calls'], 'profile is not a clearly ordinary friend')
        need(norm(p['name']) == norm(target['name']) and norm(p['name']),
             'row/profile association mismatch: %r vs %r' % (target['name'], p['name']))
        self.chain.update(profile_frame=f['id'], profile_name=p['name'], weixin_id=p['weixin_id'])
        op_key = '%s|%s|wxid:%s' % (REQUEST_ID, ACCOUNT, p['weixin_id'])
        st = ledger.state(op_key)
        need(st is None, 'logical operation already exists in ledger (%s); no re-dispatch' % st)
        self.act(f, p['messages'], 'profile-messages', [g['x'], g['y'], g['w'], g['h']])

        # CHAT
        def chat_check(ch):
            if norm(p['name']) not in norm(ch['title']):
                raise Unknown('chat title %r does not match profile %r' % (ch['title'], p['name']))
        f, ch = self.perceive('chat', lambda f: perceive_chat(f['image'], g), check=chat_check, wait=1.5)
        need(ch['composer_empty'], 'composer has unexplained content (draft?)')
        need(ch['send_disabled'], 'chat Send not in disabled state')
        self.chain.update(chat_frame=f['id'], chat_title=ch['title'])
        self.act(f, ch['cube'], 'favorites-entry', [g['x'], g['y'], g['w'], g['h']])

        # FAVORITES (zero-select baseline)
        def base_check(v):
            if v['send'] != 'disabled' or any(r['checked'] for r in v['radios']):
                raise Unknown('panel not at zero-select baseline: send=%s' % v['send'])
        f, pv = self.perceive('favorites', lambda f: perceive_panel(f['image'], f['panel']['geom']),
                              want_panel=True, check=base_check, wait=1.5)
        panel = f['panel']
        need(norm(p['name']) in norm(pv['header']) and norm(pv['header']).startswith('Sendfavoritesto'),
             'panel header not bound to recipient: %r' % pv['header'])
        need(pv['all_favorites'] and 'SearchFavorites' in norm(pv['search_text']), 'panel filter/search not default')
        need(pv['first_at_top'], 'first favorite not at calibrated top position')
        self.chain.update(panel_frame=f['id'], panel_id=panel['id'], panel_header=pv['header'])
        first = pv['radios'][0]
        pg = panel['geom']
        self.act(f, (first['x'], first['y']), 'select-first', [pg['x'], pg['y'], pg['w'], pg['h']])

        # SELECTED
        def sel_check(v):
            if v['send'] != 'enabled' or [r['checked'] for r in v['radios']] != [True] + [False] * (len(v['radios']) - 1):
                raise Unknown('not exactly first selected: send=%s radios=%r' % (v['send'], [r['checked'] for r in v['radios']]))
        f, sv = self.perceive('selected', lambda f: perceive_panel(f['image'], f['panel']['geom']),
                              want_panel=True, check=sel_check, wait=0.8)
        need(f['panel']['id'] == panel['id'] and f['panel']['geom'] == pg, 'panel identity changed')
        need(norm(p['name']) in norm(sv['header']), 'panel recipient binding lost')
        need(abs(sv['radios'][0]['y'] - first['y']) <= 2, 'list moved after selection')
        send_pt = abspt(pg, P_SEND_CLICK)

        intent = dict(request=REQUEST_ID, account=ACCOUNT, chain=self.chain, favorite_title_ocr=sv['first_title'],
                      decision_frame=f['path'], send_point=send_pt, policy=POLICY['policy_version'])
        if not self.send:
            self.rec.event(kind='dry_run_ready', intent=intent)
            self.act(f, abspt(pg, (520, 550)), 'cancel', [pg['x'], pg['y'], pg['w'], pg['h']])
            time.sleep(1.0)
            self.rec.capture('after_cancel')
            return self.finish('dry_run_prepared_no_send', T0, intent)

        # DISPATCH: durable intent first, then exactly one Send.
        ledger.put(op_key, 'PREPARED', intent=intent, recipient_ref=json.dumps(self.chain, ensure_ascii=False))
        need(time.time() - f['at'] < POLICY['capture_max_age_s'], 'frame expired before dispatch')
        live = wxio.observe()
        need(live['active'] == panel['id'] and live['main']['geom'] == g, 'context changed before dispatch')
        ledger.put(op_key, 'DISPATCHING', result=dict(at=time.time()))
        try:
            s = time.time()
            self.epoch += 1
            self.rec.event(kind='input', label='SEND', point=send_pt, frame=f['id'], epoch=self.epoch, op_key=op_key)
            self.x.click(*send_pt)
            self.t('input:send', s)
        except BaseException as e:
            ledger.put(op_key, 'UNKNOWN', result=dict(error=repr(e)))
            self.rec.event(kind='send_unknown', error=repr(e))
            raise
        ledger.put(op_key, 'SEND_CLICKED', result=dict(at=time.time(), frame=f['id']))
        self.rec.event(kind='send_clicked', op_key=op_key)
        time.sleep(1.5)
        self.rec.capture('after_send_evidence_only')
        return self.finish('send_clicked', T0, intent)

    def finish(self, outcome, T0, intent):
        out = dict(outcome=outcome, total_s=round(time.time() - T0, 3), timing=self.timing,
                   batch='incomplete (max_contacts=1 reached; tail UNKNOWN)', intent=intent,
                   evidence=str(self.rec.dir))
        self.rec.event(kind='finish', **out)
        (self.rec.dir / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return out


# ---------------------------------------------------------------- offline replay

def replay():
    from PIL import Image
    E = HERE / 'evidence' / 'p0_explore'
    G = dict(x=11, y=45, w=1088, h=770)
    P = dict(x=169, y=124, w=770, h=610)
    im = lambda n: Image.open(next(E.glob('%02d_*.png' % n))).convert('RGB')
    res = {}
    a = perceive_account(im(2), dict(x=44, y=66, w=328, h=330)); res['account'] = a['weixin_id'] == ACCOUNT
    c = perceive_contacts(im(3), G)
    r0 = c['rows'][0]
    res['contacts_top'] = c['top_proof']; res['first_row'] = (r0['name'], r0['complete'])
    p = perceive_profile(im(4), G, r0['band'])
    res['profile'] = (p['selected'], p['name'], p['weixin_id'], p['friend_profile'], p['calls'])
    # Negative: unselected row band must not read as selected.
    res['neg_unselected_row'] = not row_selected(im(4), G, c['rows'][1]['band'])
    ch = perceive_chat(im(5), G)
    res['chat'] = (ch['title'], ch['composer_empty'], ch['send_disabled'], ch['cube'], round(ch['cube_score'], 3))
    pv = perceive_panel(im(6), P)
    res['panel_baseline'] = (pv['header'], pv['all_favorites'], pv['send'], [r['checked'] for r in pv['radios']], pv['first_at_top'], pv['first_title'])
    sv = perceive_panel(im(8), P)
    res['panel_selected'] = (sv['send'], [r['checked'] for r in sv['radios']])
    hv = perceive_panel(im(7), P)  # hover variant
    res['panel_selected_hover'] = (hv['send'], [r['checked'] for r in hv['radios']])
    # Negatives: wrong-window crops must not yield the controls.
    for name, fn in (('neg_chat_on_contacts', lambda: perceive_chat(im(3), G)),
                     ('neg_panel_on_chat', lambda: perceive_panel(im(5), P)),
                     ('neg_profile_on_chat', lambda: perceive_profile(im(5), G, r0['band']))):
        try:
            fn(); res[name] = False
        except Unknown as e:
            res[name] = 'rejected: ' + str(e)[:80]
    for k, v in res.items():
        print(k, '=>', v)
    return res


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'replay'
    if mode == 'replay':
        replay()
    elif mode == 'live':
        send = '--send' in sys.argv
        need(send or '--no-send' in sys.argv, 'specify --send or --no-send')
        eng = Engine(send)
        try:
            print(json.dumps(eng.run(), ensure_ascii=False, indent=1, default=str))
        except Stop as e:
            eng.rec.event(kind='stop', reason=str(e), timing=eng.timing)
            print('STOP:', e)
            sys.exit(2)
