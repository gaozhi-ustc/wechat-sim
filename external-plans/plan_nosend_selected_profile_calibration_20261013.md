# Bounded selected-profile no-Send calibration implementation plan

> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the sole parent controller to obtain actual fresh selected-profile, chat, and native Favorite-panel images by at most one Messages click and one cube click, without recipient/article admission, card selection, or Send.

**Architecture:** One opt-in addon borrows the unchanged UI245d `Engine`, its real `Desktop`, and the already locked `LocalDB`. It journals its own closed action vocabulary and session-local calibration state in the existing `db12_session`/`db12_operation` tables, reuses `Engine.record`/`boundary`, and directly calls `f.check_owned` rather than trusting the optional Engine callback. A distinct exact-build/session-bound no-Send approval admits this path; it is not a direct-request, detector, recipient, article, or send capability.

**Tech Stack:** Python standard library, existing SQLite durable operation/session APIs, unchanged X11 ownership/guard/capture/input adapter, `unittest` with generated temporary fixtures. No schema changes, database creation in runtime, model calls, image decoding by the addon, or new runner/service/framework.

**Tasks Overview:** One bounded writer unit, two new files, one offline red/green cycle. No existing file is edited. In particular the stale root PublicUI is not changed.

---

## Project constraints and findings

- Root: `/tmp/wxview92/upgrade_20261010T1529`. `CLAUDE.md` is absent. `AGENTS.md` requires sole-parent live control, exact reviewed deployment, immutable old facts, existing locks/lease, no child SSH/UI/production DB/Git operations. Its latest authority points to `msg_mv6nn1hjqjrlfm6nuy9`; that does not make a no-Send review a sending approval.
- This plan is **not** a production approval or an implementation. Writer runs only generated offline fixtures. Parent alone may subsequently deploy/use the independently reviewed exact delta under the existing live authority. Do not create approval files for production as part of implementation.
- Existing source evidence: candidate UI lines 179–229 expose `Engine(db, desktop, sid, check=...)` and authenticated immutable full-root records with strict `<180s`; lines 547–552 implement a journal/state/evidence boundary; lines 554–748 show the durable operation pattern. UI lines 297–338 and 630–648 write old coverage/exact identity; do not call them. UI `cube` requires `chat-copied`/old article; do not fake those values.
- `controller_db_forward_20261012.py:230–260` is the existing lock context. Use `with f.locked(root, cred)` for an existing live lease (or `with f.locked(root)` before new open). `readonly=True` is observation only, not a writable session. Lines 300–315 are the real `f.open_owned(db, main, new_private_path, base_review)`. Lines 318–327 are `f.check_owned(db, cred, base_review)`. Lines 330–357 are honest `f.close_owned(db, cred, reason)`. There is no `f.Session`.
- `controller_db_store_20261012.py:631–648` durably commits operation intent before input and atomically completes result/session. Addon only uses these, `session`, and capture storage via existing Desktop. It never calls `put`, `reserve`, round install/borrow, coverage APIs, or direct-request admission.
- `controller_db_round_store_20261013.py:422–482` is the **entire** conservative `no_unresolved(base)` check. Keep it intact, call it directly with no exceptions/allow/current_operation, and do not install schemas to make it pass. Missing required tables are a stop. Its existing `INPUT_ACTIONS` does not include addon actions, so the addon additionally rejects every global NULL operation other than its authenticated current operation, and every unknown/non-done calibration operation, including from closed sessions.
- `controller_db_x11_20261012.py:235–293` performs genuine capture, strict evidence/owner/focus/age checks, and single-use input guard. No manufactured `main_active` or owner facts. An embedded profile is supported only when **actual** active window equals actual main; an unexpected active popup at Messages/cube stops. Capturing the popup after cube retains the real `favorite` owner policy and full process/transient checks.
- The account-current addon hash `88def117d06f4695d93453672ca376a3e8e6645631836e8cc0146a1713a68723` is source reference only. Its lines 122–201 bind and burn an old specific lineage; do not import it, call it, reuse its capability, or synthesize a new source history. Existing permitted recovery receipts show completed account-current/account-dismiss and capture. This addon requires the already established current account binding and does not refresh or invent it.
- Current selected-profile navigation can suffice **for navigation only**. A direct visual review of the fresh full image can identify the actual embedded selected profile and its Messages control without making an exact recipient/dedup claim. The next fresh chat image must independently show the cube and empty/disabled composer state. No OCR identity, old HuShengkun/name/row occurrence, old capture13, or fixed coordinate is accepted as navigation proof. If that actual UI is no longer present, stop; do not add row/scroll support speculatively.

### Exact source pins

These pins were read and SHA256-checked during planning. They are prerequisites, not permission to deploy or edit another source.

