import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import tempfile
import time
import unittest
from unittest.mock import patch
import controller as c


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.old = self.root / 'old.json'
        self.old.write_text(json.dumps({
            'version': 1, 'phase': 'complete', 'title': c.TITLE, 'source': c.SOURCE,
            'recipients': [{'identity': x, 'status': 'confirmed',
                            'confirmation': {'evidence': {'sha256': x + '-old'}}}
                           for x in ('assfox', 'File Transfer', 'cherry-pku')]}))
        Path(str(self.old) + '.lock').touch()
        self.before = self.old.read_bytes()
        self.s = c.Store(self.root)
        self.addCleanup(self.s.db.close)
        self.s.initialize(self.old)
        self.token = self.s.claim('unit-test')
        self.g = {'id': '123', 'x': 10, 'y': 20, 'w': 100, 'h': 100,
                  'title': 'WeChat', 'wm_class': 'wechat'}
        self.counter = 0

    def evidence(self):
        self.counter += 1
        p = self.root / ('image%d.png' % self.counter)
        # Synthetic PNG header; no real desktop command is called by tests.
        p.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' +
                      struct.pack('>II', 100, 100) + bytes([self.counter]))
        return self.s.add_evidence({'path': str(p), 'sha256': c.digest(p),
            'captured_at': time.time(), 'geometry': self.g, 'geometry_source': 'xwininfo',
            'reviewer': 'test', 'main_window': True})['id']

    def page(self, ids, scroll=None):
        e = self.evidence()
        d = {'evidence': e, 'reviewer': 'test', 'pane': [10, 20, 100, 100],
             'rows': [{'oid': x, 'label': 'same-name', 'box': [20, 25+i*15, 60, 10]}
                      for i, x in enumerate(ids)], 'all_visible_rows': True,
             'at_top': True, 'top_visible': True}
        if scroll:
            previous = self.s.list('pages')[-1]
            event = self.s.record_scroll({'before': previous['evidence'], 'after': e,
                'from_page': previous['id'], 'pane': previous['pane'], 'reviewer': 'test',
                'direction': 'down', 'notches': 1, 'actual_input': True, 'list_focused': True})
            d['scroll'] = event['id']
        return self.s.record_page(d)

    def identify(self, oid, friend_id):
        return self.s.record_contact({'oid': oid, 'evidence': self.evidence(),
            'reviewer': 'test', 'same_row': True, 'field': 'WeChat ID',
            'friend_id': friend_id, 'kind': 'friend', 'status': 'identified'})

    def article(self, url=None):
        return self.s.record_article({'evidence': self.evidence(), 'reviewer': 'test',
            'title': c.TITLE, 'source': c.SOURCE, 'first_favorite': True,
            'exactly_one': True, 'url_observed': True,
            'association_note': 'Synthetic test URL association, not real UI', 'url': url})

    def test_url_identity_and_tracking(self):
        a = c.article_key('https://mp.weixin.qq.com/s?sn=S&idx=1&mid=2&__biz=B&scene=1#x')
        b = c.article_key('http://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1&sn=S&scene=9')
        self.assertEqual(a, b)
        self.assertIn('__biz=B', a)
        self.assertIsNone(c.article_key('https://mp.weixin.qq.com/s/short'))
        self.assertIsNone(c.article_key('https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1'))
        self.assertIsNone(c.article_key('https://evil.test/s?__biz=B&mid=2&idx=1&sn=S'))
        self.assertIsNone(c.article_key('https://mp.weixin.qq.com/s?__biz=B&mid=2&mid=3&idx=1&sn=S'))
        self.assertNotEqual(a, c.article_key('https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=2&sn=S'))

    def test_history_unmapped_readonly_and_filetransfer(self):
        self.page(['a', 'b', 'f'])
        self.identify('a', 'assfox')
        self.identify('b', 'cherry-pku')
        self.s.record_contact({'oid': 'f', 'evidence': self.evidence(), 'reviewer': 'test',
            'same_row': True, 'kind': 'special', 'status': 'skipped', 'reason': 'File Transfer'})
        report = self.s.dry_run()
        self.assertTrue(all('legacy_unmapped' in x['reasons'] for x in report['queue']))
        self.assertEqual(len(self.s.list('ledger')), 0)
        self.assertEqual(self.old.read_bytes(), self.before)
        self.assertEqual(len(report['legacy']), 3)
        self.assertFalse(report['send_enabled'])

    def test_complete_overlap_and_tail(self):
        self.page(['a', 'b', 'c'])
        self.page(['b', 'c', 'd'], True)
        self.page(['b', 'c', 'd'], True)
        self.page(['b', 'c', 'd'], True)
        self.s.record_end({'reviewer': 'test', 'bottom_visible': True, 'no_progress': True})
        out = self.s.dry_run()
        self.assertTrue(out['coverage']['enumeration_complete'])
        self.assertEqual(out['coverage']['observations'], 4)
        self.assertEqual(len(out['excluded']), 4)
        self.assertTrue(all(x['reason'] == 'identity_pending' for x in out['excluded']))

    def test_overlap_rejects_previous_occurrence_appended_again(self):
        self.page(['a', 'b', 'c'])
        with self.assertRaisesRegex(c.Error, 'outside overlap'):
            self.page(['b', 'c', 'a'], True)
        self.assertEqual(len(self.s.list('pages')), 1)
        self.page(['b', 'c', 'd'], True)
        self.page(['b', 'c', 'd'], True)
        self.assertEqual(len(self.s.list('pages')), 3)

    def test_overlap_rejects_older_page_occurrence_appended_again(self):
        self.page(['a', 'b', 'c'])
        self.page(['b', 'c', 'd'], True)
        with self.assertRaisesRegex(c.Error, 'outside overlap'):
            self.page(['c', 'd', 'a'], True)
        self.assertEqual(len(self.s.list('pages')), 2)

    def test_gap_and_premature_tail_rejected(self):
        self.page(['a', 'b', 'c'])
        with self.assertRaises(c.Error):
            self.page(['d', 'e', 'f'], True)
        with self.assertRaises(c.Error):
            self.s.record_end({'reviewer': 'test', 'bottom_visible': True, 'no_progress': True})
        self.assertFalse(self.s.dry_run()['coverage']['enumeration_complete'])

    def test_same_name_is_not_identity_and_stable_id_dedup(self):
        self.page(['a', 'b', 'c'])
        self.identify('a', 'person_one')
        self.identify('b', 'person_two')
        self.identify('c', 'person_one')
        self.article('https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1&sn=S')
        out = self.s.dry_run()
        self.assertEqual(len(out['queue']), 2)
        self.assertEqual(out['excluded'][0]['reason'], 'duplicate_stable_id')
        self.s.dry_run()
        self.assertEqual(len(self.s.list('ledger')), 2)
        with self.assertRaises(c.Error):
            self.identify('a', 'other_person')

    def test_article_pending_never_creates_fake_pair(self):
        self.page(['a'])
        self.identify('a', 'person_one')
        self.article()
        out = self.s.dry_run()
        self.assertIn('article_pending', out['queue'][0]['reasons'])
        self.assertEqual(self.s.list('ledger'), [])

    def test_legacy_mapping_requires_url_and_original_card(self):
        self.page(['a'])
        self.identify('a', 'assfox')
        url = 'https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1&sn=S'
        self.article(url)
        d = {'friend_id': 'assfox', 'evidence': self.evidence(), 'reviewer': 'test',
             'same_original_card': True, 'url_observed': True, 'url': url,
             'association_note': 'Synthetic old-card URL evidence',
             'legacy_confirmation_sha256': 'wrong'}
        with self.assertRaises(c.Error):
            self.s.map_legacy(d)
        d['legacy_confirmation_sha256'] = 'assfox-old'
        self.s.map_legacy(d)
        out = self.s.dry_run()
        self.assertIn('confirmed', out['queue'][0]['reasons'])
        self.assertNotIn('legacy_unmapped', out['queue'][0]['reasons'])
        self.assertEqual(self.old.read_bytes(), self.before)

    def assert_legacy_mapping_evidence_failure(self, missing):
        self.page(['a'])
        self.identify('a', 'assfox')
        url = 'https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1&sn=S'
        self.article(url)
        eid = self.evidence()
        mapping = {'friend_id': 'assfox', 'evidence': eid, 'reviewer': 'test',
                   'same_original_card': True, 'url_observed': True, 'url': url,
                   'association_note': 'Synthetic old-card URL evidence',
                   'legacy_confirmation_sha256': 'assfox-old'}
        self.s.map_legacy(mapping)
        self.assertEqual(self.s.dry_run()['queue'][0]['status'], 'confirmed')
        ledger_before = self.s.list('ledger')
        legacy_before = self.s.list('legacy')
        path = Path(self.s.evidence(eid)['path'])
        if missing:
            path.unlink()
        else:
            path.write_bytes(b'corrupt mapping evidence')
        with self.assertRaisesRegex(c.Error, 'evidence'):
            self.s.dry_run()
        self.assertEqual(self.s.list('ledger'), ledger_before)
        self.assertEqual(self.s.list('legacy'), legacy_before)
        self.assertEqual(self.s.list('ledger')[0]['status'], 'confirmed')
        self.assertEqual(self.old.read_bytes(), self.before)

    def test_dry_run_rejects_missing_legacy_mapping_evidence(self):
        self.assert_legacy_mapping_evidence_failure(missing=True)

    def test_dry_run_rejects_corrupt_legacy_mapping_evidence(self):
        self.assert_legacy_mapping_evidence_failure(missing=False)

    def test_lease_survives_connection_and_rejects_steal(self):
        other = c.Store(self.root)
        try:
            with self.assertRaises(c.Error):
                other.claim('other')
            with self.assertRaises(c.Error):
                other.authorize('wrong')
            other.authorize(self.token)
            other.release(self.token)
            self.assertNotEqual(other.claim('other'), self.token)
        finally:
            other.db.close()

    def test_legacy_lock_busy_missing_and_state_change(self):
        with open(str(self.old) + '.lock', 'rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(c.Error):
                with c.legacy_guard(self.old):
                    pass
        Path(str(self.old) + '.lock').unlink()
        with self.assertRaises(c.Error):
            with c.legacy_guard(self.old):
                pass
        self.old.write_text('{}')
        with self.assertRaises(c.Error):
            self.s.check_legacy()

    def test_process_lock_busy(self):
        with c.process_guard(self.root):
            with self.assertRaises(c.Error):
                with c.process_guard(self.root):
                    pass

    def test_evidence_integrity_age_and_geometry(self):
        e = self.evidence()
        self.s.evidence(e, fresh=True)
        with patch('controller.time.time', return_value=time.time()+181):
            with self.assertRaises(c.Error):
                self.s.evidence(e, fresh=True)
        item = self.s.evidence(e)
        Path(item['path']).write_bytes(b'changed')
        with self.assertRaises(c.Error):
            self.s.evidence(e)
        e = self.evidence()
        with patch('controller.geometry', return_value=dict(self.g, x=11)):
            with self.assertRaises(c.Error):
                c.navigation_guard(self.s, {'evidence': e})

    def test_geometry_parser_is_not_proportional(self):
        text = ('xwininfo: Window id: 0x7b "WeChat"\n'
                '  Absolute upper-left X: 317\n  Absolute upper-left Y: 41\n'
                '  Width: 921\n  Height: 688\n  Map State: IsViewable\n')
        with patch('controller.tool', side_effect=[text.encode(),
                   b'WM_CLASS(STRING) = "wechat-instance", "WeChat"\n']) as tool:
            g = c.geometry('123')
        self.assertEqual((g['x'], g['y'], g['w'], g['h']), (317, 41, 921, 688))
        self.assertEqual(g['wm_class'], 'WeChat')
        self.assertEqual(tool.call_args_list[1].args[0], ['xprop', '-id', '123', 'WM_CLASS'])

    def test_geometry_rejects_missing_or_malformed_wm_class(self):
        text = ('xwininfo: Window id: 0x7b "WeChat"\n'
                '  Absolute upper-left X: 10\n  Absolute upper-left Y: 20\n'
                '  Width: 100\n  Height: 100\n  Map State: IsViewable\n').encode()
        for response in (b'WM_CLASS:  not found.\n', b'WM_CLASS(STRING) = "WeChat"\n',
                         b'WM_CLASS(STRING) = "wechat", ""\n', text):
            with self.subTest(response=response), \
                 patch('controller.tool', side_effect=[text, response]):
                with self.assertRaises(c.Error):
                    c.geometry('123')
        with patch('controller.tool', side_effect=[text, FileNotFoundError('xprop missing')]):
            with self.assertRaisesRegex(c.Error, 'xprop'):
                c.geometry('123')

    def test_capture_success_with_supported_geometry_commands(self):
        text = ('xwininfo: Window id: 0x7b "WeChat"\n'
                '  Absolute upper-left X: 10\n  Absolute upper-left Y: 20\n'
                '  Width: 100\n  Height: 100\n  Map State: IsViewable\n').encode()
        png = (b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' +
               struct.pack('>II', 100, 100) + b'synthetic capture')
        calls = []
        def output(command):
            calls.append(command)
            if command == ['xdotool', 'search', '--onlyvisible', '--class', '[Ww]e[Cc]hat|[Ww]eixin|微信']:
                return b'123\n'
            if command == ['xwininfo', '-id', '123']:
                return text
            if command == ['xprop', '-id', '123', 'WM_CLASS']:
                return b'WM_CLASS(STRING) = "wechat-instance", "WeChat"\n'
            if command == ['import', '-window', 'root', '-crop', '100x100+10+20', '+repage', '-strip', 'png:-']:
                return png
            self.fail('unexpected command: ' + repr(command))
        with patch('controller.tool', side_effect=output):
            evidence = c.capture(self.s, {'reviewer': 'test', 'main_window': True})
        self.assertEqual(evidence['geometry'], dict(self.g, wm_class='WeChat'))
        self.assertEqual(Path(evidence['path']).read_bytes(), png)
        self.assertEqual(self.s.evidence(evidence['id']), evidence)
        self.assertEqual(calls.count(['xprop', '-id', '123', 'WM_CLASS']), 2)

    def test_future_intent_durable_no_retry(self):
        self.s.db.execute('INSERT INTO ledger VALUES(?,?,?,?)', ('friend', 'key', 'pending', '{}'))
        self.s.db.commit()
        self.s.intent('friend', 'key', {'synthetic': True})
        other = c.Store(self.root)
        try:
            self.assertEqual(other.list('ledger')[0]['status'], 'submitting')
            with self.assertRaises(c.Error):
                other.intent('friend', 'key', {})
            other.transition('friend', 'key', 'uncertain', {'synthetic': True})
            with self.assertRaises(c.Error):
                other.transition('friend', 'key', 'pending', {})
            with self.assertRaises(c.Error):
                other.intent('friend', 'key', {})
            other.transition('friend', 'key', 'confirmed', {'synthetic': True})
        finally:
            other.db.close()

    def test_submit_never_touches_tools_or_store(self):
        with patch('controller.tool', side_effect=AssertionError('UI forbidden')), \
             patch('controller.Store', side_effect=AssertionError('DB forbidden')):
            self.assertEqual(c.main(['submit']), 2)
            self.assertEqual(c.main(['submit', '--data', '{"execute":true}']), 2)

    def test_navigation_cannot_use_send_or_chat_action(self):
        with patch('controller.tool', side_effect=AssertionError('UI forbidden')):
            for action in ('send', 'submit', 'chat', 'favorites'):
                with self.assertRaises(c.Error):
                    c.navigate(self.s, {'reviewer': 'test', 'safe_navigation': True,
                                        'screen': 'contacts', 'action': action})

    def test_capture_rejects_geometry_change(self):
        with patch('controller.windows', return_value=[self.g]), \
             patch('controller.geometry', return_value=dict(self.g, w=101)), \
             patch('controller.tool', return_value=b'not accepted after geometry change'):
            with self.assertRaises(c.Error):
                c.capture(self.s, {'reviewer': 'test', 'main_window': True})
        self.assertEqual(self.s.list('evidence'), [])

    def test_verified_article_cannot_change_or_become_pending(self):
        self.article('https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1&sn=S')
        for url in (None, 'https://mp.weixin.qq.com/s?__biz=B&mid=3&idx=1&sn=S'):
            with self.assertRaises(c.Error):
                self.article(url)

    def test_navigation_rejects_nonlatest_and_inactive_window(self):
        old = self.evidence()
        latest = self.evidence()
        with patch('controller.tool', side_effect=AssertionError('no tool for old evidence')):
            with self.assertRaises(c.Error):
                c.navigation_guard(self.s, {'evidence': old})
        with patch('controller.geometry', return_value=self.g), \
             patch('controller.tool', return_value=b'999'):
            with self.assertRaises(c.Error):
                c.navigation_guard(self.s, {'evidence': latest})

    def test_scroll_requires_strict_capture_chronology(self):
        p = self.page(['a', 'b', 'c'])
        before = self.s.evidence(p['evidence'])
        after = self.s.evidence(self.evidence())
        after['captured_at'] = before['captured_at']
        with self.s.db:
            self.s.put('evidence', after['id'], after)
        with self.assertRaises(c.Error):
            self.s.record_scroll({'before': before['id'], 'after': after['id'],
                'from_page': p['id'], 'pane': p['pane'], 'reviewer': 'test',
                'direction': 'down', 'notches': 1, 'actual_input': True, 'list_focused': True})

    def test_tail_rejects_one_file_reregistered_as_three_captures(self):
        p = self.page(['a', 'b', 'c'])
        image = self.s.evidence(p['evidence'])
        for _ in range(2):
            previous = self.s.list('pages')[-1]
            data = dict(image, captured_at=time.time())
            data.pop('id')
            new = self.s.add_evidence(data)
            event = self.s.record_scroll({'before': previous['evidence'], 'after': new['id'],
                'from_page': previous['id'], 'pane': previous['pane'], 'reviewer': 'test',
                'direction': 'down', 'notches': 1, 'actual_input': True, 'list_focused': True})
            self.s.record_page(dict(p, evidence=new['id'], scroll=event['id']))
        with self.assertRaises(c.Error):
            self.s.record_end({'reviewer': 'test', 'bottom_visible': True, 'no_progress': True})
        self.assertFalse(self.s.dry_run()['coverage']['enumeration_complete'])

    def test_navigation_intent_is_committed_before_input_failure(self):
        e = self.evidence()
        d = {'evidence': e, 'reviewer': 'test', 'safe_navigation': True,
             'screen': 'contacts', 'action': 'contact-row', 'target': [20, 25, 60, 10],
             'x': 25, 'y': 28}
        def failed_input(command):
            other = c.Store(self.root)
            try:
                self.assertEqual(other.list('events')[-1]['status'], 'intent')
            finally:
                other.db.close()
            raise c.Error('synthetic tool failure')
        with patch('controller.navigation_guard', return_value=self.s.evidence(e)), \
             patch('controller.tool', side_effect=failed_input):
            with self.assertRaises(c.Error):
                c.navigate(self.s, d)
        self.assertEqual(self.s.list('events')[-1]['status'], 'uncertain')

    def test_status_redacts_lease_token_hash(self):
        self.assertNotIn(hashlib.sha256(self.token.encode()).hexdigest(),
                         json.dumps(self.s.status()))


if __name__ == '__main__':
    unittest.main()
