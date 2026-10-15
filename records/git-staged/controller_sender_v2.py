#!/usr/bin/env python3
"""One-shot reviewed sender adapter. CLI real sends require future manager approval."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
import controller as c


def deny_approval(request):
    raise c.Error('APPROVAL_REQUIRED: manager has not opened real sending')


def current_queue(store):
    report = store.dry_run()
    key = report['article'].get('article_key')
    blocked = [r['friend_id'] for r in store.list('ledger')
               if r['article_key'] == key and r['status'] in ('submitting', 'uncertain')]
    eligible = [r for r in report['queue']
                if r['status'] == 'pending' and set(r['reasons']) == {'send_disabled'}]
    report['reconciliation_required'] = blocked
    report['next'] = eligible[0] if eligible and not blocked else None
    return report


@contextlib.contextmanager
def locked(store, token):
    with c.process_guard(store.root):
        old = store.get('legacy_path')
        c.need(old, 'init required')
        with c.legacy_guard(old):
            store.check_legacy()
            store.authorize(token)
            yield


def recent(store, eid):
    e = store.evidence(eid)
    c.need(0 <= time.time() - e['captured_at'] < c.MAX_AGE, 'review evidence stale')
    return e


def validate_request(store, d):
    c.reviewed(d)
    report = current_queue(store)
    item = report['next']
    c.need(item is not None, 'no eligible next recipient; reconcile blocked intents first')
    c.need(all(d.get(k) == item[k] for k in ('oid', 'friend_id', 'article_key')),
           'next recipient/order/article mismatch')
    profile, favorite = d['profile'], d['favorite']
    c.reviewed(profile)
    c.reviewed(favorite)
    p = recent(store, profile['evidence'])
    a = recent(store, favorite['evidence'])
    final = store.evidence(d['evidence'], fresh=True)
    c.need(len({p['id'], a['id'], final['id']}) == 3,
           'separate profile, favorite and final captures required')
    c.need(max(p['captured_at'], a['captured_at']) <= final['captured_at'], 'review chronology mismatch')
    contact = store.item('contacts', item['oid'])
    c.need(contact['kind'] == 'friend' and contact['status'] == 'identified'
           and contact['friend_id'] == d['friend_id'], 'stored identity mismatch')
    c.need(profile.get('oid') == d['oid'] and profile.get('friend_id') == d['friend_id']
           and profile.get('field') == 'WeChat ID' and profile.get('same_row') is True,
           'profile identity mismatch')
    c.need(favorite.get('title') == c.TITLE and favorite.get('source') == c.SOURCE
           and favorite.get('first_favorite') is True and favorite.get('exactly_one') is True
           and favorite.get('url_observed') is True and favorite.get('association_note')
           and c.article_key(favorite.get('url')) == d['article_key'], 'first favorite URL mismatch')
    c.need(d.get('screen') == 'send-confirmation' and d.get('send_control') is True
           and d.get('recipient_id') == d['friend_id']
           and d.get('recipient_matches_profile') is True
           and d.get('article_matches_favorite') is True
           and c.article_key(d.get('url')) == d['article_key'], 'final recipient/article mismatch')
    c.need(type(d.get('recipient_count')) is int and d['recipient_count'] == 1
           and type(d.get('article_count')) is int and d['article_count'] == 1,
           'exactly one recipient and article required')
    c.need(c.inside(d['target'], c.rect(final['geometry'])), 'target outside reviewed window')
    c.need(type(d.get('x')) is int and type(d.get('y')) is int
           and c.inside([d['x'], d['y'], 1, 1], d['target']), 'click outside reviewed target')
    return final


class Desktop:
    """Real command adapter; tests inject a bytes-returning executor, never real tools."""
    def __init__(self, execute=None):
        self.execute = execute if execute is not None else c.tool

    def geometry(self, wid):
        c.need(str(wid).isdigit(), 'decimal window ID required')
        text = self.execute(['xwininfo', '-id', str(wid)]).decode(errors='replace')
        c.need('Map State: IsViewable' in text, 'window not viewable')
        g = {'id': str(wid)}
        for key, label in (('x', 'Absolute upper-left X'), ('y', 'Absolute upper-left Y'),
                           ('w', 'Width'), ('h', 'Height')):
            m = re.search(r'^\s*' + label + r':\s*(-?\d+)', text, re.M)
            c.need(m is not None, 'missing window geometry ' + key)
            g[key] = int(m.group(1))
        c.need(g['x'] >= 0 and g['y'] >= 0 and g['w'] > 0 and g['h'] > 0, 'offscreen/invalid window')
        title = re.search(r'Window id:.*?"(.*)"', text)
        g['title'] = title.group(1) if title else ''
        text = self.execute(['xprop', '-id', str(wid), 'WM_CLASS']).decode(errors='replace').strip()
        m = re.fullmatch(r'WM_CLASS\(STRING\) = "([^"\\\r\n]+)", "([^"\\\r\n]+)"', text)
        c.need(m is not None, 'missing/invalid WM_CLASS')
        g['wm_class'] = m.group(2)
        c.need(re.search(r'wechat|weixin|微信', g['wm_class'], re.I), 'not a WeChat window')
        return g

    def guard(self, store, d):
        e = store.evidence(d['evidence'], fresh=True)
        c.need(self.geometry(e['geometry']['id']) == e['geometry'], 'geometry changed; recapture/review')
        active = self.execute(['xdotool', 'getactivewindow']).decode().strip()
        c.need(active == e['geometry']['id'], 'reviewed window is not active')
        return e

    def click(self, d):
        # Exactly one tool invocation and one button-1 click. Never retry.
        self.execute(['xdotool', 'mousemove', '--sync', str(d['x']), str(d['y']), 'click', '1'])

    def capture(self, store, wid, reviewer):
        g = self.geometry(wid)
        active = self.execute(['xdotool', 'getactivewindow']).decode().strip()
        c.need(active == g['id'], 'post-send window is not active')
        started = time.time()
        crop = '%dx%d+%d+%d' % (g['w'], g['h'], g['x'], g['y'])
        png = self.execute(['import', '-window', 'root', '-crop', crop, '+repage', '-strip', 'png:-'])
        c.need(self.geometry(wid) == g, 'window moved during capture')
        c.need(self.execute(['xdotool', 'getactivewindow']).decode().strip() == g['id'],
               'active window changed during capture')
        path = store.root / ('sender_capture_' + uuid.uuid4().hex + '.png')
        with path.open('xb') as f:
            f.write(png)
            f.flush()
            os.fsync(f.fileno())
        fd = os.open(str(store.root), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return store.add_evidence({'path': str(path), 'sha256': c.digest(path),
            'captured_at': started, 'geometry': g, 'geometry_source': 'xwininfo',
            'reviewer': reviewer, 'main_window': True})


def submit(store, request, token, desktop=None, *, approval=deny_approval):
    # Copy input so an injected policy cannot alter the validated request in place.
    d = json.loads(c.dumps(request))
    c.need(approval(json.loads(c.dumps(d))) is True, 'APPROVAL_REQUIRED')
    desktop = desktop if desktop is not None else Desktop()
    with locked(store, token):
        final = validate_request(store, d)
        desktop.guard(store, d)
        fid, key = d['friend_id'], d['article_key']
        store.intent(fid, key, d)  # FULL-synchronous commit before any possible click.
        try:
            desktop.guard(store, d)  # Recheck latest/hash/age/geometry/active after commit.
            desktop.click(d)
            after = desktop.capture(store, final['geometry']['id'], d['reviewer'])
            store.event({'kind': 'sender-result', 'friend_id': fid, 'article_key': key,
                         'status': 'submitting', 'before': final['id'], 'after': after['id']})
            return {'friend_id': fid, 'article_key': key, 'status': 'submitting', 'after': after['id']}
        except BaseException as exc:
            # Failure of this recovery write still leaves the already durable submitting intent.
            try:
                store.transition(fid, key, 'uncertain', {'kind': 'sender-failure',
                    'error': str(exc) or type(exc).__name__, 'before': final['id']})
            except BaseException:
                pass
            raise


def reconcile(store, d, token):
    with locked(store, token):
        c.reviewed(d)
        fid, key = d['friend_id'], d['article_key']
        row = store.db.execute('SELECT status,data FROM ledger WHERE friend_id=? AND article_key=?',
                               (fid, key)).fetchone()
        c.need(row and row['status'] in ('submitting', 'uncertain'), 'reconciliation state required')
        data = json.loads(row['data'])
        intent = data.get('intent')
        c.need(intent and isinstance(intent.get('attestation'), dict), 'reviewable sender intent required')
        request = intent['attestation']
        c.need(request.get('friend_id') == fid and request.get('article_key') == key,
               'intent identity/article mismatch')
        e = store.evidence(d['evidence'], fresh=True)
        before = store.evidence(request['evidence'])
        c.need(e['id'] != before['id'] and e['path'] != before['path']
               and e['captured_at'] > intent['at'], 'new post-intent evidence required')
        observed = d.get('observed_at')
        c.need(type(observed) in (int, float) and intent['at'] <= observed <= e['captured_at']
               and d.get('time_visible') is True and isinstance(d.get('time_note'), str)
               and d['time_note'].strip(), 'new reviewed send time required')
        c.need(d.get('recipient_id') == fid and d.get('recipient_verified') is True
               and d.get('outgoing') is True and d.get('exactly_one') is True,
               'reviewed single outgoing recipient/card required')
        c.need(c.article_key(d.get('url')) == key and d.get('url_observed') is True
               and isinstance(d.get('association_note'), str) and d['association_note'].strip(),
               'reviewed outgoing-card URL required')
        store.transition(fid, key, 'confirmed', dict(d, kind='sender-reconciliation'))
        return {'friend_id': fid, 'article_key': key, 'status': 'confirmed'}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # This denial precedes JSON parsing, DB creation, locks and all desktop tools.
    # argparse also accepts options before the positional command. Deny a submit
    # token regardless of its position without parsing or inspecting its data.
    if 'submit' in argv:
        print('ERROR: APPROVAL_REQUIRED: manager has not opened real sending', file=sys.stderr)
        return 2
    if not argv or argv[0] != 'reconcile':
        return c.main(argv)
    parser = argparse.ArgumentParser(description='Review an existing sender intent; never sends')
    parser.add_argument('command', choices=['reconcile'])
    parser.add_argument('--data', required=True)
    parser.add_argument('--token', required=True)
    args = parser.parse_args(argv)
    try:
        d = json.loads(args.data)
        c.need(isinstance(d, dict), '--data must be an object')
        root = Path(__file__).resolve().parent
        c.need(str(root) in c.ROOTS, 'controller must run from its approved upgrade directory')
        c.need((root / 'ledger.sqlite3').is_file(), 'existing ledger required')
        os.umask(0o077)
        store = c.Store(root)
        try:
            result = reconcile(store, d, args.token)
            print(c.dumps(result))
        finally:
            store.db.close()
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print('ERROR: ' + (str(exc) or type(exc).__name__), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
