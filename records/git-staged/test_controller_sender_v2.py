import copy
import io
import json
from pathlib import Path
import struct
import time
import unittest
from unittest.mock import patch
import controller as c
import test_controller as fixtures
import controller_sender_v2 as v


URL = 'https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1&sn=S'


class FakeExecutor:
    def __init__(self, case):
        self.case = case
        self.calls = []
        self.fail = None
        self.active = '123'
        self.geometry = dict(case.g)
        self.on_click = None

    def __call__(self, command):
        self.calls.append(command)
        if command[:2] == ['xdotool', 'mousemove']:
            with c.sqlite3.connect(str(self.case.root / 'ledger.sqlite3')) as db:
                state = db.execute('SELECT status FROM ledger WHERE friend_id=? AND article_key=?',
                                   ('person_one', c.article_key(URL))).fetchone()[0]
            self.case.assertEqual(state, 'submitting')
            if self.on_click:
                self.on_click()
            if self.fail == 'click':
                raise c.Error('synthetic click failure')
            return b''
        if command == ['xdotool', 'getactivewindow']:
            return self.active.encode()
        if command == ['xwininfo', '-id', '123']:
            g = self.geometry
            return ('xwininfo: Window id: 0x7b "WeChat"\n'
                    '  Absolute upper-left X: {x}\n  Absolute upper-left Y: {y}\n'
                    '  Width: {w}\n  Height: {h}\n  Map State: IsViewable\n'.format(**g)).encode()
        if command == ['xprop', '-id', '123', 'WM_CLASS']:
            return b'WM_CLASS(STRING) = "wechat-instance", "wechat"\n'
        if command[0] == 'import':
            if self.fail == 'capture':
                raise c.Error('synthetic capture failure')
            return (b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' +
                    struct.pack('>II', self.geometry['w'], self.geometry['h']) + b'post')
        raise AssertionError('unexpected command: ' + repr(command))

    def clicks(self):
        return [x for x in self.calls if x[:2] == ['xdotool', 'mousemove']]


