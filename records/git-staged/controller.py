#!/usr/bin/env python3
"""Externally reviewed WeChat inventory. NOT autonomous vision. SEND IS DISABLED."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import struct
import subprocess
import sys
import time
import uuid
from urllib.parse import parse_qs, urlencode, urlsplit

TITLE = '分治法 vs 端到端？ Attention is All You Need!'
SOURCE = '高志创业笔记'
ROOTS = {'/tmp/wxview92/upgrade_20261010T1529',
         '/home/gaozhi/fav_forward_20261010/upgrade_20261010T1529'}
TABLES = ('meta', 'evidence', 'pages', 'contacts', 'events', 'ledger', 'legacy')
MAX_AGE = 180


class Error(Exception):
    pass


def need(ok, message):
    if not ok:
        raise Error(message)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def reviewed(d):
    need(isinstance(d.get('reviewer'), str) and d['reviewer'].strip(), 'reviewer required')


def article_key(url):
    if not isinstance(url, str) or not url:
        return None
    try:
        u = urlsplit(url)
        if (u.scheme not in ('http', 'https') or u.netloc != 'mp.weixin.qq.com'
                or u.path != '/s'):
            return None
        q = parse_qs(u.query, keep_blank_values=True)
        keys = ('__biz', 'mid', 'idx', 'sn')
        if not all(len(q.get(k, [])) == 1 and q[k][0].strip() for k in keys):
            return None
        if not q['mid'][0].isdigit() or not q['idx'][0].isdigit():
            return None
        return 'https://mp.weixin.qq.com/s?' + urlencode([(k, q[k][0]) for k in keys])
    except ValueError:
        return None


def rectangle(r):
    need(isinstance(r, list) and len(r) == 4 and all(type(x) is int for x in r), 'invalid rectangle')
    need(r[2] > 0 and r[3] > 0, 'empty rectangle')
    return r


def inside(inner, outer):
    a, b, w, h = rectangle(inner)
    x, y, width, height = rectangle(outer)
    return x <= a and y <= b and a+w <= x+width and b+h <= y+height


def rect(g):
    return [g['x'], g['y'], g['w'], g['h']]


@contextlib.contextmanager
def process_guard(root):
    fd = os.open(str(Path(root) / 'controller.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Error('controller process lock busy; no retry')
        yield
    finally:
        os.close(fd)


@contextlib.contextmanager
def legacy_guard(path):
    lock = Path(str(path) + '.lock')
    need(lock.is_file() and not lock.is_symlink(), 'old state lock missing/unsafe; stop, do not create it')
    fd = os.open(str(lock), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Error('old controller lock busy; no takeover')
        need(os.fstat(fd).st_ino == lock.stat().st_ino, 'old lock inode changed')
        yield
    finally:
        os.close(fd)


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.db = sqlite3.connect(str(self.root / 'ledger.sqlite3'), timeout=0)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pages(id INTEGER PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS contacts(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS legacy(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ledger(
                friend_id TEXT NOT NULL, article_key TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','submitting','confirmed','uncertain')),
                data TEXT NOT NULL, PRIMARY KEY(friend_id,article_key));
        ''')

    def get(self, key, default=None):
        row = self.db.execute('SELECT v FROM meta WHERE k=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, dumps(value)))

    def put(self, table, key, value):
        need(table in TABLES and table not in ('meta', 'ledger'), 'invalid table')
        self.db.execute('INSERT OR REPLACE INTO '+table+' VALUES(?,?)', (key, dumps(value)))

    def list(self, table):
        need(table in TABLES, 'invalid table')
        if table == 'meta':
            return {r['k']: json.loads(r['v']) for r in self.db.execute('SELECT * FROM meta')
                    if r['k'] != 'lease'}
        if table == 'ledger':
            return [dict(r) for r in self.db.execute('SELECT * FROM ledger ORDER BY friend_id,article_key')]
        return [json.loads(r['data']) for r in self.db.execute('SELECT * FROM '+table+' ORDER BY rowid')]

    def item(self, table, key):
        need(table in TABLES and table not in ('meta', 'ledger'), 'invalid table')
        row = self.db.execute('SELECT data FROM '+table+' WHERE id=?', (key,)).fetchone()
        need(row is not None, 'unknown '+table+' ID: '+str(key))
        return json.loads(row[0])

    def initialize(self, old):
        old = Path(old).resolve()
        state = json.loads(old.read_text())
        recipients = state.get('recipients', [])
        need(state.get('version') == 1 and state.get('phase') == 'complete', 'old state must be complete v1')
        need(state.get('title') == TITLE and state.get('source') == SOURCE, 'legacy article mismatch')
        need([r.get('identity') for r in recipients] == ['assfox', 'File Transfer', 'cherry-pku']
             and all(r.get('status') == 'confirmed' for r in recipients), 'legacy recipients mismatch')
        old_hash = digest(old)
        if self.get('legacy_path'):
            need(self.get('legacy_path') == str(old) and self.get('legacy_hash') == old_hash,
                 'already bound to a different legacy state')
            return {'initialized': True, 'unchanged': True}
        with self.db:
            self.set('legacy_path', str(old))
            self.set('legacy_hash', old_hash)
            self.set('legacy_snapshot', state)
            self.set('article', {'status': 'pending', 'article_key': None})
            for r in recipients:
                self.put('legacy', r['identity'], {'id': r['identity'], 'record': r,
                    'status': 'special' if r['identity'] == 'File Transfer' else 'unmapped',
                    'article_key': None})
        return {'initialized': True, 'history_unmapped': ['assfox', 'cherry-pku']}

    def check_legacy(self):
        need(self.get('legacy_path'), 'init required')
        need(digest(self.get('legacy_path')) == self.get('legacy_hash'), 'old state changed; stop')

    def claim(self, owner):
        need(isinstance(owner, str) and owner.strip(), 'owner required')
        token = secrets.token_urlsafe(32)
        with self.db:
            need(not self.get('lease'), 'persistent lease occupied; no expiry takeover')
            self.set('lease', {'owner': owner, 'hash': hashlib.sha256(token.encode()).hexdigest(),
                               'created': time.time()})
        return token

    def authorize(self, token):
        lease = self.get('lease')
        need(lease and isinstance(token, str) and secrets.compare_digest(
            lease['hash'], hashlib.sha256(token.encode()).hexdigest()), 'lease token required/mismatch')

    def release(self, token):
        self.authorize(token)
        with self.db:
            self.set('lease', None)
        return {'released': True}

    def add_evidence(self, d):
        reviewed(d)
        need(d.get('main_window') is True and d.get('geometry_source') == 'xwininfo', 'main window geometry review required')
        p = Path(d['path']).resolve()
        need(self.root in p.parents and p.is_file(), 'evidence must be inside upgrade directory')
        need(digest(p) == d['sha256'], 'evidence hash mismatch')
        raw = p.read_bytes()[:24]
        need(len(raw) == 24 and raw[:8] == b'\x89PNG\r\n\x1a\n' and raw[12:16] == b'IHDR', 'PNG required')
        g = d['geometry']
        rectangle(rect(g))
        need(g['x'] >= 0 and g['y'] >= 0 and str(g['id']).isdigit(), 'unsupported root geometry')
        need(struct.unpack('>II', raw[16:24]) == (g['w'], g['h']), 'PNG dimensions/geometry mismatch')
        need(isinstance(d['captured_at'], (int, float)) and 0 < d['captured_at'] <= time.time(), 'invalid evidence time')
        e = dict(d, id=uuid.uuid4().hex, path=str(p))
        with self.db:
            self.put('evidence', e['id'], e)
            self.set('latest', e['id'])
        return e

    def evidence(self, eid, fresh=False):
        e = self.item('evidence', eid)
        need(digest(e['path']) == e['sha256'], 'evidence file changed')
        if fresh:
            need(eid == self.get('latest') and 0 <= time.time()-e['captured_at'] < MAX_AGE,
                 'latest evidence under 180 seconds required')
        return e

    def event(self, data):
        e = dict(data, id=uuid.uuid4().hex, recorded_at=time.time())
        with self.db:
            self.put('events', e['id'], e)
        return e

    def record_scroll(self, d):
        reviewed(d)
        before, after = self.evidence(d['before']), self.evidence(d['after'])
        page = self.item('pages', d['from_page'])
        need(page['evidence'] == before['id'] and d['before'] != d['after'], 'scroll source page mismatch')
        need(before['captured_at'] < after['captured_at'] and before['geometry'] == after['geometry'], 'scroll geometry/time mismatch')
        need(d.get('direction') == 'down' and d.get('notches') == 1 and d.get('actual_input') is True
             and d.get('list_focused') is True, 'one actual reviewed list down-scroll required')
        need(d.get('pane') == page['pane'], 'scroll pane mismatch')
        return self.event(dict(d, kind='scroll', origin=d.get('origin', 'external-review')))

    def record_page(self, d):
        reviewed(d)
        need(not self.get('end_proof'), 'coverage sealed; no more pages')
        e = self.evidence(d['evidence'])
        need(d.get('all_visible_rows') is True and inside(d['pane'], rect(e['geometry'])), 'middle pane/all rows review required')
        rows = d['rows']
        need(isinstance(rows, list) and rows, 'nonempty visible rows required')
        ids = [r['oid'] for r in rows]
        need(all(isinstance(x, str) and x.strip() for x in ids) and len(set(ids)) == len(ids), 'unique opaque row occurrence IDs required')
        for i, row in enumerate(rows):
            need(isinstance(row['label'], str) and row['label'].strip() and inside(row['box'], d['pane']), 'invalid row label/box')
            if i:
                need(rows[i-1]['box'][1] + rows[i-1]['box'][3] <= row['box'][1], 'rows must be ordered and nonoverlapping')
        pages = self.list('pages')
        overlap = 0
        if not pages:
            need(d.get('at_top') is True and d.get('top_visible') is True, 'visually proven top required')
        else:
            prev = pages[-1]
            scroll = self.item('events', d.get('scroll', ''))
            need(scroll.get('kind') == 'scroll' and scroll['from_page'] == prev['id']
                 and scroll['before'] == prev['evidence'] and scroll['after'] == d['evidence'], 'continuous scroll edge required')
            need(d['pane'] == prev['pane'], 'list pane changed; cannot claim continuity')
            old = [r['oid'] for r in prev['rows']]
            minimum = 2 if min(len(old), len(ids)) >= 3 else 1
            overlap = max([k for k in range(1, min(len(old), len(ids))+1) if old[-k:] == ids[:k]] or [0])
            need(overlap >= minimum, 'missing sufficient suffix/prefix overlap')
        known = {r['oid']: r['label'] for p in pages for r in p['rows']}
        need(all(oid not in known for oid in ids[overlap:]), 'reused row ID outside overlap')
        need(all(r['oid'] not in known or known[r['oid']] == r['label'] for r in rows), 'reused row ID label changed')
        p = dict(d, id=len(pages)+1)
        with self.db:
            self.put('pages', p['id'], p)
        return p

    def record_contact(self, d):
        reviewed(d)
        self.evidence(d['evidence'])
        need(d.get('same_row') is True, 'profile-to-row visual association required')
        rows = {r['oid'] for p in self.list('pages') for r in p['rows']}
        need(d['oid'] in rows, 'unknown row occurrence')
        kind, status = d.get('kind'), d.get('status')
        if kind == 'friend' and status == 'identified':
            need(d.get('field') == 'WeChat ID' and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{2,63}', d.get('friend_id', '')),
                 'exact profile WeChat ID required, not nickname')
            need(d['friend_id'] != 'File Transfer', 'special entry cannot be friend')
        else:
            need((kind, status) in (('friend', 'pending'), ('special', 'skipped')) and d.get('reason'),
                 'no-ID/special entries need explicit pending/skipped reason')
            need(not d.get('friend_id'), 'unresolved entry cannot carry guessed ID')
        previous = next((r for r in self.list('contacts') if r['id'] == d['oid']), None)
        if previous and previous['status'] == 'identified':
            need(d.get('friend_id') == previous['friend_id'] and status == 'identified', 'identified row cannot change identity')
        row = dict(d, id=d['oid'])
        with self.db:
            self.put('contacts', row['id'], row)
        return row

    def record_end(self, d):
        reviewed(d)
        need(d.get('bottom_visible') is True and d.get('no_progress') is True, 'bottom/no-progress visual review required')
        pages = self.list('pages')
        need(len(pages) >= 3, 'two additional actual tail scrolls required')
        tail = pages[-3:]
        lists = [[r['oid'] for r in p['rows']] for p in tail]
        need(lists[0] == lists[1] == lists[2] and len({p['evidence'] for p in tail}) == 3, 'tail requires three separate unchanged-list captures')
        tail_evidence = [self.evidence(p['evidence']) for p in tail]
        need(len({e['path'] for e in tail_evidence}) == 3,
             'tail requires three distinct capture files, not one re-registered image')
        for p in pages:
            self.evidence(p['evidence'])
        for previous, current in zip(tail, tail[1:]):
            event = self.item('events', current['scroll'])
            need(event['kind'] == 'scroll' and event['from_page'] == previous['id'], 'tail scroll proof missing')
        proof = dict(d, pages=[p['id'] for p in tail], evidence=[p['evidence'] for p in tail])
        with self.db:
            self.set('end_proof', proof)
        return proof

    def record_article(self, d):
        reviewed(d)
        self.evidence(d['evidence'])
        need(d.get('title') == TITLE and d.get('source') == SOURCE and d.get('first_favorite') is True
             and d.get('exactly_one') is True, 'fixed first favorite review required')
        key = article_key(d.get('url'))
        if key:
            need(d.get('url_observed') is True and d.get('association_note'), 'actual URL association review required')
        current = self.get('article', {})
        need(not current.get('article_key') or current['article_key'] == key, 'cannot switch a verified article in this run')
        value = dict(d, article_key=key, status='verified' if key else 'pending')
        with self.db:
            self.set('article', value)
        return value

    def map_legacy(self, d):
        reviewed(d)
        self.evidence(d['evidence'])
        need(d['friend_id'] in ('assfox', 'cherry-pku'), 'only real legacy friends may map')
        legacy = self.item('legacy', d['friend_id'])
        key = article_key(d.get('url'))
        need(key and key == self.get('article', {}).get('article_key'), 'reliable matching article key required')
        need(d.get('same_original_card') is True and d.get('url_observed') is True and d.get('association_note'),
             'historically sent original-card URL review required, title is insufficient')
        old_hash = legacy['record']['confirmation']['evidence']['sha256']
        need(d.get('legacy_confirmation_sha256') == old_hash, 'legacy confirmation evidence mismatch')
        need(legacy['status'] in ('unmapped', 'mapped') and legacy.get('article_key') in (None, key), 'mapping conflict')
        with self.db:
            pair = self.db.execute('SELECT status FROM ledger WHERE friend_id=? AND article_key=?',
                                   (d['friend_id'], key)).fetchone()
            need(not pair or pair[0] == 'confirmed', 'existing nonconfirmed pair requires reconciliation; do not overwrite')
            self.db.execute('INSERT OR IGNORE INTO ledger VALUES(?,?,?,?)',
                (d['friend_id'], key, 'confirmed', dumps({'origin': 'legacy', 'mapping': d, 'legacy': legacy['record']})))
            self.put('legacy', d['friend_id'], dict(legacy, status='mapped', article_key=key, mapping=d))
        return {'friend_id': d['friend_id'], 'status': 'confirmed', 'article_key': key}

    def dry_run(self):
        article = self.get('article', {'status': 'pending', 'article_key': None})
        key = article.get('article_key')
        if article.get('evidence'):
            self.evidence(article['evidence'])
        pages = self.list('pages')
        manifest = {}
        for page in pages:
            self.evidence(page['evidence'])
            for row in page['rows']:
                item = manifest.setdefault(row['oid'], {'oid': row['oid'], 'label': row['label'], 'pages': []})
                item['pages'].append(page['id'])
        contacts = {r['id']: r for r in self.list('contacts')}
        legacy = self.list('legacy')
        for record in legacy:
            if record['status'] == 'mapped':
                try:
                    self.evidence(record['mapping']['evidence'])
                except OSError as exc:
                    raise Error('legacy mapping evidence unavailable: '+str(exc)) from exc
        unmapped = {r['id'] for r in legacy if r['status'] == 'unmapped'}
        queue, excluded, seen = [], [], set()
        complete = bool(pages and self.get('end_proof'))
        with self.db:
            for oid, occurrence in manifest.items():
                row = contacts.get(oid)
                if not row or row['status'] != 'identified':
                    excluded.append(dict(occurrence, reason='special_skipped' if row and row['kind'] == 'special' else 'identity_pending',
                                         details=row.get('reason') if row else 'profile WeChat ID not reviewed'))
                    continue
                self.evidence(row['evidence'])
                fid = row['friend_id']
                if fid in seen:
                    excluded.append(dict(occurrence, reason='duplicate_stable_id', friend_id=fid))
                    continue
                seen.add(fid)
                reasons = ['send_disabled']
                if not complete:
                    reasons.append('coverage_incomplete')
                if not key:
                    reasons.append('article_pending')
                if fid in unmapped:
                    reasons.append('legacy_unmapped')
                if key and fid not in unmapped:
                    self.db.execute('INSERT OR IGNORE INTO ledger VALUES(?,?,?,?)',
                                    (fid, key, 'pending', dumps({'origin': 'dry-run'})))
                pair = self.db.execute('SELECT status FROM ledger WHERE friend_id=? AND article_key=?', (fid, key)).fetchone()
                status = pair[0] if pair else None
                if status in ('confirmed', 'submitting', 'uncertain'):
                    reasons.append(status)
                queue.append(dict(occurrence, friend_id=fid, article_key=key, status=status, reasons=reasons))
        return {'send_enabled': False, 'automatic_vision': False, 'article': article,
                'coverage': {'enumeration_complete': complete, 'pages': len(pages),
                             'observations': len(manifest), 'distinct_identified_friends': len(seen),
                             'end_proof': self.get('end_proof'), 'manifest': list(manifest.values())},
                'queue': queue, 'excluded': excluded, 'legacy': legacy}

    def intent(self, fid, key, attestation):
        # Persistence primitive only. No production CLI/desktop path calls this.
        with self.db:
            row = self.db.execute('SELECT status,data FROM ledger WHERE friend_id=? AND article_key=?', (fid, key)).fetchone()
            need(row and row[0] == 'pending', 'only pending can acquire a submission intent; never retry')
            data = json.loads(row[1])
            data['intent'] = {'at': time.time(), 'attestation': attestation}
            changed = self.db.execute("UPDATE ledger SET status='submitting',data=? WHERE friend_id=? AND article_key=? AND status='pending'",
                                      (dumps(data), fid, key)).rowcount
            need(changed == 1, 'intent conflict')

    def transition(self, fid, key, target, evidence):
        # Persistence primitive only. Future adapter must validate semantic evidence.
        need(target in ('uncertain', 'confirmed'), 'no transition back to pending')
        with self.db:
            row = self.db.execute('SELECT status,data FROM ledger WHERE friend_id=? AND article_key=?', (fid, key)).fetchone()
            need(row and row[0] in ('submitting', 'uncertain'), 'reconciliation state required')
            data = json.loads(row[1])
            data.setdefault('reconciliation', []).append({'to': target, 'evidence': evidence, 'at': time.time()})
            self.db.execute('UPDATE ledger SET status=?,data=? WHERE friend_id=? AND article_key=?', (target, dumps(data), fid, key))

    def status(self):
        return {table: self.list(table) for table in TABLES}


def tool(command):
    env = dict(os.environ, DISPLAY=os.environ.get('DISPLAY', ':1'), LC_ALL='C')
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise Error('tool timeout; no retry: '+command[0])
    except BaseException:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
        raise
    need(proc.returncode == 0, 'tool failed; no retry: '+command[0]+' '+err.decode(errors='replace')[-1000:])
    return out


def geometry(wid):
    need(str(wid).isdigit(), 'decimal window ID required')
    text = tool(['xwininfo', '-id', str(wid)]).decode(errors='replace')
    need('Map State: IsViewable' in text, 'window not viewable')
    g = {'id': str(wid)}
    for key, label in (('x', 'Absolute upper-left X'), ('y', 'Absolute upper-left Y'),
                       ('w', 'Width'), ('h', 'Height')):
        m = re.search(r'^\s*'+label+r':\s*(-?\d+)', text, re.M)
        need(m is not None, 'missing window geometry '+key)
        g[key] = int(m.group(1))
    need(g['x'] >= 0 and g['y'] >= 0 and g['w'] > 0 and g['h'] > 0, 'offscreen/invalid window')
    title = re.search(r'Window id:.*?"(.*)"', text)
    g['title'] = title.group(1) if title else ''
    try:
        wm_class = tool(['xprop', '-id', str(wid), 'WM_CLASS']).decode(errors='replace').strip()
    except OSError as exc:
        raise Error('xprop unavailable; cannot validate WM_CLASS: '+str(exc)) from exc
    match = re.fullmatch(r'WM_CLASS\(STRING\) = "([^"\\\r\n]+)", "([^"\\\r\n]+)"', wm_class)
    need(match is not None, 'missing/invalid xprop WM_CLASS')
    g['wm_class'] = match.group(2)
    return g


def windows():
    output = tool(['xdotool', 'search', '--onlyvisible', '--class', '[Ww]e[Cc]hat|[Ww]eixin|微信']).decode()
    ids = list(dict.fromkeys(output.split()))
    return [geometry(wid) for wid in ids]


def capture(store, d):
    reviewed(d)
    need(d.get('main_window') is True, 'external main-window review required')
    candidates = windows()
    if d.get('window_id') is None:
        need(len(candidates) == 1, 'choose reviewed main window_id from candidates')
        g = candidates[0]
    else:
        matches = [x for x in candidates if x['id'] == str(d['window_id'])]
        need(len(matches) == 1, 'selected window is not a detected WeChat candidate')
        g = matches[0]
    started = time.time()
    crop = '%dx%d+%d+%d' % (g['w'], g['h'], g['x'], g['y'])
    png = tool(['import', '-window', 'root', '-crop', crop, '+repage', '-strip', 'png:-'])
    need(geometry(g['id']) == g, 'window moved during capture; discard and re-review')
    path = store.root / ('capture_'+uuid.uuid4().hex+'.png')
    with path.open('xb') as f:
        f.write(png)
        f.flush()
        os.fsync(f.fileno())
    fd = os.open(str(store.root), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return store.add_evidence({'path': str(path), 'sha256': digest(path), 'captured_at': started,
        'geometry': g, 'geometry_source': 'xwininfo', 'reviewer': d['reviewer'], 'main_window': True})


def navigation_guard(store, d):
    e = store.evidence(d['evidence'], fresh=True)
    need(geometry(e['geometry']['id']) == e['geometry'], 'geometry changed; recapture/review')
    active = tool(['xdotool', 'getactivewindow']).decode().strip()
    need(active == e['geometry']['id'], 'reviewed main window is not active')
    return e


def navigate(store, d):
    reviewed(d)
    need(d.get('safe_navigation') is True, 'external safe-navigation review required')
    allowed = {'contacts': {'contacts-tab', 'contact-row', 'scroll-down'}, 'profile': {'profile-close'}}
    need(d.get('action') in allowed.get(d.get('screen'), set()), 'navigation target forbidden; no chat/send/favorites actions')
    e = navigation_guard(store, d)
    need(inside(d['target'], rect(e['geometry'])), 'target outside captured window')
    need(type(d['x']) is int and type(d['y']) is int and inside([d['x'], d['y'], 1, 1], d['target']), 'click outside reviewed target')
    scrolling = d['action'] == 'scroll-down'
    if scrolling:
        page = store.item('pages', d['from_page'])
        need(page['evidence'] == e['id'] and d['target'] == page['pane'], 'scroll must use reviewed current middle pane')
    intent = store.event({'kind': 'navigation', 'status': 'intent', 'request': d})
    try:
        navigation_guard(store, d)
        tool(['xdotool', 'mousemove', '--sync', str(d['x']), str(d['y']), 'click', '5' if scrolling else '1'])
        after = capture(store, {'window_id': e['geometry']['id'], 'reviewer': d['reviewer'], 'main_window': True})
        result = {'kind': 'navigation-result', 'intent': intent['id'], 'status': 'done', 'after': after['id']}
        if scrolling:
            scroll = store.record_scroll({'before': e['id'], 'after': after['id'], 'from_page': d['from_page'],
                'pane': d['target'], 'reviewer': d['reviewer'], 'direction': 'down', 'notches': 1,
                'actual_input': True, 'list_focused': True, 'origin': 'controller', 'navigation_intent': intent['id']})
            result['scroll'] = scroll['id']
        store.event(result)
        return dict(result, capture=after)
    except BaseException as exc:
        store.event({'kind': 'navigation-result', 'intent': intent['id'], 'status': 'uncertain', 'error': str(exc)})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = ('init', 'claim', 'release', 'status', 'windows', 'capture', 'record-evidence', 'navigate',
                'record-scroll', 'record-page', 'record-contact', 'record-end', 'record-article',
                'map-legacy', 'dry-run', 'submit')
    parser.add_argument('command', choices=commands)
    parser.add_argument('--data', default='{}', help='JSON object; see README.md CLI contract')
    parser.add_argument('--token')
    args = parser.parse_args(argv)
    if args.command == 'submit':
        print('ERROR: SEND_DISABLED', file=sys.stderr)
        return 2
    try:
        d = json.loads(args.data)
        need(isinstance(d, dict), '--data must be an object')
        root = Path(__file__).resolve().parent
        need(str(root) in ROOTS, 'controller must run from its one approved upgrade directory')
        os.umask(0o077)
        with process_guard(root):
            store = Store(root)
            try:
                old = Path(d['legacy_state']).resolve() if args.command == 'init' else Path(store.get('legacy_path', '/missing'))
                with legacy_guard(old):
                    if args.command == 'init':
                        result = store.initialize(old)
                    else:
                        store.check_legacy()
                        if args.command == 'claim':
                            result = {'token': store.claim(d.get('owner')), 'send_enabled': False}
                        else:
                            store.authorize(args.token)
                            if args.command == 'release':
                                result = store.release(args.token)
                            elif args.command == 'windows':
                                result = windows()
                            elif args.command == 'capture':
                                result = capture(store, d)
                            elif args.command == 'navigate':
                                result = navigate(store, d)
                            elif args.command == 'record-evidence':
                                result = store.add_evidence(d)
                            elif args.command in ('status', 'dry-run'):
                                result = getattr(store, args.command.replace('-', '_'))()
                            else:
                                result = getattr(store, args.command.replace('-', '_'))(d)
                    print(dumps(result))
            finally:
                store.db.close()
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print('ERROR: '+(str(exc) or type(exc).__name__), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