| Logical source | Local source to copy into offline fixture | SHA256 |
|---|---|---|
| controller.py | ROOT/controller.py | e4ebe8c4ce4e58b7b274475e262f02b60383675e93cba344eb326fb6748e3455 |
| controller_db_x11_20261012.py | ROOT/controller_db_x11_20261012.py | 252b8aa1edc7a64cc834f84ffb183ed42351eb41123f4c1ca79d6905de018846 |
| controller_db_store_20261012.py | ROOT/controller_db_store_20261012.py | 85f69b9d564b910d8e25daac29fe09ab73ddc7fb93362abd6eec3d9c26b7ca87 |
| controller_db_ui_20261012.py | /tmp/wxview92/db13_ui_selected_contacts_candidate_20261013.py | 245d856488dd78d686bd5248aafd11f900be99cee46d710825c732eb31f87238 |
| controller_db_forward_20261012.py | ROOT/controller_db_forward_20261012.py | c4b53a37a3c3e334176a4ebfff180b8547f39a691a6c100d85dd544b022ef8bb |
| controller_db_round_store_20261013.py | ROOT/controller_db_round_store_20261013.py | 03373c7da947feb0461b2e8670dff802b5d38a033f9b6c212862c0a4a2011504 |

`ROOT` in this table means the absolute root given above. The first five are the unchanged base review closure. RoundStore is an additional read-only dependency explicitly covered by addon approval; it is not the changing RoundUI (`e81469…`) and must not be replaced with it. If any listed source changes, fail the source guard and report drift; do not relax pins.

## API and operational boundary (parent reference, not writer actions)

Runtime entry is `cal.run(engine, q, cred, base_review, addon_review)` only. No CLI or persistent transport is added. Parent uses its existing locked one-action mechanism and reconstructs the unchanged `u.Engine` with `u.Desktop(state['main'])` and real `lambda: f.check_owned(db, cred, base_review)`. Addon checks real ownership independently on every boundary. Engine is never monkeypatched or subclassed in runtime.

A **fresh** legally opened DB12 session, steps zero, is required for first `calibration-capture`. Do not adopt the last closed Contacts session. Opening and honest close use existing `f` APIs; original new secret remains private and never appears in requests/results. The independent addon review has exactly:

- `authority`: `msg_mv6nn1hjqjrlfm6nuy9`
- `verdict`: `APPROVED`
- `reviewer`, `test_reference`: real nonempty independent review references
- `sha256`: actual reviewed addon file SHA256
- `scope`: `selected-profile-messages-cube-no-send`
- `session`: actual newly opened DB12 session UUID
- `main`: actual main window ID string
- `account_binding_sha256`: `d.hash_value(db.get('target_account'))` of the existing authentic account binding

This is the existing exact-addon approval convention extended with a narrow no-Send/session/account scope, not a new authority issuance service. The parent binds its existing exact-delta approval to that freshly opened session; writer does not fabricate real approval. The addon journals the capability digest but not credential/token. A capability for another session/build/account/main cannot be reused.

Request envelopes and observed fields are closed; exact definitions/code below are the entire API. At most six captures and two left clicks in this session. Each click requires a newly captured image after the preceding input. Review `reviewer='parent-visual'` means the parent actually saw the whole current screenshot; do not use that label for OCR/template/mock production output. Unknown operation result stops the session and all later addon sessions; no retry with a new operation/session hides it. No row selection, scrolling, focus activation, account repair, cancel click, card selection, Send, or clipboard operation exists.

Expected parent progression after exact-delta review: legally open → `calibration-capture` and visually review actual selected profile → `calibration-messages` → `calibration-capture` and visually review actual chat → `calibration-cube` → `calibration-capture` of actual panel → **honest no-input `f.close_owned`**. Closing releases the lease but does not dismiss the UI panel. Report that panel remains open/unselected if it does; do not claim UI dismissal. No explicit Cancel addition is needed to collect the images. If capture/control/account/ownership/freshness is ambiguous, close honestly with retained unknown facts and stop. Production layouts still require their separate actual detector admission afterward; calibration output alone does not admit them or authorize ordinary sending.

### Task 1: Add the two-click calibration addon and generated offline tests

**Objective:** Implement only the opt-in API above and prove real ownership, exact pins, durable-before-input, immutable business history, fresh evidence, bounded actions, and unknown-stop using generated fixtures.

**Context from:** Source map and contracts above; no additional architecture decision or production inspection is needed. The addon imports the logical UI245d name; the test subprocess constructs that exact composition from the candidate in a temporary directory, leaving root PublicUI untouched. All new session state uses `stage='calibration-only'` (not old `profile`, `chat-copied`, or `panel`) and nested `no_send_calibration`; `friend_id`, `oid`, and `intent` stay null. Old Engine guards therefore remain unchanged and do not receive invented sender/recipient/article prerequisites.

**Non-goals:** No ordinary sending, recipient/card selection, rows, scroll, account rebinding, reopening old session, CopyURL, frozen article, current round/coverage changes, detector admission, runtime/model changes, schema installation in runtime, second DB/framework, live UI/SSH/production DB/private image access, production approvals, deployment, Git or broad test reruns.

**Files:**
- Create `/tmp/wxview92/upgrade_20261010T1529/controller_db_nosend_calibration_20261013.py`
- Create `/tmp/wxview92/upgrade_20261010T1529/test_controller_db_nosend_calibration_20261013.py`

- [ ] **Step 1: Write the complete generated offline test file below.**