class SenderTest(unittest.TestCase):
    setUp = fixtures.ControllerTest.setUp
    evidence = fixtures.ControllerTest.evidence
    page = fixtures.ControllerTest.page
    identify = fixtures.ControllerTest.identify
    article = fixtures.ControllerTest.article

    def ready(self):
        self.page(['a', 'b', 'c'])
        self.page(['a', 'b', 'c'], True)
        self.page(['a', 'b', 'c'], True)
        self.s.record_end({'reviewer': 'test', 'bottom_visible': True, 'no_progress': True})
        # Deliberately reverse recording order; contact-list order must win.
        self.identify('b', 'person_two')
        self.identify('a', 'person_one')
        self.s.record_contact({'oid': 'c', 'evidence': self.evidence(), 'reviewer': 'test',
            'same_row': True, 'kind': 'friend', 'status': 'pending', 'reason': 'ID not visible'})
        self.article(URL)
        self.d = {'reviewer': 'test', 'oid': 'a', 'friend_id': 'person_one',
            'article_key': c.article_key(URL),
            'profile': {'reviewer': 'test', 'evidence': self.evidence(), 'oid': 'a',
                        'friend_id': 'person_one', 'field': 'WeChat ID', 'same_row': True},
            'favorite': {'reviewer': 'test', 'evidence': self.evidence(), 'url': URL,
                         'title': c.TITLE, 'source': c.SOURCE, 'first_favorite': True,
                         'exactly_one': True, 'url_observed': True, 'association_note': 'test favorite URL'},
            'evidence': self.evidence(), 'screen': 'send-confirmation',
            'recipient_id': 'person_one', 'recipient_count': 1, 'article_count': 1,
            'recipient_matches_profile': True, 'article_matches_favorite': True,
            'url': URL, 'send_control': True, 'target': [20, 25, 60, 10], 'x': 25, 'y': 28}
        self.fake = FakeExecutor(self)
        self.desktop = v.Desktop(self.fake)
        return self.d

    def send(self):
        return v.submit(self.s, self.d, self.token, self.desktop, approval=lambda request: True)

    def state(self):
        return self.s.db.execute('SELECT status FROM ledger WHERE friend_id=? AND article_key=?',
                                ('person_one', c.article_key(URL))).fetchone()[0]

    def confirmation(self):
        observed = time.time()
        return {'reviewer': 'test', 'friend_id': 'person_one', 'article_key': c.article_key(URL),
                'evidence': self.evidence(), 'recipient_id': 'person_one', 'url': URL,
                'url_observed': True, 'association_note': 'new outgoing card URL and visible time reviewed',
                'outgoing': True, 'exactly_one': True, 'recipient_verified': True,
                'observed_at': observed, 'time_visible': True, 'time_note': 'reviewed visible send timestamp'}

    def test_real_commands_durable_intent_post_capture_and_no_retry(self):
        self.ready()
        result = self.send()
        self.assertEqual(result['status'], 'submitting')
        self.assertEqual(self.state(), 'submitting')
        self.assertEqual(self.fake.clicks(), [['xdotool', 'mousemove', '--sync', '25', '28', 'click', '1']])
        self.assertIn(['import', '-window', 'root', '-crop', '100x100+10+20', '+repage', '-strip', 'png:-'], self.fake.calls)
        self.assertTrue(Path(self.s.evidence(result['after'])['path']).is_file())
        with self.assertRaises(c.Error):
            self.send()
        self.assertEqual(len(self.fake.clicks()), 1)
        self.assertEqual(self.old.read_bytes(), self.before)
        self.assertEqual(len(self.s.list('legacy')), 3)

    def test_cli_and_default_policy_deny_without_store_or_tools(self):
        with patch.object(c, 'Store', side_effect=AssertionError('DB forbidden')), \
             patch.object(c, 'tool', side_effect=AssertionError('desktop forbidden')), \
             patch('sys.stderr', new_callable=io.StringIO):
            self.assertEqual(v.main(['submit', '--data', '{broken']), 2)
            self.assertEqual(v.main(['submit', '--data', '{"approved":true}']), 2)
        self.ready()
        with self.assertRaisesRegex(c.Error, 'APPROVAL_REQUIRED'):
            v.submit(self.s, self.d, self.token, self.desktop)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.s.list('ledger'), [])

    def test_queue_order_confirmed_skip_and_pending_exclusion(self):
        self.ready()
        report = v.current_queue(self.s)
        self.assertEqual([x['friend_id'] for x in report['queue']], ['person_one', 'person_two'])
        self.assertEqual(report['next']['friend_id'], 'person_one')
        self.assertEqual(report['excluded'][0]['reason'], 'identity_pending')
        self.s.intent('person_one', c.article_key(URL), {})
        self.s.transition('person_one', c.article_key(URL), 'confirmed', {'fixture': True})
        self.assertEqual(v.current_queue(self.s)['next']['friend_id'], 'person_two')
        self.assertEqual(len(self.s.list('ledger')), 2)

    def test_unmapped_history_never_eligible(self):
        self.ready()
        with self.s.db:
            record = self.s.item('contacts', 'a')
            self.s.put('contacts', 'a', dict(record, friend_id='assfox'))
        report = v.current_queue(self.s)
        self.assertIn('legacy_unmapped', report['queue'][0]['reasons'])
        self.assertEqual(report['next']['friend_id'], 'person_two')
        self.assertFalse(any(r['friend_id'] == 'assfox' for r in self.s.list('ledger')))

    def test_input_identity_article_order_and_count_mismatches(self):
        self.ready()
        mutations = [
            {'friend_id': 'person_two'}, {'oid': 'b'}, {'article_key': 'wrong'},
            {'recipient_id': 'person_two'}, {'recipient_count': 2}, {'article_count': 2},
            {'recipient_count': True}, {'article_count': True},
            {'recipient_count': 1.0}, {'article_count': 1.0}, {'url': URL.replace('mid=2', 'mid=3')},
            {'recipient_matches_profile': False}, {'article_matches_favorite': False},
            {'profile': dict(self.d['profile'], friend_id='person_two')},
            {'profile': dict(self.d['profile'], oid='b')},
            {'profile': dict(self.d['profile'], field='nickname')},
            {'profile': dict(self.d['profile'], same_row=False)},
            {'favorite': dict(self.d['favorite'], title='wrong')},
            {'favorite': dict(self.d['favorite'], source='wrong')},
            {'favorite': dict(self.d['favorite'], exactly_one=False)},
            {'favorite': dict(self.d['favorite'], url_observed=False)},
            {'favorite': dict(self.d['favorite'], association_note='')},
            {'favorite': dict(self.d['favorite'], first_favorite=False)},
            {'favorite': dict(self.d['favorite'], url=URL.replace('mid=2', 'mid=3'))},
            {'target': [500, 500, 10, 10]}, {'x': 99}, {'x': True}, {'y': 28.0},
            {'screen': 'chat'}, {'reviewer': ''}, {'send_control': False}]
        original = copy.deepcopy(self.d)
        for change in mutations:
            with self.subTest(change=change):
                self.d = dict(original, **change)
                with self.assertRaises(c.Error):
                    self.send()
                self.assertEqual(self.fake.clicks(), [])
                self.assertEqual(self.state(), 'pending')
        self.d = original

    def test_pre_intent_stale_hash_geometry_active_and_lease_failures(self):
        self.ready()
        self.fake.active = '999'
        with self.assertRaises(c.Error):
            self.send()
        self.fake.active = '123'
        self.fake.geometry['x'] += 1
        with self.assertRaises(c.Error):
            self.send()
        self.fake.geometry = dict(self.g)
        with patch.object(v.time, 'time', return_value=time.time() + 181):
            with self.assertRaises(c.Error):
                self.send()
        with self.assertRaises(c.Error):
            v.submit(self.s, self.d, 'wrong', self.desktop, approval=lambda request: True)
        e = self.s.evidence(self.d['profile']['evidence'])
        Path(e['path']).write_bytes(b'changed')
        with self.assertRaises(c.Error):
            self.send()
        self.assertEqual(self.fake.clicks(), [])
        self.assertEqual(self.state(), 'pending')

    def test_nonlatest_final_evidence_blocks(self):
        self.ready()
        self.evidence()
        with self.assertRaises(c.Error):
            self.send()
        self.assertEqual(self.fake.clicks(), [])

    def test_click_failure_uncertain_no_retry(self):
        self.ready()
        self.fake.fail = 'click'
        with self.assertRaises(c.Error):
            self.send()
        self.assertEqual(self.state(), 'uncertain')
        self.assertIsNone(v.current_queue(self.s)['next'])
        with self.assertRaises(c.Error):
            self.send()
        self.assertEqual(len(self.fake.clicks()), 1)

    def test_post_intent_guard_failure_blocks_even_without_click(self):
        self.ready()
        with patch.object(self.desktop, 'guard', side_effect=[self.s.evidence(self.d['evidence']),
                                                              c.Error('geometry changed')]):
            with self.assertRaises(c.Error):
                self.send()
        self.assertEqual(self.state(), 'uncertain')
        self.assertEqual(self.fake.clicks(), [])
        with self.assertRaises(c.Error):
            self.send()
        self.assertEqual(self.fake.clicks(), [])

    def test_post_capture_failure_uncertain(self):
        self.ready()
        self.fake.fail = 'capture'
        with self.assertRaises(c.Error):
            self.send()
        self.assertEqual(self.state(), 'uncertain')
        self.assertEqual(len(self.fake.clicks()), 1)

    def test_crash_after_intent_survives_restart(self):
        self.ready()
        with patch.object(self.desktop, 'guard', side_effect=[self.s.evidence(self.d['evidence']), SystemExit('crash')]), \
             patch.object(self.s, 'transition', side_effect=OSError('process died before recovery write')):
            with self.assertRaises(SystemExit):
                self.send()
        self.assertEqual(self.fake.clicks(), [])
        other = c.Store(self.root)
        try:
            self.assertEqual(other.list('ledger')[0]['status'], 'submitting')
            self.assertIsNone(v.current_queue(other)['next'])
            with self.assertRaises(c.Error):
                v.submit(other, self.d, self.token, self.desktop, approval=lambda request: True)
        finally:
            other.db.close()
        self.assertEqual(self.fake.clicks(), [])

    def test_reconciliation_requires_new_recipient_article_time_evidence(self):
        self.ready()
        self.send()
        d = self.confirmation()
        for change in ({'recipient_id': 'person_two'}, {'url': URL.replace('mid=2', 'mid=3')},
                       {'evidence': self.d['evidence']}, {'observed_at': 1},
                       {'observed_at': True}, {'observed_at': time.time()+100},
                       {'time_visible': False}, {'time_note': ''}, {'recipient_verified': False},
                       {'url_observed': False}, {'association_note': ''},
                       {'outgoing': False}, {'exactly_one': False}):
            with self.subTest(change=change):
                with self.assertRaises(c.Error):
                    v.reconcile(self.s, dict(d, **change), self.token)
                self.assertEqual(self.state(), 'submitting')
        result = v.reconcile(self.s, d, self.token)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(self.state(), 'confirmed')
        self.assertEqual(v.current_queue(self.s)['next']['friend_id'], 'person_two')
        self.assertEqual(self.old.read_bytes(), self.before)
        self.assertEqual(len(self.fake.clicks()), 1)
        with self.assertRaises(c.Error):
            v.reconcile(self.s, d, self.token)

    def test_uncertain_can_only_be_explicitly_confirmed_with_new_review(self):
        self.ready()
        self.fake.fail = 'capture'
        with self.assertRaises(c.Error):
            self.send()
        v.reconcile(self.s, self.confirmation(), self.token)
        self.assertEqual(self.state(), 'confirmed')
        self.assertEqual(len(self.fake.clicks()), 1)


    def test_default_and_cli_denial_precede_locks_and_any_store_access(self):
        with patch.object(c, 'process_guard', side_effect=AssertionError('lock forbidden')), \
             patch.object(c, 'legacy_guard', side_effect=AssertionError('lock forbidden')), \
             patch.object(c, 'Store', side_effect=AssertionError('DB forbidden')), \
             patch.object(c, 'tool', side_effect=AssertionError('tool forbidden')), \
             patch('sys.stderr', new_callable=io.StringIO) as err:
            with self.assertRaisesRegex(c.Error, 'APPROVAL_REQUIRED'):
                v.submit(None, {}, None)
            for args in (['submit'], ['--data', '{broken', 'submit'],
                         ['--token', 'fake', 'submit'], ['submit', '--enable-send'],
                         ['submit', '--data', '{broken'],
                         ['submit', '--data', '{"approved":true}', '--token', 'fake']):
                with patch.dict(c.os.environ, {'SEND_ENABLED': '1', 'APPROVED': 'true'}):
                    self.assertEqual(v.main(args), 2)
            self.assertIn('APPROVAL_REQUIRED', err.getvalue())

    def test_separate_evidence_chronology_and_each_stale_hash_failure(self):
        self.ready()
        original = copy.deepcopy(self.d)
        for part in ('profile', 'favorite'):
            eid = original[part]['evidence']
            saved = self.s.item('evidence', eid)
            for change in ({'captured_at': time.time()-181},
                           {'captured_at': self.s.evidence(original['evidence'])['captured_at']+1}):
                with self.subTest(part=part, change=change):
                    with self.s.db:
                        self.s.put('evidence', eid, dict(saved, **change))
                    with self.assertRaises(c.Error):
                        self.send()
                    self.assertEqual(self.state(), 'pending')
                    with self.s.db:
                        self.s.put('evidence', eid, saved)
            path = Path(saved['path'])
            raw = path.read_bytes()
            path.write_bytes(b'bad hash')
            with self.assertRaises(c.Error):
                self.send()
            path.write_bytes(raw)
            self.d = copy.deepcopy(original)
            self.d[part]['evidence'] = original['evidence']
            with self.assertRaises(c.Error):
                self.send()
            self.d = copy.deepcopy(original)
        final = self.s.evidence(original['evidence'])
        Path(final['path']).write_bytes(b'bad final hash')
        with self.assertRaises(c.Error):
            self.send()
        self.assertEqual(self.fake.clicks(), [])
        self.assertEqual(self.state(), 'pending')

    def test_locks_lease_and_old_state_block_preintent(self):
        self.ready()
        v.current_queue(self.s)
        with c.process_guard(self.root):
            with self.assertRaises(c.Error):
                self.send()
        with c.legacy_guard(self.old):
            with self.assertRaises(c.Error):
                self.send()
        self.old.write_text('{}')
        with self.assertRaises(c.Error):
            self.send()
        self.old.write_bytes(self.before)
        with self.assertRaises(c.Error):
            v.submit(self.s, self.d, 'bad-token', self.desktop, approval=lambda request: True)
        self.assertEqual(self.state(), 'pending')
        self.assertEqual(self.fake.calls, [])

    def test_global_block_includes_nonqueue_current_article_intents(self):
        self.ready()
        key = c.article_key(URL)
        with self.s.db:
            self.s.db.execute('INSERT INTO ledger VALUES(?,?,?,?)',
                             ('off_page_friend', key, 'submitting', '{}'))
        report = v.current_queue(self.s)
        self.assertIsNone(report['next'])
        self.assertEqual(report['reconciliation_required'], ['off_page_friend'])
        with self.assertRaises(c.Error):
            self.send()
        self.assertEqual(self.fake.calls, [])

    def test_geometry_invalid_class_and_dynamic_post_capture(self):
        self.ready()
        for change in ({'x': -1}, {'w': 0}, {'y': 21}, {'h': 101}):
            with self.subTest(change=change):
                self.fake.geometry = dict(self.g, **change)
                with self.assertRaises(c.Error):
                    self.send()
                self.assertEqual(self.state(), 'pending')
        self.fake.geometry = dict(self.g)
        def invalid_class(command):
            if command[0] == 'xprop':
                return b'WM_CLASS(STRING) = "other", "other"'
            return self.fake(command)
        with self.assertRaises(c.Error):
            v.submit(self.s, self.d, self.token, v.Desktop(invalid_class),
                     approval=lambda request: True)
        self.assertEqual(self.fake.clicks(), [])
        self.fake.on_click = lambda: self.fake.geometry.update(x=30, y=40, w=120, h=110)
        result = self.send()
        self.assertIn(['import', '-window', 'root', '-crop', '120x110+30+40',
                       '+repage', '-strip', 'png:-'], self.fake.calls)
        self.assertEqual(self.s.evidence(result['after'])['geometry'], self.fake.geometry)

    def test_reconcile_latest_hash_fresh_path_and_no_ui(self):
        self.ready()
        self.send()
        review = self.confirmation()
        eid = review['evidence']
        saved = self.s.evidence(eid)
        before = self.s.evidence(self.d['evidence'])
        for change in ({'captured_at': time.time()-181},
                       {'captured_at': 1},
                       {'path': before['path'], 'sha256': before['sha256']}):
            with self.subTest(change=change):
                with self.s.db:
                    self.s.put('evidence', eid, dict(saved, **change))
                with self.assertRaises(c.Error):
                    v.reconcile(self.s, review, self.token)
                self.assertEqual(self.state(), 'submitting')
                with self.s.db:
                    self.s.put('evidence', eid, saved)
        path = Path(saved['path'])
        raw = path.read_bytes()
        path.write_bytes(b'corrupted confirmation')
        with self.assertRaises(c.Error):
            v.reconcile(self.s, review, self.token)
        path.write_bytes(raw)
        self.evidence()
        with self.assertRaises(c.Error):
            v.reconcile(self.s, review, self.token)
        new_review = self.confirmation()
        calls = list(self.fake.calls)
        with patch.object(c, 'tool', side_effect=AssertionError('UI forbidden')):
            v.reconcile(self.s, new_review, self.token)
        self.assertEqual(self.fake.calls, calls)
        self.assertEqual(self.state(), 'confirmed')
        self.assertEqual(self.old.read_bytes(), self.before)

    def test_pending_and_unreviewable_intent_cannot_reconcile(self):
        self.ready()
        v.current_queue(self.s)
        review = self.confirmation()
        with self.assertRaises(c.Error):
            v.reconcile(self.s, review, self.token)
        self.s.intent('person_one', c.article_key(URL), {})
        with self.assertRaises(c.Error):
            v.reconcile(self.s, self.confirmation(), self.token)
        self.assertEqual(self.state(), 'submitting')
        self.assertEqual(self.fake.calls, [])


class SenderDocumentationTest(unittest.TestCase):
    def test_rollout_contract_is_explicit(self):
        text = (Path(__file__).parent / 'README.md').read_text()
        for required in ('## Sender v2 — adapter implemented, approval NOT opened',
                         'ZERO new real sends', 'APPROVAL_REQUIRED',
                         'test_controller_sender_v2', 'No CLI flag, JSON field or environment variable',
                         'new recipient/article/time evidence', 'same ledger.sqlite3'):
            self.assertIn(required, text)


if __name__ == '__main__':
    unittest.main()