```python
"""Generated offline fixtures only; never connect to live UI or production DB."""
import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
NAME = 'controller_db_nosend_calibration_20261013.py'
if '--fixture' not in sys.argv:
    if __name__ == '__main__':
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('controller.py', 'controller_db_x11_20261012.py',
                         'controller_db_store_20261012.py', 'controller_db_forward_20261012.py',
                         'controller_db_round_store_20261013.py', NAME, Path(__file__).name):
                if (HERE/name).exists():
                    shutil.copyfile(HERE/name, root/name)
            shutil.copyfile(HERE.parent/'db13_ui_selected_contacts_candidate_20261013.py',
                            root/'controller_db_ui_20261012.py')
            result = subprocess.run([sys.executable, '-B', str(root/Path(__file__).name),
                                     '--fixture', *sys.argv[1:]], cwd=root,
                                    text=True, capture_output=True)
            print(result.stdout, end='')
            print(result.stderr, end='', file=sys.stderr)
            sys.exit(result.returncode)
else:
    sys.argv.remove('--fixture')
    import controller as c
    import controller_db_store_20261012 as d
    import controller_db_forward_20261012 as f
    import controller_db_ui_20261012 as u
    import controller_db_round_store_20261013 as r
    import controller_db_nosend_calibration_20261013 as a

    def owner(popup=False):
        main = dict(id='101', pid=77, x=10, y=10, w=600, h=500, wm_class='wechat')
        active = dict(id='102', pid=77, x=200, y=100, w=250, h=200,
                      wm_class='wechat') if popup else main
        process = dict(pid=77, start_ticks=123, exe='/fixture/wechat',
                       ancestry=[[77, 123], [1, 1]])
        return dict(main=main, active=active, process=process, active_process=process,
                    visible_mains=['101'], root=[0, 0, 800, 600],
                    mode='transient' if popup else 'main',
                    chain=['102', '101'] if popup else [])

    class CalibrationTest(unittest.TestCase):
        def setUp(self):
            self.tmp = tempfile.TemporaryDirectory()
            self.addCleanup(self.tmp.cleanup)
            self.root = Path(self.tmp.name)
            p = patch.object(d.socket, 'gethostname', return_value=d.LOCAL_HOST)
            p.start(); self.addCleanup(p.stop)
            self.db = d.LocalDB.create(self.root, {'fixture': 'generated only'})
            self.addCleanup(self.db.close)
            # Test fixture schema only. Runtime addon must never install any table.
            self.db.db.executescript(r.SCHEMA)
            self.popup = False; self.inputs = []; self.failure = False; self.drift = None
            self.desktop = object.__new__(u.Desktop)
            self.desktop.main_id = '101'
            for method, value in (('capture', self.capture_impl), ('guard', self.guard_impl),
                                  ('input', self.input_impl)):
                p = patch.object(u.Desktop, method, value)
                p.start(); self.addCleanup(p.stop)
            self.review = dict(authority=d.AUTHORITY, content_authority=d.CONTENT_AUTHORITY,
                               environment_authority=d.ENVIRONMENT_AUTHORITY, verdict='APPROVED',
                               reviewer='generated offline fixture review',
                               test_reference='generated fixture only', files=dict(a.BASE_PINS))
            old = f.open_owned(self.db, '101', self.root/'old.json', self.review)
            oldcred = f.credential(self.root/'old.json')
            evidence = self.capture_impl(self.db, old, 'profile')
            with self.db.tx():
                self.db.put('target_account', dict(account='gaozhi-xinshu', owner=evidence['owner'],
                    capture=evidence['id'], at=evidence['at'], reviewer='generated account fixture'))
            f.close_owned(self.db, oldcred, 'generated prior account fixture closed')
            self.sid = f.open_owned(self.db, '101', self.root/'new.json', self.review)
            self.cred = f.credential(self.root/'new.json')
            self.engine = u.Engine(self.db, self.desktop, self.sid)  # Deliberate no-op callback.
            self.approval = dict(authority=a.AUTHORITY, verdict='APPROVED',
                reviewer='generated independent fixture', test_reference='offline synthetic only',
                sha256=c.digest(a.__file__), scope=a.SCOPE, session=self.sid, main='101',
                account_binding_sha256=d.hash_value(self.db.get('target_account')))

        def capture_impl(self, db, sid, policy):
            if self.failure == 'capture': raise c.Error('generated capture failure')
            eid = uuid.uuid4().hex
            path = db.root/('generated_'+eid+'.png')
            path.write_bytes(b'\x89PNG\r\n\x1a\n'+struct.pack('>I', 13)+b'IHDR'+
                             struct.pack('>II', 800, 600))
            path.chmod(0o400)
            e = dict(id=eid, session=sid, path=str(path), crop=[0, 0, 800, 600],
                     owner=owner(self.popup), sha256=c.digest(path), at=time.time(), policy=policy)
            with db.tx():
                db.db.execute('INSERT INTO db12_capture VALUES(?,?,?)', (eid, sid, c.dumps(e)))
            return e

        def guard_impl(self, e):
            if self.drift: self.drift()
            if e['owner'] != owner(self.popup): raise c.Error('generated live topology drift')

        def input_impl(self, q, button=1):
            op = self.db.db.execute('SELECT * FROM db12_operation WHERE id=?',
                                    (q['operation'],)).fetchone()
            self.assertIsNotNone(op)
            self.assertIsNone(op['result'])
            self.assertEqual(json.loads(op['request']), q)
            self.assertFalse(self.db.db.in_transaction)  # Durable operation already committed.
            f.check_owned(self.db, self.cred, self.review)
            self.assertEqual(button, 1)
            self.inputs.append(copy.deepcopy(q))
            if self.failure == 'input': raise c.Error('generated possibly delivered click')
            if q['action'] == 'calibration-cube': self.popup = True

        def q(self, action, evidence=None):
            q = dict(operation=uuid.uuid4().hex, session=self.sid, action=action,
                     evidence=evidence, reviewer='parent-visual',
                     note='GENERATED offline review, not a production visual attestation', observed={})
            if action != 'calibration-capture':
                z = {key: True for key in a.VISUAL | a.FLAGS[action]}
                z.update(send_box=None if action == 'calibration-messages' else [500, 450, 50, 20],
                         send_absent=action == 'calibration-messages', unsafe_boxes=[])
                key = a.CONTROL[action]
                z[key] = [350, 300, 40, 20] if action == 'calibration-messages' else [200, 400, 20, 20]
                q.update(observed=z, target=z[key])
            return q

        def runq(self, q):
            return a.run(self.engine, q, self.cred, self.review, self.approval)

        def capture(self):
            return self.runq(self.q('calibration-capture'))['capture']

        def reject(self, q):
            count = len(self.inputs)
            with self.assertRaises((c.Error, ValueError, KeyError, TypeError)):
                self.runq(q)
            self.assertEqual(len(self.inputs), count)

        def protected(self):
            names = [row[0] for row in self.db.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
                if row[0] not in ('db12_session', 'db12_operation', 'db12_capture')]
            return {name: [tuple(row) for row in self.db.db.execute(
                        'SELECT * FROM '+name+(" WHERE k!='owned_lease'" if name == 'db12_state' else ''))]
                    for name in names}

        def test_full_path_and_honest_close_preserve_business_history(self):
            old_sessions = [tuple(x) for x in self.db.db.execute(
                'SELECT * FROM db12_session WHERE id!=?', (self.sid,))]
            protected = self.protected()
            e = self.capture()
            self.runq(self.q('calibration-messages', e['id']))
            e = self.capture()
            self.runq(self.q('calibration-cube', e['id']))
            e = self.capture()
            self.assertEqual(e['policy'], 'favorite')
            self.assertNotEqual(e['owner']['active'], e['owner']['main'])
            self.assertEqual([q['action'] for q in self.inputs],
                             ['calibration-messages', 'calibration-cube'])
            state = self.db.session(self.sid)
            self.assertEqual(state['stage'], 'calibration-only')
            self.assertTrue(all(state[k] is None for k in ('friend_id', 'oid', 'intent')))
            self.assertEqual(protected, self.protected())
            for action in ('select', 'send', 'rows', 'profile', 'cube', 'messages'):
                with self.assertRaises(c.Error):
                    self.engine.run(dict(self.q('calibration-capture'), action=action))
            result = f.close_owned(self.db, self.cred, 'generated panel remains open, no selection/send')
            self.assertTrue(result['closed']); self.assertIsNone(self.db.meta('lease'))
            self.assertTrue(self.popup)  # Lease close is not a UI dismiss.
            self.assertEqual(old_sessions, [tuple(x) for x in self.db.db.execute(
                'SELECT * FROM db12_session WHERE id!=?', (self.sid,))])
            self.assertEqual(protected, self.protected())

        def test_closed_vocabulary_and_geometry(self):
            e = self.capture()
            good = self.q('calibration-messages', e['id'])
            for action in ('send', 'select', 'row', 'scroll-down', 'copy-url', 'cancel', 'account-current'):
                self.reject(dict(good, action=action))
            for key, value in (('friend_id', 'not-an-identity'), ('main_active', True), ('id_box', [1, 1, 5, 5])):
                q = copy.deepcopy(good); q['observed'][key] = value; self.reject(q)
            for change in ('unsafe', 'target', 'outside', 'false-flag', 'send-overlap'):
                q = copy.deepcopy(good)
                if change == 'unsafe': q['observed']['unsafe_boxes'] = [q['target']]
                if change == 'target': q['target'] = [50, 50, 10, 10]
                if change == 'outside':
                    q['target'] = q['observed']['messages_box'] = [790, 590, 30, 30]
                if change == 'false-flag': q['observed']['opens_chat_only'] = False
                if change == 'send-overlap':
                    q['observed'].update(send_box=q['target'], send_absent=False)
                self.reject(q)
            self.assertEqual(self.inputs, [])

        def test_real_credential_and_capability_checks_despite_noop_engine_check(self):
            for key, value in (('session', uuid.uuid4().hex), ('sha256', '0'*64),
                               ('scope', 'send'), ('main', '999'), ('account_binding_sha256', '0'*64)):
                original = copy.deepcopy(self.approval)
                self.approval[key] = value; self.reject(self.q('calibration-capture'))
                self.approval = original
            self.cred['token'] += 'wrong'
            self.reject(self.q('calibration-capture'))

        def test_latest_and_under180_and_tampered_image(self):
            old = self.capture(); e = self.capture()
            self.reject(self.q('calibration-messages', old['id']))
            with patch.object(u.time, 'time', return_value=e['at']+180):
                self.reject(self.q('calibration-messages', e['id']))
            path = Path(e['path']); path.chmod(0o600); path.write_bytes(b'changed')
            self.reject(self.q('calibration-messages', e['id']))

        def test_stage_replay_capture_limit_and_popup_refusal(self):
            e = self.capture()
            self.reject(self.q('calibration-cube', e['id']))
            self.popup = True
            self.reject(self.q('calibration-messages', e['id']))
            self.popup = False
            # Failed guard is unknown and permanently blocks further addon calls.
            self.reject(self.q('calibration-capture'))

        def test_bounds_and_new_capture_required(self):
            e = self.capture()
            q = self.q('calibration-messages', e['id']); self.runq(q)
            self.reject(q)
            self.reject(self.q('calibration-cube', e['id']))
            for _ in range(5): self.capture()
            self.reject(self.q('calibration-capture'))
            e = self.db.session(self.sid)['latest']
            self.runq(self.q('calibration-cube', e))
            self.reject(self.q('calibration-cube', e))

        def test_ambiguous_input_stops_even_after_honest_close_new_session(self):
            e = self.capture(); self.failure = 'input'
            with self.assertRaises(c.Error): self.runq(self.q('calibration-messages', e['id']))
            self.assertEqual(len(self.inputs), 1)
            op = self.db.db.execute('SELECT result FROM db12_operation ORDER BY rowid DESC LIMIT 1').fetchone()
            self.assertEqual(json.loads(op[0])['status'], 'unknown')
            self.reject(self.q('calibration-capture'))
            f.close_owned(self.db, self.cred, 'unknown generated click; never replay')
            self.sid = f.open_owned(self.db, '101', self.root/'third.json', self.review)
            self.cred = f.credential(self.root/'third.json')
            self.engine = u.Engine(self.db, self.desktop, self.sid)
            self.approval['session'] = self.sid
            self.reject(self.q('calibration-capture'))

        def test_durable_pending_survives_end_failure(self):
            e = self.capture(); self.failure = 'input'
            with patch.object(self.db, 'end_operation', side_effect=OSError('generated commit failure')):
                with self.assertRaises(c.Error): self.runq(self.q('calibration-messages', e['id']))
            self.reject(self.q('calibration-capture'))
            result = f.close_owned(self.db, self.cred, 'generated durable pending; no replay')
            self.assertEqual(len(result['unresolved_operations']), 1)

        def test_full_no_unresolved_used_and_missing_schema_not_installed(self):
            with patch.object(r, 'no_unresolved', side_effect=c.Error('generated unresolved local send')) as check:
                self.reject(self.q('calibration-capture')); check.assert_called_with(self.db)
            self.db.db.execute('DROP TABLE db13_round_pair')
            with self.assertRaises(Exception): self.capture()
            self.assertIsNone(self.db.db.execute(
                "SELECT name FROM sqlite_master WHERE name='db13_round_pair'").fetchone())

        def test_cross_session_pending_and_unaccounted_send_block(self):
            q = self.q('calibration-capture'); q['session'] = 'f'*32
            oid = self.db.start_operation(q['session'], q)
            self.reject(self.q('calibration-capture'))
            with self.db.tx():
                self.db.db.execute('UPDATE db12_operation SET result=? WHERE id=?',
                                   (c.dumps({'status': 'done'}), oid))
            q = dict(self.q('calibration-capture'), action='send')
            self.db.start_operation(self.sid, q)
            self.reject(self.q('calibration-capture'))

        def test_owner_and_account_drift_after_guard_stop_before_input(self):
            e = self.capture()
            def drift():
                lease = self.db.meta('lease'); lease['hash'] = '0'*64
                with self.db.tx(): self.db.set_lease(lease)
            self.drift = drift
            self.reject(self.q('calibration-messages', e['id']))
            self.assertEqual(self.inputs, [])

        def test_source_guard_checks_real_pins(self):
            a.source_guard(self.engine)
            source = Path(r.__file__)
            raw = source.read_bytes()
            try:
                source.write_bytes(raw+b'\n# generated fixture drift\n')
                self.reject(self.q('calibration-capture'))
            finally: source.write_bytes(raw)

    if __name__ == '__main__': unittest.main()
```

- [ ] **Step 2: Run red.**

```bash
cd /tmp/wxview92/upgrade_20261010T1529
PYTHONDONTWRITEBYTECODE=1 python3 -B test_controller_db_nosend_calibration_20261013.py -v
```

Expected: nonzero with `ModuleNotFoundError: No module named 'controller_db_nosend_calibration_20261013'`. No production connections, screenshots or source edits occur.

- [ ] **Step 3: Write the complete addon below.**

```python
"""Session-local visual calibration only: capture, Messages once, cube once.

Not recipient, layout, article, round, or Send admission. Parent owns locks/open/
close and genuine independent exact-delta approval. No import-time live action.
"""
import copy
import json
import re
from pathlib import Path
import controller as c
import controller_db_x11_20261012 as o
import controller_db_store_20261012 as d
import controller_db_ui_20261012 as u
import controller_db_forward_20261012 as f
import controller_db_round_store_20261013 as r

AUTHORITY = 'msg_mv6nn1hjqjrlfm6nuy9'
SCOPE = 'selected-profile-messages-cube-no-send'
BASE_PINS = {
    'controller.py': 'e4ebe8c4ce4e58b7b274475e262f02b60383675e93cba344eb326fb6748e3455',
    'controller_db_x11_20261012.py': '252b8aa1edc7a64cc834f84ffb183ed42351eb41123f4c1ca79d6905de018846',
    'controller_db_store_20261012.py': '85f69b9d564b910d8e25daac29fe09ab73ddc7fb93362abd6eec3d9c26b7ca87',
    'controller_db_ui_20261012.py': '245d856488dd78d686bd5248aafd11f900be99cee46d710825c732eb31f87238',
    'controller_db_forward_20261012.py': 'c4b53a37a3c3e334176a4ebfff180b8547f39a691a6c100d85dd544b022ef8bb',
}
ROUND_PIN = '03373c7da947feb0461b2e8670dff802b5d38a033f9b6c212862c0a4a2011504'
VISUAL = {'current_frame_review', 'single_wechat_review', 'whole_frame_ownership'}
FLAGS = {
    'calibration-messages': {'current_selected_profile', 'messages_label', 'opens_chat_only'},
    'calibration-cube': {'same_chat_from_messages', 'one_to_one_chat', 'smiley_right_cube',
                         'opens_only', 'composer_empty', 'send_disabled'},
}
CONTROL = {'calibration-messages': 'messages_box', 'calibration-cube': 'cube_box'}
ACTIONS = {'calibration-capture', *CONTROL}
CAP_FIELDS = {'authority', 'verdict', 'reviewer', 'test_reference', 'sha256', 'scope',
              'session', 'main', 'account_binding_sha256'}


def source_guard(engine):
    root = Path(__file__).resolve().parent
    modules = [(name, module) for name, module in zip(BASE_PINS, (c, o, d, u, f))]
    modules.append(('controller_db_round_store_20261013.py', r))
    for name, module in modules:
        path = root/name
        expected = ROUND_PIN if module is r else BASE_PINS[name]
        c.need(path.is_file() and not path.is_symlink() and
               Path(module.__file__).resolve() == path and c.digest(path) == expected,
               'exact reviewed source composition required')
    c.need(type(engine) is u.Engine and type(engine.db) is d.LocalDB and
           type(engine.desktop) is u.Desktop, 'unchanged base Engine/LocalDB/Desktop required')
    c.need(not set(vars(engine)).intersection({'record', 'boundary', 'validate', 'run'}),
           'base Engine methods must not be replaced')


def shape(q):
    c.need(type(q) is dict and q.get('action') in ACTIONS, 'calibration action only')
    fields = {'operation', 'session', 'action', 'evidence', 'reviewer', 'note', 'observed'}
    if q['action'] in CONTROL: fields.add('target')
    c.need(set(q) == fields, 'closed calibration request required')
    for key in ('operation', 'session'):
        c.need(type(q[key]) is str and re.fullmatch(r'[0-9a-f]{32}', q[key]), 'UUID required')
    c.need(q['reviewer'] == 'parent-visual' and type(q['note']) is str and q['note'].strip(),
           'actual parent whole-image review required')
    z = q['observed']; a = q['action']
    if a == 'calibration-capture':
        c.need(z == {} and q['evidence'] is None, 'capture takes no target/evidence/observation')
        return
    c.need(type(q['evidence']) is str and bool(q['evidence']), 'fresh actual capture required')
    c.need(type(z) is dict and set(z) == VISUAL | FLAGS[a] |
           {CONTROL[a], 'send_box', 'send_absent', 'unsafe_boxes'}, 'closed visual observation required')
    u.flags(z, *(VISUAL | FLAGS[a]))
    c.rectangle(q['target']); c.rectangle(z[CONTROL[a]])
    c.need(q['target'] == z[CONTROL[a]], 'exact visible action control required')
    c.need(type(z['unsafe_boxes']) is list, 'explicit unsafe boxes required')
    for box in z['unsafe_boxes']:
        c.rectangle(box)
        c.need(u.disjoint(q['target'], box), 'target overlaps unsafe region')
    if z['send_box'] is None:
        c.need(a == 'calibration-messages' and z['send_absent'] is True,
               'only profile Messages permits explicitly absent Send')
    else:
        c.rectangle(z['send_box'])
        c.need(z['send_absent'] is False and u.disjoint(q['target'], z['send_box']),
               'navigation must be disjoint from actual Send')


def clear_operations(db, ownop=None, q=None):
    # Retain the FULL existing local send/orphan/operation check, with no exemptions.
    r.no_unresolved(db)
    for row in db.db.execute('SELECT * FROM db12_operation'):
        request = json.loads(row['request'])
        if row['id'] == ownop:
            c.need(request == q and row['session'] == q['session'] and row['result'] is None,
                   'exact own pending operation required')
            continue
        c.need(row['result'] is not None, 'global pending operation: stop, never reopen around it')
        if str(request.get('action', '')).startswith('calibration-'):
            c.need(json.loads(row['result']).get('status') == 'done',
                   'unknown calibration lineage: stop, never retry')


def checked(engine, q, cred, review, approval, ownop=None):
    source_guard(engine); shape(q)
    c.need(type(approval) is dict and set(approval) == CAP_FIELDS,
           'exact scoped independent addon review required')
    for key in ('reviewer', 'test_reference'):
        c.need(type(approval[key]) is str and approval[key].strip(), 'independent review reference required')
    c.need(approval['authority'] == AUTHORITY and approval['verdict'] == 'APPROVED' and
           approval['scope'] == SCOPE and approval['sha256'] == c.digest(__file__),
           'exact addon no-Send approval required')
    f.credential_value(cred)
    c.need(cred['session'] == engine.sid == q['session'] == approval['session'],
           'original exact session credential required')
    state = f.check_owned(engine.db, cred, review)  # Never trust Engine.check alone.
    engine.check()
    c.need(state == f.check_owned(engine.db, cred, review), 'owner callback changed state')
    c.need(review['files'] == BASE_PINS and not state['closed'] and state['steps'] < 12 and
           state['main'] == approval['main'] == engine.desktop.main_id,
           'exact base review/main/bounded session required')
    c.need(not any(state.get(k) for k in ('friend_id', 'oid', 'intent', 'bootstrap',
                                        'direct_request', 'round_id', 'coverage_binding', 'copied_url')),
           'no recipient, article, round or send authority in calibration')
    for table in ('db12_intent', 'db13_round_intent'):
        c.need(engine.db.db.execute('SELECT 1 FROM '+table+' WHERE session=?',
                                   (engine.sid,)).fetchone() is None, 'session intent history prohibited')
    clear_operations(engine.db, ownop, q)
    account = engine.db.get('target_account')
    source = engine.db.get('local_account_source')
    c.need(account and source and account['account'] == source['account'] == 'gaozhi-xinshu' and
           d.hash_value(account) == approval['account_binding_sha256'], 'existing current account binding required')
    cal = state.get('no_send_calibration')
    if cal is None:
        c.need(q['action'] == 'calibration-capture' and state['stage'] == 'start' and
               state['steps'] == 0 and state['latest'] is None and state['recoveries'] == 0,
               'fresh legally opened pristine session only')
        c.need(engine.db.db.execute('SELECT 1 FROM db12_operation WHERE session=? AND id!=?',
                                   (engine.sid, ownop or '')).fetchone() is None,
               'do not reuse ordinary/closed/attempted session history')
        cal = dict(scope=SCOPE, approval=d.hash_value(approval), phase='selected-profile', captures=0)
    else:
        c.need(state['stage'] == 'calibration-only' and set(cal) == {'scope', 'approval', 'phase', 'captures'} and
               cal['scope'] == SCOPE and cal['approval'] == d.hash_value(approval) and
               cal['phase'] in ('selected-profile', 'messages-returned', 'cube-returned') and
               type(cal['captures']) is int and 1 <= cal['captures'] <= 6,
               'original bounded calibration scope required')
        for row in engine.db.db.execute('SELECT id,request FROM db12_operation WHERE session=?', (engine.sid,)):
            c.need(json.loads(row['request']).get('action') in ACTIONS,
                   'no mixing calibration with ordinary Engine actions')
    if q['action'] == 'calibration-capture':
        c.need(cal['captures'] < 6, 'capture budget exhausted; close honestly')
        return state, cal, None
    expected = 'selected-profile' if q['action'] == 'calibration-messages' else 'messages-returned'
    c.need(cal['phase'] == expected, 'one Messages then one cube only')
    e = engine.record(q['evidence'], state)
    validate_capture(engine, e, state, account)
    owner = e['owner']; z = q['observed']; main = c.rect(owner['main'])
    c.need(owner['active'] == owner['main'], 'actual active main required; do not fabricate focus')
    c.need(c.inside(q['target'], main) and c.inside(q['target'], e['crop']), 'visible control outside main/root')
    if z['send_box'] is not None:
        c.need(c.inside(z['send_box'], main) and c.inside(z['send_box'], e['crop']), 'actual Send bounds required')
    c.need(all(c.inside(box, e['crop']) for box in z['unsafe_boxes']), 'unsafe regions outside root')
    return state, cal, e


def validate_capture(engine, e, state, account):
    c.need(e['owner']['main']['id'] == state['main'] and e['session'] == engine.sid,
           'actual capture main/session changed')
    c.need(o.same_main(account['owner'], e['owner']), 'account process/main changed')
    if state.get('owner_anchor'):
        c.need(o.same_main(state['owner_anchor'], e['owner']), 'session process/main changed')
    c.need(c.inside(c.rect(e['owner']['main']), e['crop']) and
           c.inside(c.rect(e['owner']['active']), e['crop']), 'complete actual windows required')


def run(engine, q, cred, review, approval):
    """Caller holds f.locked; close with original f.close_owned, never a UI cancel."""
    q, cred, review, approval = copy.deepcopy((q, cred, review, approval))
    state, cal, e = checked(engine, q, cred, review, approval)
    oid = engine.db.start_operation(engine.sid, q)
    try:
        c.need(checked(engine, q, cred, review, approval, oid) == (state, cal, e),
               'state changed after durable operation')
        changed = copy.deepcopy(state)
        nextcal = copy.deepcopy(cal)
        if q['action'] == 'calibration-capture':
            policy = 'favorite' if cal['phase'] == 'cube-returned' else 'profile'
            captured = engine.desktop.capture(engine.db, engine.sid, policy)
            changed.update(latest=captured['id'], owner_anchor=captured['owner'])
            # Authenticate newly created immutable evidence without pretending it was preexisting state.
            actual = engine.record(captured['id'], changed)
            c.need(actual == captured and actual['policy'] == policy, 'actual durable capture mismatch')
            validate_capture(engine, actual, state, engine.db.get('target_account'))
            nextcal['captures'] += 1
            result = dict(capture=actual, scope=SCOPE)
        else:
            engine.desktop.guard(e)
            c.need(checked(engine, q, cred, review, approval, oid) == (state, cal, e),
                   'guard changed ownership/state/evidence')
            engine.boundary(q, state, e)
            c.need(checked(engine, q, cred, review, approval, oid) == (state, cal, e),
                   'final real-owned input boundary changed')
            engine.desktop.input(q, 1)
            changed['latest'] = None
            nextcal['phase'] = 'messages-returned' if q['action'] == 'calibration-messages' else 'cube-returned'
            result = dict(action=q['action'], scope=SCOPE)
        # Post-call failure is unknown, never a successful navigation claim or retry grant.
        c.need(checked(engine, q, cred, review, approval, oid) == (state, cal, e),
               'ownership/account/state drift after desktop call')
        clear_operations(engine.db, oid, q)
        changed.update(stage='calibration-only', no_send_calibration=nextcal, steps=state['steps']+1)
        engine.db.end_operation(oid, dict(status='done', value=result), changed)
        return result
    except BaseException as exc:
        failed = copy.deepcopy(state)
        failed.update(stage='calibration-only', latest=None, steps=state['steps']+1,
                      no_send_calibration=copy.deepcopy(cal))
        try:
            engine.db.end_operation(oid, dict(status='unknown', error_type=type(exc).__name__), failed)
        except BaseException:
            pass  # Durable NULL operation is a stop too; no rollback/refund/retry.
        raise
```

- [ ] **Step 4: Run green and existing targeted no-side-effect regression.**

```bash
cd /tmp/wxview92/upgrade_20261010T1529
PYTHONDONTWRITEBYTECODE=1 python3 -B test_controller_db_nosend_calibration_20261013.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -B test_controller_db_account_current_20261013.py -v
```

Expected: first command reports `Ran 12 tests` and `OK`; second command reports its existing account-current generated fixture suite `OK`. Each self-contained test entry creates a temporary exact-composition subprocess and deletes it. Do not run a broad discovery against the stale root UI. If an independently changing source pin causes failure, stop and report exact drift instead of changing another source or silently replacing the pin.

- [ ] **Step 5: Verify static artifact boundaries and report hashes, not production approval.**

```bash
cd /tmp/wxview92/upgrade_20261010T1529
python3 -B - <<'PY'
import ast
from pathlib import Path
p = Path('controller_db_nosend_calibration_20261013.py')
tree = ast.parse(p.read_text())
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        assert node.func.attr not in {'reserve', 'install', 'borrow', 'executescript',
                                      'clipboard_write', 'clipboard_read', 'put',
                                      'save_current_target_coverage'}
print('addon parses; no schema, business-state, clipboard or Send-admission calls')
PY
sha256sum controller_db_nosend_calibration_20261013.py test_controller_db_nosend_calibration_20261013.py
```

Expected: static message as above and two SHA256 lines. Return actual test results and exact addon/test hashes to the parent for independent review. Do not commit, stage, deploy, open a live session, issue a real approval, read DB/private images, or run runtime entrypoints.

**Verification coverage:** Positive real-API fixture flow; genuine `f.check_owned` with deliberately no-op `Engine.check`; exact source drift; closed action/field/control schemas; Send/unsafe overlap and bounds; latest/strict180/immutable capture; actual owner drift; no old recipient or coverage writes; single-use Messages/cube; six-capture cap; operation durable before click; failure/NULL operation unknown-stop across honest close/new session; full unchanged no-unresolved invocation, unaccounted Send and missing-schema stops; lease close retains panel reality. Test images and reviews are unmistakably generated fixtures, never production evidence. Real on-screen control semantics, actual account continuity, deployment, and final layout admission remain parent-only live checks, not claimed by tests.

## Self-check before handoff

- SPEC COVERAGE: One Task covers the full requested minimal path, honest closure boundary, real ownership, strict180, durable-before-input, unknown-stop, pinned independent capability, and no business-history writes.
- COMPLETENESS: Complete two-file contents and directly runnable red/green/static commands are included. No existing source edit or implicit runtime shim is required.
- CROSS-TASK: Single task; API/type names are identical in code/tests. Session credentials use actual `f` APIs, not an invented Session class. No dependency on changing DirectEngine/RoundUI is introduced.
- WEAK EXECUTOR: Most complex part (boundary/journal/capture authentication) is complete code; temporary exact UI composition and generated DB/owner fixtures are supplied. Production setup/approval is explicitly not a writer step.
- NON-GOALS: All inputs except two named left-click controls are excluded. Neither ordinary sender nor detector pipeline is modified, and selected-profile visual navigation is explicitly not identity/send authority.
- CONCURRENCY: One task modifies only its two new files; no intersection with underway runtime/detector work. Changes to read-only prerequisite pins are reported, never overwritten.

## Task Index

| ID | Title | Files | Verification | Depends_on |
|---|---|---|---|---|
| 1 | Bounded no-Send selected-profile calibration addon and offline tests | /tmp/wxview92/upgrade_20261010T1529/controller_db_nosend_calibration_20261013.py; /tmp/wxview92/upgrade_20261010T1529/test_controller_db_nosend_calibration_20261013.py | cd /tmp/wxview92/upgrade_20261010T1529 && PYTHONDONTWRITEBYTECODE=1 python3 -B test_controller_db_nosend_calibration_20261013.py -v | — |
