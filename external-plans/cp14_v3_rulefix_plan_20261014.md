# CP14 v3：仅精确历史恢复与 pre-reserve 时效拒绝的最小修正

> Steps use checkbox (`- [ ]`) syntax for tracking。只实施这两个本地候选任务，不运行现场恢复。

**Goal:** 按用户 `msg_mv7ed5acudo9emknic`（2026-10-14 08:54+08，16:26/16:33 继续，manager 17:52 再确认）让可核清、未 reserve、未 native 的时效拒绝不永久废掉 v3 scope；通过合法 append-only amendment 接续当前已停的 v3，旧 closed SID 与全部旧事实保持原样。

**Architecture:** 保持预算源码 `fcf1f91f…` 字节不变；新增一个精确 v3 recovery 模块及 21-source amendment。producer 只把预算入口改经该模块，并在原 `original_frame` 上将独立通过原 immutable/owner/account/geometry 验证的纯年龄拒绝标记为专用异常；只有 reserve 前再次核清完全零变化时返回明确 `refused-pre-reserve-expiry`，其余错误仍 append-only hard halt。不修改原 decision 的 `files`；用 amendment 将原 20 map 的 producer 唯一替换及新增模块绑定到当前实际 21 map。

**Tech Stack:** Python 3 标准库、现有 SQLite `BEGIN IMMEDIATE`/savepoint 与 append-only triggers、现有 `LocalDB`/`Engine.record`/owner/authentication；测试只用临时合成 SQLite 与隔离 21-source 副本。无新库、服务、CLI、网络或第二生产账本。

**Project conventions / conflict resolution:** 已先读 R/CLAUDE.md、R/AGENTS.md。遵循现有 `c.need`、`budget._json`、`d.hash_value`、精确源码闭包/模块 origin、唯一 ledger、完整 `r.no_unresolved`、局部 unittest，不重跑无关完整套。项目文档中的“注册后准入失败永久停止”已被本次指定的最新用户/manager 输入在本次极窄范围取代；旧 v1 protocol 与旧未批准实现封存，只作为结构参考，不复制部署。实现子任务禁止 SSH/UI/native/network/生产 DB/secret/Git；父负责文档更正、独审、现场读审、placement 与后续新 SID。

**Tasks Overview:**
1. 两个新文件：精确历史 amendment、有效 stopped/report 与不可退款预算 wrappers；本地纯 SQLite 测试。
2. 两个新文件：从已受审 SOURCE 逐字节复制 producer 后做最小接线/专用时效非 fatal 分支；新的定向隔离测试，不重跑旧 34 全套。

## 固定输入与不可越界的验收事实

- R=`/tmp/wxview92/upgrade_20261010T1529`；受审 SOURCE=`/tmp/wxview92/cp14_v3_evidence_20261014`。候选输出目录 C=`/tmp/wxview92/cp14_v3_rulefix_20261014`（不可覆写 SOURCE）。
- 原 producer SHA256=`0f693073a2c33b2dff2f5ed6438c30f349f7dff5c84a514d73e23ce7ca66f7ad`；原 budget SHA256=`fcf1f91f334bdf2865956ffb22b4fdba0d840658a252f58b2a808c09c4dab760`。
- 原 decision canonical SHA256=`019f0bf6ca0f3c66be74add282ad9d771cd920b0b90bdd128e12bda4f72c5164`。它及原 decision JSON 文件字节完全不改、不另行 register。
- scope 仍为 `contacts_producer_20261014_v3`；旧 SID=`b42a4d3c2b1b490e8c33b1eb4833cfca`；原 stop 完整前像 `{scope: contacts_producer_20261014_v3, reason: Error, at: 1791971065.2647989}` 不改；旧 SID closed_at=`1791971065.269438`，steps=5，latest=null，不复活。
- 5 done：cp-account-history / cp-capture / cp-review / cp-scroll-up / cp-capture。消耗=`5/2/1/0/0/1`；余量=`155/78/47/24/1/2`（operations/captures/notches/rows/entry/SIDs）。
- 失败 request=`7fbd79579b32420db8c59364224fda26`，canonical request hash=`84d210bbcdd263ec13718999ca956398ce490426141cbad4a88a5472b62b96a2`；没有 reservation、没有 journal/input。
- terminal audit `/tmp/wxview92/cp14_v3_terminal_readonly_1791971205137650989.jsonl` SHA256=`642b1a3347b29ecd6e4fc5814dca6c4d3293e5683e7601f94f78807f7745d728`；trace `/tmp/wxview92/cp14_v3_run_1791971061164856091.jsonl.stderr` SHA256=`e4fea3f3f649b43ad307e0cf66587db6562975fe40726533a8decb52276bbc64`。trace 已定位 SOURCE producer:530→395→310→UI:228，非 native、reserve:556 前。无需重诊断。
- 本 plan 选择 **21 map**；budget 与其余原 18 源码不变。未知/failed/reserved 不明操作仍硬停。未改变 180/360、CAPS、去重、journal、owner、account、source 与 full `no_unresolved`。
- 最小新 hard-halt 表必要性：旧 budget.stop 是单行 `INSERT OR IGNORE`，现有 Error 行不能再记录未来错误；若只豁免该行，未来 native 错误会被一并掩盖。故增加 `cp14v3_halt`，仅 INSERT，任何行无条件阻断。

### Task 1: 精确 v3 amendment 与保留预算源码的 recovery wrappers

**Objective:** 创建仅适用当前历史 stop 的 append-only amendment 与 hard-halt 表；所有后续 admisssion/reservation仍使用同一四表、同一 journal、原 CAPS 与已花计数。新模块不得认证新的视觉/UI事实。

**Context from:** SOURCE budget:77–188 是计数、healthy、admit、reserve 的完整原实现；SOURCE producer:81–90 checkpoint、100–115 actual eight legacy table map、171–181 decision_value、199–280 old_history。Task 2 会在 producer 中接线。旧 decision shape 与 old_history 函数不改，只在 source-map equality 处用合法 amendment 接续。

**Non-goals:** 不改 budget 源码；不部署/读生产库；不生成或操作 secret；不新 scope/v4；不修改旧 decision/stop/admission/reservation/session；不把所有 Error 变 nonfatal；不使用旧 v1 implementation；不减少任何守卫或重置余量。

**Files (≤2):**
- Create: `/tmp/wxview92/cp14_v3_rulefix_20261014/controller_db_contacts_v3_recovery_20261014.py`
- Create: `/tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_recovery.py`

**Steps:**

- [ ] **1. 先创建以下定向测试文件。** 它只导入未改的纯 budget；producer 用显式模拟 seam，所有 DB 都是内存合成。`record_value` 的生产 exact-history guard 在 Task 2 验证真实拒绝/绑定，不以这些 mock 当现场认证。

```python
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from contextlib import contextmanager
from unittest.mock import patch

HERE = Path(__file__).absolute().parent
SOURCE = Path('/tmp/wxview92/cp14_v3_evidence_20261014')
spec = importlib.util.spec_from_file_location(
    'controller_db_contacts_budget_v3_20261014',
    SOURCE/'controller_db_contacts_budget_v3_20261014.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
sys.modules[spec.name] = b
sys.path.insert(0, str(HERE))
import controller_db_contacts_v3_recovery_20261014 as a

class DB:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          CREATE TABLE db12_operation(id TEXT PRIMARY KEY,session TEXT,
            request TEXT,started REAL,result TEXT);
          CREATE TABLE db12_session(id TEXT PRIMARY KEY,data TEXT);
          CREATE TABLE db12_capture(id TEXT PRIMARY KEY,session TEXT,data TEXT);
          CREATE TABLE db12_intent(id TEXT PRIMARY KEY,session TEXT);
        ''')
        b.install(self)
        with self.tx():
            self.db.execute('INSERT INTO cp14v3_decision VALUES(?,?)',
                            (b.SCOPE, b._json({'files': {}})))
    @contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
    def session(self, sid):
        row = self.db.execute('SELECT data FROM db12_session WHERE id=?', (sid,)).fetchone()
        return json.loads(row[0]) if row else None
    def save_session(self, sid, state):
        self.db.execute('INSERT OR REPLACE INTO db12_session VALUES(?,?)',
                        (sid, b._json(state)))

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.db = DB()
        self.addCleanup(self.db.db.close)
        self.sid = 'a'*32
        self.review = {'session': self.sid}
        self.decision = {'files': {}}
        with self.db.tx():
            self.db.save_session(self.sid, {'closed': False, 'steps': 0,
                'latest': None, 'unresolved_operations': [], 'unresolved_intents': []})
        self.tables()
    def tables(self):
        with self.db.tx():
            a._tables(self.db)
    def approved(self):
        with self.db.tx():
            self.db.db.execute('INSERT INTO cp14v3_rule_amendment VALUES(?,?)',
                              (b.SCOPE, b._json({'synthetic': True})))
            self.db.db.execute('INSERT INTO cp14v3_stop VALUES(?,?,?)',
                              (b.SCOPE, 'Error', 1791971065.2647989))
        m = patch.object(a, 'record_value', return_value={'synthetic': True})
        m.start()
        self.addCleanup(m.stop)
    def q(self, oid='b'*32):
        return {'operation': oid, 'session': self.sid, 'action': 'cp-capture'}
    def test_no_amendment_preserves_stop(self):
        b.stop(self.db, 'Error')
        self.assertTrue(a.report(self.db)['stopped'])
        with self.assertRaises(RuntimeError):
            a.healthy(self.db)
    def test_wrappers_use_same_journal_and_do_not_refund(self):
        self.approved()
        with self.db.tx():
            a.admit(self.db, self.sid, self.decision, self.review)
            changed = a.reserve(self.db, self.q(), self.db.session(self.sid))
        self.assertEqual(changed['steps'], 1)
        self.assertEqual(b.report(self.db)['consumed']['operations'], 1)
        self.assertEqual(b.report(self.db)['remaining']['captures'], 79)
        self.assertTrue(b.report(self.db)['stopped'])
        self.assertFalse(a.report(self.db)['stopped'])
        self.assertTrue(a.report(self.db)['historical_stopped'])
        with self.assertRaises(RuntimeError):
            a.healthy(self.db)
        with self.db.tx():
            self.db.db.execute('UPDATE db12_operation SET result=? WHERE id=?',
                              (b._json({'status': 'done'}), 'b'*32))
        a.healthy(self.db)
        with self.db.tx(), self.assertRaises(RuntimeError):
            a.reserve(self.db, self.q(), changed)
        self.assertEqual(b.report(self.db)['consumed']['operations'], 1)
    def test_unknown_and_failed_remain_hard_blockers(self):
        self.approved()
        with self.db.tx():
            a.admit(self.db, self.sid, self.decision, self.review)
            a.reserve(self.db, self.q(), self.db.session(self.sid))
        for status in ('unknown', 'failed'):
            with self.db.tx():
                self.db.db.execute('UPDATE db12_operation SET result=? WHERE id=?',
                                  (b._json({'status': status}), 'b'*32))
            with self.assertRaises(RuntimeError):
                a.healthy(self.db)
    def test_new_halt_is_terminal_even_with_amendment(self):
        self.approved()
        old = tuple(self.db.db.execute('SELECT * FROM cp14v3_stop').fetchone())
        a.stop(self.db, 'reserved input failed: Error')
        self.assertEqual(old, tuple(self.db.db.execute('SELECT * FROM cp14v3_stop').fetchone()))
        self.assertTrue(a.report(self.db)['stopped'])
        with self.assertRaises(RuntimeError):
            a.healthy(self.db)
    def test_append_only_new_tables(self):
        self.approved()
        a.stop(self.db, 'hard failure')
        for table in ('cp14v3_rule_amendment', 'cp14v3_halt'):
            for verb in ('UPDATE', 'DELETE'):
                sql = ('UPDATE '+table+' SET scope=scope') if verb == 'UPDATE' else 'DELETE FROM '+table
                with self.assertRaises(sqlite3.IntegrityError), self.db.tx():
                    self.db.db.execute(sql)
    def test_closed_sid_never_admitted(self):
        self.approved()
        with self.db.tx():
            self.db.save_session(self.sid, {'closed': True, 'steps': 0})
        with self.assertRaises(RuntimeError), self.db.tx():
            a.admit(self.db, self.sid, self.decision, self.review)
        self.assertEqual(b.report(self.db)['consumed']['sessions'], 0)
    def test_no_record_source_transition_denied(self):
        with self.assertRaises(RuntimeError):
            a.composition_ok(self.db, {'files': {}}, {'new': 'build'})
    def test_new_sids_share_remaining_sessions_and_never_reopen(self):
        self.approved()
        for index in range(3):
            sid=('%032x' % (index+1))
            with self.db.tx():
                self.db.save_session(sid,{'closed':False,'steps':0,'latest':None,
                    'unresolved_operations':[],'unresolved_intents':[]})
                a.admit(self.db,sid,self.decision,{'session':sid})
                self.db.save_session(sid,{'closed':True,'steps':0,'latest':None,
                    'unresolved_operations':[],'unresolved_intents':[]})
            self.assertEqual(a.report(self.db)['remaining']['sessions'],2-index)
        with self.assertRaises(RuntimeError),self.db.tx():
            a.admit(self.db,'%032x' % 4,self.decision,{'session':'new'})
        with self.assertRaises(RuntimeError),self.db.tx():
            a.admit(self.db,'%032x' % 1,self.decision,{'session':'closed'})
        self.assertEqual(a.report(self.db)['consumed']['sessions'],3)

    def test_atomic_reserve_failure_rolls_back(self):
        self.approved()
        with self.db.tx():
            a.admit(self.db, self.sid, self.decision, self.review)
        with patch.object(self.db, 'save_session', side_effect=RuntimeError('save failed')):
            with self.db.tx():
                with self.assertRaises(RuntimeError):
                    a.reserve(self.db, self.q(), self.db.session(self.sid))
        self.assertEqual(b.report(self.db)['consumed']['operations'], 0)
        self.assertIsNone(self.db.db.execute('SELECT 1 FROM db12_operation').fetchone())

if __name__ == '__main__':
    unittest.main(verbosity=2)
```

- [ ] **2. 红灯。**

```bash
python3 -I -B /tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_recovery.py
```

预期非零，缺少新 recovery module。不要运行旧 runner 或任何现场脚本。

- [ ] **3. 创建完整 recovery 模块。** 此代码 lazy-import producer（只在被调用时），保持 21-source 闭包；不得 monkeypatch budget/global guards。`admit`/`reserve` 是原 budget 函数精确复制，仅调用本模块 healthy，表名/计数/savepoint/journal全不改。下方完整模块的最后两函数代码在本 task Step 4 中给出并须顺接同一文件。

```python
"""Exact v3 zero-reserve expiry amendment; no native/UI/CLI or automatic grant."""
import copy
import hashlib
import json
import re
import time
import controller_db_contacts_budget_v3_20261014 as budget

SCOPE = budget.SCOPE
AUTHORITY = 'msg_mv7ed5acudo9emknic'
DECIDED_AT = '2026-10-14T08:54+08'
HIST_SID = 'b42a4d3c2b1b490e8c33b1eb4833cfca'
FAILED_REQUEST = '7fbd79579b32420db8c59364224fda26'
DECISION_SHA = '019f0bf6ca0f3c66be74add282ad9d771cd920b0b90bdd128e12bda4f72c5164'
PRODUCER = 'controller_db_contacts_producer_20261014.py'
MODULE = 'controller_db_contacts_v3_recovery_20261014.py'
BUDGET = 'controller_db_contacts_budget_v3_20261014.py'
OLD_PRODUCER = '0f693073a2c33b2dff2f5ed6438c30f349f7dff5c84a514d73e23ce7ca66f7ad'
OLD_BUDGET = 'fcf1f91f334bdf2865956ffb22b4fdba0d840658a252f58b2a808c09c4dab760'
STOP = {'scope': SCOPE, 'reason': 'Error', 'at': 1791971065.2647989}
JOURNAL_SHA = '2e215c04fbebabcc2443abd65bf357ded08dba8fbe6100895e7d4c71070071bd'
CAPTURES_SHA = 'df8f21e4275237e166ef2433b1da29ceb1d7647a30eae6eb8a86de0cfb37a739'
FAILED_REQUEST_SHA = '84d210bbcdd263ec13718999ca956398ce490426141cbad4a88a5472b62b96a2'
EVIDENCE = {
    'terminal_sha256': '642b1a3347b29ecd6e4fc5814dca6c4d3293e5683e7601f94f78807f7745d728',
    'trace_sha256': 'e4fea3f3f649b43ad307e0cf66587db6562975fe40726533a8decb52276bbc64',
    'classification': 'verified-pre-reserve-non-native-expiry',
    'failed_request_sha256': FAILED_REQUEST_SHA,
}
CONSUMED = {'operations': 5, 'captures': 2, 'scroll_notches': 1,
            'full_row_selections': 0, 'contacts_entries': 0, 'sessions': 1}
FIELDS = {'kind', 'authority', 'decided_at', 'scope', 'verdict', 'reviewer',
          'test_reference', 'files', 'original_decision_sha256',
          'original_decision_data_sha256', 'stop_preimage', 'baseline',
          'legacy_scope_tables', 'historical_session_sha256', 'evidence',
          'account_binding_sha256', 'environment', 'db_identity', 'display', 'at'}
_need = budget._need
_json = budget._json
_transaction = budget._transaction
_open_state = budget._open_state
CAPS = budget.CAPS
KINDS = budget.KINDS


def _p():
    import controller_db_contacts_producer_20261014 as p
    return p


def _exists(db, table):
    return db.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                         (table,)).fetchone() is not None


def _tables(db):
    _transaction(db)
    db.db.execute('CREATE TABLE cp14v3_rule_amendment('
                  'scope TEXT PRIMARY KEY REFERENCES cp14v3_decision(scope),'
                  'data TEXT NOT NULL)')
    db.db.execute('CREATE TABLE cp14v3_halt('
                  'scope TEXT PRIMARY KEY REFERENCES cp14v3_decision(scope),'
                  'reason TEXT NOT NULL,at REAL NOT NULL)')
    for table in ('cp14v3_rule_amendment', 'cp14v3_halt'):
        for verb in ('UPDATE', 'DELETE'):
            db.db.execute('CREATE TRIGGER '+table+'_'+verb.lower()+' BEFORE '+verb+
                          ' ON '+table+" BEGIN SELECT RAISE(ABORT,'cp14v3 append-only'); END")


def _registered(db):
    row = db.db.execute('SELECT data FROM cp14v3_decision WHERE scope=?', (SCOPE,)).fetchone()
    _need(row is not None, 'original registered v3 decision required')
    p = _p()
    decision = json.loads(row[0])
    _need(p.d.hash_value(decision) == DECISION_SHA, 'exact original v3 decision required')
    return row[0], decision


def _stop(db):
    row = db.db.execute('SELECT scope,reason,at FROM cp14v3_stop WHERE scope=?', (SCOPE,)).fetchone()
    _need(row is not None and dict(row) == STOP, 'exact original v3 stop preimage required')
    return dict(row)


def _baseline(db):
    p = _p()
    excluded = [row[0] for row in db.db.execute('SELECT sid FROM cp14v3_admission')]
    # One legitimate open-owned SID may precede admission; subsequent checks in
    # producer authenticate it and reject adoption of any pre-admission work.
    lease = db.meta('lease')
    if lease:
        _need(type(lease) is dict and type(lease.get('owner')) is str
              and re.fullmatch(r'db12:[0-9a-f]{32}', lease['owner']), 'exact sole lease owner')
        excluded.append(lease['owner'][5:])
    return p.checkpoint(db, excluded)


def _history(db):
    p = _p()
    state = db.session(HIST_SID)
    p.cal.closed_authority(db, HIST_SID, state, db.get('target_account')['owner']['main']['id'])
    _need(state['opened_at'] == 1791970415.0265985
          and state['closed_at'] == 1791971065.269438 and state['steps'] == 5
          and state['close_reason'] == 'V3 actual error; preserve facts, no retry.'
          and state['main'] == '39845906'
          and state['latest'] is None and state['unresolved_operations'] == []
          and state['unresolved_intents'] == [], 'exact honestly closed v3 SID required')
    admission = db.db.execute('SELECT scope,data FROM cp14v3_admission WHERE sid=?', (HIST_SID,)).fetchone()
    _need(admission is not None and admission['scope'] == SCOPE
          and p.d.hash_value(json.loads(admission['data']))
          == 'b7ea5785f38688873b76d8b309cc86d9833e31d30c2891b300ecb38953292f07',
          'original historical SID review bytes/value binding required')
    operations = [dict(row) for row in db.db.execute(
        'SELECT * FROM db12_operation WHERE session=? ORDER BY rowid', (HIST_SID,))]
    captures = [dict(row) for row in db.db.execute(
        'SELECT * FROM db12_capture WHERE session=? ORDER BY id', (HIST_SID,))]
    _need(p.d.hash_value(operations) == JOURNAL_SHA and p.d.hash_value(captures) == CAPTURES_SHA,
          'exact five done journal/two capture preimages changed')
    reservations = list(db.db.execute(
        'SELECT * FROM cp14v3_reservation WHERE sid=?', (HIST_SID,)))
    _need(len(reservations) == len(operations) == 5, 'exact five spent reservations required')
    for row in operations:
        q = json.loads(row['request'])
        p.qvalue(q)
        end = json.loads(row['result'])
        match = next((x for x in reservations if x['operation'] == row['id']), None)
        _need(match is not None and match['sid'] == HIST_SID
              and match['kind'] == q['action'] and match['at'] == row['started']
              and json.loads(match['request']) == q and q['operation'] == row['id']
              and q['session'] == HIST_SID and end['status'] == 'done',
              'exact done scope journal/reservation binding required')
    _need(db.db.execute('SELECT 1 FROM db12_intent WHERE session=?', (HIST_SID,)).fetchone() is None,
          'no actual Send work in historical observation')
    for table, column in (('db12_operation', 'id'), ('cp14v3_reservation', 'operation')):
        _need(db.db.execute('SELECT 1 FROM '+table+' WHERE '+column+'=?',
                            (FAILED_REQUEST,)).fetchone() is None,
              'failed request must have zero journal and zero reservation')
    safe = dict(state)
    safe.pop('lease', None)
    return p.d.hash_value(safe)


def _composition(original, files):
    _need(type(original) is dict and len(original) == 20
          and original.get(PRODUCER) == OLD_PRODUCER and original.get(BUDGET) == OLD_BUDGET,
          'original exact 20 map required')
    _need(type(files) is dict and set(files) == set(original) | {MODULE}
          and len(files) == 21, 'amended exact 21 map required')
    for name, digest in files.items():
        _need(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'exact SHA256 source map')
        if name not in (PRODUCER, MODULE):
            _need(digest == original[name], 'immutable source pin changed: '+name)


def record_value(db, record=None):
    if record is None:
        _need(_exists(db, 'cp14v3_rule_amendment'), 'legal v3 rule amendment required')
        row = db.db.execute('SELECT data FROM cp14v3_rule_amendment WHERE scope=?', (SCOPE,)).fetchone()
        _need(row is not None, 'legal v3 rule amendment required')
        record = json.loads(row[0])
    p = _p()
    _need(type(record) is dict and set(record) == FIELDS, 'closed exact v3 amendment')
    raw, original = _registered(db)
    _need(record['kind'] == 'exact-v3-pre-reserve-expiry-amendment'
          and record['authority'] == AUTHORITY and record['decided_at'] == DECIDED_AT
          and record['scope'] == SCOPE and record['verdict'] == 'APPROVED'
          and p.cal.text(record['reviewer']) and p.cal.text(record['test_reference']),
          'explicit independently reviewed user amendment required')
    _need(record['original_decision_sha256'] == DECISION_SHA
          and record['original_decision_data_sha256'] == hashlib.sha256(raw.encode()).hexdigest()
          and record['stop_preimage'] == _stop(db), 'original decision bytes/stop changed')
    _composition(original['files'], record['files'])
    _need(record['files'] == p.build(), 'exact reviewed amended source composition required')
    _need(record['baseline'] == original['baseline'] == _baseline(db), 'original scope-excluded baseline changed')
    p.sealed_legacy_tables(db, original)
    _need(record['legacy_scope_tables'] == original['legacy_scope_tables'] == p.LEGACY_TABLES,
          'actual eight legacy tables changed')
    _need(record['historical_session_sha256'] == _history(db) and record['evidence'] == EVIDENCE,
          'exact verified historical refusal binding required')
    _need(record['account_binding_sha256'] == original['account_binding_sha256']
          == p.d.hash_value(db.get('target_account'))
          and record['environment'] == original['environment'] == p.f.session_environment(db)
          and record['db_identity'] == original['db_identity'] == list(db.inode)
          and record['display'] == original['display'] == p.os.environ.get('DISPLAY') == ':1',
          'unchanged actual account/environment/DB/display required')
    _need(type(record['at']) in (int, float) and record['at'] >= state_closed_at(),
          'finite amendment after historical honest close required')
    _json(record)
    return record


def state_closed_at():
    return 1791971065.269438


def make_record(db, approval):
    """Parent uses only after external exact-delta approval; no automatic approval."""
    p = _p()
    _need(type(approval) is dict and set(approval) == {'verdict', 'reviewer', 'test_reference', 'files'}
          and approval['verdict'] == 'APPROVED' and approval['files'] == p.build()
          and p.cal.text(approval['reviewer']) and p.cal.text(approval['test_reference']),
          'external exact-source approval required')
    raw, original = _registered(db)
    _composition(original['files'], approval['files'])
    return dict(kind='exact-v3-pre-reserve-expiry-amendment', authority=AUTHORITY,
        decided_at=DECIDED_AT, scope=SCOPE, verdict=approval['verdict'],
        reviewer=approval['reviewer'], test_reference=approval['test_reference'],
        files=copy.deepcopy(approval['files']), original_decision_sha256=DECISION_SHA,
        original_decision_data_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        stop_preimage=_stop(db), baseline=copy.deepcopy(original['baseline']),
        legacy_scope_tables=copy.deepcopy(original['legacy_scope_tables']),
        historical_session_sha256=_history(db), evidence=copy.deepcopy(EVIDENCE),
        account_binding_sha256=original['account_binding_sha256'],
        environment=copy.deepcopy(original['environment']), db_identity=list(db.inode),
        display=original['display'], at=time.time())


def install(db, record):
    """Sole parent locked idle install; schema+record one transaction, never reinstall."""
    p = _p()
    _need(type(db) is p.d.LocalDB, 'original sole LocalDB required')
    record = copy.deepcopy(record)
    with db.tx():
        _need(not db.meta('lease'), 'idle lease-empty amendment required')
        p.r.no_unresolved(db)
        db.unchanged()
        for row in db.db.execute('SELECT data FROM db12_session'):
            _need(json.loads(row[0]).get('closed') is True, 'full idle all-closed amendment required')
        _need(not _exists(db, 'cp14v3_rule_amendment') and not _exists(db, 'cp14v3_halt'),
              'one append-only amendment install only')
        _need(budget.report(db)['consumed'] == CONSUMED, 'exact historical spent counts required')
        record_value(db, record)
        _tables(db)
        db.db.execute('INSERT INTO cp14v3_rule_amendment VALUES(?,?)', (SCOPE, _json(record)))
    return report(db)


def composition_ok(db, decision, files):
    if decision['files'] == files:
        return
    record = record_value(db)
    raw, original = _registered(db)
    _need(_json(decision) == _json(original) and record['files'] == files,
          'amendment binds original immutable decision only')


def report(db):
    counts = budget.report(db)
    historical = counts['stopped']
    amended = False
    if _exists(db, 'cp14v3_rule_amendment') and db.db.execute(
            'SELECT 1 FROM cp14v3_rule_amendment WHERE scope=?', (SCOPE,)).fetchone() is not None:
        record_value(db)
        amended = True
    halted = _exists(db, 'cp14v3_halt') and db.db.execute(
        'SELECT 1 FROM cp14v3_halt WHERE scope=?', (SCOPE,)).fetchone() is not None
    return dict(counts, historical_stopped=historical, stopped=halted or (historical and not amended))


def healthy(db):
    counts = report(db)
    _need(not counts['stopped'], 'Contacts observation scope hard stopped')
    _need(all(value >= 0 for value in counts['remaining'].values()), 'budget exceeded')
    for row in db.db.execute(
            'SELECT o.id,o.result FROM cp14v3_reservation r '
            'LEFT JOIN db12_operation o ON o.id=r.operation'):
        _need(row[0] is not None and row[1] is not None,
              'missing or pending operation blocks Contacts scope')
        try:
            result = json.loads(row[1])
        except (ValueError, TypeError) as exc:
            raise RuntimeError('malformed operation result blocks Contacts scope') from exc
        _need(isinstance(result, dict) and result.get('status') == 'done',
              'non-done operation permanently blocks Contacts scope')
    return counts


def stop(db, reason):
    """Every NEW hard failure blocks despite the historical stop exception."""
    _need(isinstance(reason, str) and bool(reason.strip()), 'honest stop reason required')
    if not _exists(db, 'cp14v3_rule_amendment'):
        return budget.stop(db, reason)
    with db.tx():
        _need(_exists(db, 'cp14v3_halt'), 'hard-halt journal missing')
        db.db.execute('INSERT OR IGNORE INTO cp14v3_halt VALUES(?,?,?)',
                      (SCOPE, reason, time.time()))
```

- [ ] **4. 在同一个 module 后面追加以下完整两个函数。** 不通过动态 exec、代理过滤 SQL 或临时移除 stop 绕预算；此处采用原 budget 逻辑的显式最小复制。

```python
def admit(db, sid, decision, review):
    _transaction(db)
    _need(isinstance(sid, str) and bool(sid), 'session ID required')
    _need(isinstance(decision, dict) and bool(decision), 'explicit decision required')
    _need(isinstance(review, dict) and bool(review), 'explicit bound review required')
    decision_json, review_json = _json(decision), _json(review)
    counts = healthy(db)
    existing = db.db.execute('SELECT data FROM cp14v3_decision WHERE scope=?',
                             (SCOPE,)).fetchone()
    _need(existing is None or _json(json.loads(existing[0])) == decision_json,
          'original immutable decision mismatch')
    _need(counts['remaining']['sessions'] > 0 and counts['remaining']['operations'] > 0,
          'no session or operation budget remains')
    _need(db.db.execute('SELECT 1 FROM cp14v3_admission WHERE sid=?', (sid,)).fetchone()
          is None, 'session already admitted; never reopen')
    for row in db.db.execute('SELECT sid FROM cp14v3_admission WHERE scope=?', (SCOPE,)):
        prior = db.session(row[0])
        _need(isinstance(prior, dict) and prior.get('closed') is True
              and prior.get('unresolved_operations') == []
              and prior.get('unresolved_intents') == [],
              'previous admission must be honestly closed with empty unresolved lists')
    state = db.session(sid)
    _open_state(state)
    _need(state['steps'] == 0, 'admission requires exactly zero session steps')
    if existing is None:
        db.db.execute('INSERT INTO cp14v3_decision(scope,data) VALUES(?,?)',
                      (SCOPE, decision_json))
    db.db.execute('INSERT INTO cp14v3_admission(sid,scope,data) VALUES(?,?,?)',
                  (sid, SCOPE, review_json))


def reserve(db, q, state):
    _transaction(db)
    _need(isinstance(q, dict) and isinstance(q.get('action'), str)
          and q['action'] in KINDS, 'allowed Contacts action required; no Send/park')
    sid, operation, kind = q.get('session'), q.get('operation'), q['action']
    _need(isinstance(sid, str) and bool(sid), 'session ID required')
    _need(isinstance(operation, str) and re.fullmatch(r'[0-9a-f]{32}', operation),
          'unique operation UUID required')
    request = _json(q)
    counts = healthy(db)
    _need(db.db.execute('SELECT 1 FROM cp14v3_admission WHERE sid=? AND scope=?',
                        (sid, SCOPE)).fetchone() is not None,
          'session admission required')
    _open_state(state)
    actual = db.session(sid)
    _open_state(actual)
    _need(_json(actual) == _json(state), 'stale session state denied')
    _need(counts['remaining']['operations'] > 0, 'global operations exhausted')
    cap = KINDS[kind]
    _need(cap is None or counts['remaining'][cap] > 0, 'global kind budget exhausted')
    _need(db.db.execute('SELECT 1 FROM db12_operation WHERE id=?',
                        (operation,)).fetchone() is None,
          'operation already attempted; never replay')
    changed = copy.deepcopy(state)
    changed.update(steps=state['steps'] + 1, latest=None, stage='contacts-producer',
                   friend_id=None, oid=None, intent=None)
    at = time.time()
    db.db.execute('SAVEPOINT cp14v3_atomic_reserve')
    try:
        db.db.execute('INSERT INTO db12_operation(id,session,request,started,result) '
                      'VALUES(?,?,?,?,NULL)', (operation, sid, request, at))
        db.db.execute('INSERT INTO cp14v3_reservation(operation,sid,kind,at,request) '
                      'VALUES(?,?,?,?,?)', (operation, sid, kind, at, request))
        db.save_session(sid, changed)
        _need(_json(db.session(sid)) == _json(changed), 'session save did not persist')
        db.db.execute('RELEASE SAVEPOINT cp14v3_atomic_reserve')
    except BaseException:
        db.db.execute('ROLLBACK TO SAVEPOINT cp14v3_atomic_reserve')
        db.db.execute('RELEASE SAVEPOINT cp14v3_atomic_reserve')
        raise
    return changed
```

- [ ] **5. 绿灯和不变量复核。**

**Verification (copy-paste):**

```bash
python3 -I -B /tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_recovery.py
python3 -I -B - <<'PY'
import ast, hashlib
from pathlib import Path
C=Path('/tmp/wxview92/cp14_v3_rulefix_20261014')
for n in ('controller_db_contacts_v3_recovery_20261014.py','test_v3_recovery.py'):
    ast.parse((C/n).read_text(), filename=n)
p=Path('/tmp/wxview92/cp14_v3_evidence_20261014/controller_db_contacts_budget_v3_20261014.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='fcf1f91f334bdf2865956ffb22b4fdba0d840658a252f58b2a808c09c4dab760'
print('AST OK; original budget unchanged')
PY
```

期望：9 tests / OK；第二命令打印 `AST OK; original budget unchanged`。测试记录必须声明：mock 了 amendment validation，仅证明 wrappers/SQLite append-only/事务/未知阻断，不冒称 authentic production history 或 live grant。

### Task 2: producer 最小接线与明确 nonfatal pre-reserve expiry

**Objective:** 新 21 build 合法接续 immutable 原 decision；只有原 frame 已验证但纯年龄≥180拒绝且 run reserve 前所有账/状态无变化、无 native 时返回 nonfatal。不得 catch 所有 `c.Error` 或按字符串匹配 Error 做恢复。父可识别结果后诚实关闭当前 SID，必要时用余下 SID，不盲重放旧请求/旧滚格。

**Context from:** Task 1 创建 recovery；SOURCE producer `build:46–62`、`source_guard:64–79`、`decision_value:171–181`、`original_frame:309–316`、`owned:429–469`、`_admit:472–493`、`run:511–614`、`close:617–628`。原 immutable UI `Engine.record:214–229`：fresh=False只省略最新/180检查，仍完整验证同SID、immutable PNG path/mode/hash/dimensions、owner/root。因此先 fresh=False + 原 account/owner/geometry，再独立纯时间拒绝，不放宽校验。

**Non-goals:** 不改变 review_image 180/360/overlap/rows/park/input/owner 任一规则，不重放原 notch，不用新图替原 before证明，不改旧 decision 或 old_nav_review/global baseline；不升级 budget、不引入 retry loop、不改生产 transport/文档、不自动部署或申请新授权。

**Files (≤2):**
- Create: `/tmp/wxview92/cp14_v3_rulefix_20261014/controller_db_contacts_producer_20261014.py`，从 SOURCE 复制；只修改 SOURCE 对应行 `12–16,46–79,171–181,309–316,429–628` 的下列精确片段，其他字节保持。
- Create: `/tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_rulefix.py`

**Steps:**

- [ ] **1. 复制受审 producer 为私有候选。** Task 1 module保留，SOURCE不改。

```bash
python3 -I -B - <<'PY'
from pathlib import Path
import hashlib
S=Path('/tmp/wxview92/cp14_v3_evidence_20261014/controller_db_contacts_producer_20261014.py')
assert hashlib.sha256(S.read_bytes()).hexdigest()=='0f693073a2c33b2dff2f5ed6438c30f349f7dff5c84a514d73e23ce7ca66f7ad'
C=Path('/tmp/wxview92/cp14_v3_rulefix_20261014/controller_db_contacts_producer_20261014.py')
assert not C.exists(), 'do not overwrite another candidate'
C.write_bytes(S.read_bytes())
PY
```

- [ ] **2. 创建以下新的定向测试。** Launcher只把原 private-source approval map里精确18固定源码、fcf预算与两个候选复制到临时目录；不触发旧 runner、不导入 R 中未经批准替代组合。不构造 Desktop，不执行 ctypes/native。模拟 seam 显式写出；source闭包/immutable record的拒绝类型测试保持可区分。

```python
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from unittest.mock import patch

HERE=Path(__file__).absolute().parent
SOURCE=Path('/tmp/wxview92/cp14_v3_evidence_20261014')
R=Path('/tmp/wxview92/upgrade_20261010T1529')
NAME='controller_db_contacts_producer_20261014.py'
ADDON='controller_db_contacts_v3_recovery_20261014.py'
BUDGET='controller_db_contacts_budget_v3_20261014.py'
if '--isolated' not in sys.argv:
    approved=json.loads(Path('/tmp/wxview92/cp14_v3_private_source_approval_20261014.json').read_text())['files']
    assert len(approved)==20
    with tempfile.TemporaryDirectory(prefix='cp14v3-rulefix-') as td:
        dst=Path(td)
        for name,digest in approved.items():
            if name==NAME:
                continue
            src=SOURCE/name if name==BUDGET else R/name
            if name=='controller_db_ui_20261012.py':
                src=Path('/tmp/wxview92/db13_ui_selected_contacts_candidate_20261013.py')
            if name=='controller_db_direct_automation_20261013.py':
                src=Path('/tmp/wxview92/profile_account_actual_contract_20261014')/name
            assert hashlib.sha256(src.read_bytes()).hexdigest()==digest,name
            shutil.copyfile(src,dst/name)
        for name in (NAME,ADDON,Path(__file__).name):
            shutil.copyfile(HERE/name,dst/name)
        for path in dst.glob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
        result=subprocess.run([sys.executable,'-I','-B',str(dst/Path(__file__).name),'--isolated'],
                              cwd=dst,env=dict(os.environ,TMPDIR=str(dst)))
        assert not list(dst.rglob('__pycache__'))
    raise SystemExit(result.returncode)
sys.argv.remove('--isolated')
sys.path.insert(0,str(HERE))
import controller_db_contacts_producer_20261014 as p
import controller_db_contacts_v3_recovery_20261014 as a

class MemoryDB:
    def __init__(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
          CREATE TABLE db12_operation(id TEXT PRIMARY KEY,session TEXT,request TEXT,started REAL,result TEXT);
          CREATE TABLE db12_session(id TEXT PRIMARY KEY,data TEXT);
          CREATE TABLE db12_capture(id TEXT PRIMARY KEY,session TEXT,data TEXT);
          CREATE TABLE db12_intent(id TEXT PRIMARY KEY,session TEXT);
        ''')
        self.inode=(2050,5791809)
        p.budget.install(self)
    @contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
    def meta(self,key):
        return None
    def session(self,sid):
        row=self.db.execute('SELECT data FROM db12_session WHERE id=?',(sid,)).fetchone()
        return json.loads(row[0]) if row else None
    def save_session(self,sid,state):
        self.db.execute('INSERT OR REPLACE INTO db12_session VALUES(?,?)',(sid,p.budget._json(state)))

class RulefixTests(unittest.TestCase):
    def setUp(self):
        self.db=MemoryDB()
        self.addCleanup(self.db.db.close)
        self.sid='a'*32
        self.state=dict(closed=False,steps=1,latest='c'*32,opened_at=100,
                        unresolved_operations=[],unresolved_intents=[])
        with self.db.tx():
            self.db.save_session(self.sid,self.state)
            self.db.db.execute('INSERT INTO cp14v3_decision VALUES(?,?)',(p.SCOPE,p.budget._json({'files':{}})))
            self.db.db.execute('INSERT INTO cp14v3_admission VALUES(?,?,?)',(self.sid,p.SCOPE,'{}'))
        self.engine=types.SimpleNamespace(db=self.db,sid=self.sid)
        self.q=dict(operation='b'*32,session=self.sid,action='cp-review',evidence='c'*32,
                    reviewer='parent-visual',note='synthetic expiry case',observed={})
        self.decision={'files':{}}
    def run_refusal(self,exc,mutate=None):
        def original(*args):
            if mutate:
                mutate()
            raise exc
        with patch.object(p,'qvalue'),patch.object(p,'owned',return_value=copy.deepcopy(self.state)),\
             patch.object(p,'original_frame',side_effect=original),patch.object(p.r,'no_unresolved'),\
             patch.object(a,'healthy',side_effect=lambda db:p.budget.report(db)),patch.object(a,'report',side_effect=lambda db:p.budget.report(db)),\
             patch.object(a,'stop',wraps=a.stop) as stopped:
            result=None
            try:
                result=p.run(self.engine,self.q,{}, {},self.decision)
            finally:
                self.stopped=stopped.call_count
            return result
    def test_expiry_is_explicit_nonfatal_no_reserve(self):
        before=p.zero_input_snapshot(self.db,self.sid)
        result=self.run_refusal(p.PreReserveExpiry('expired immutable source'))
        self.assertEqual(result['status'],'refused-pre-reserve-expiry')
        self.assertEqual(self.stopped,0)
        self.assertEqual(before,p.zero_input_snapshot(self.db,self.sid))
        self.assertIsNone(self.db.db.execute('SELECT 1 FROM db12_operation WHERE id=?',('b'*32,)).fetchone())
    def test_ordinary_error_is_not_exempt(self):
        with self.assertRaises(p.c.Error):
            self.run_refusal(p.c.Error('latest session capture under180 required'))
        self.assertEqual(self.stopped,1)
        self.assertTrue(p.budget.report(self.db)['stopped'])
    def test_changed_preflight_cannot_be_nonfatal(self):
        def mutate():
            with self.db.tx():
                self.db.save_session(self.sid,dict(self.state,steps=2))
        with self.assertRaises(p.c.Error):
            self.run_refusal(p.PreReserveExpiry('expired immutable source'),mutate)
        self.assertEqual(self.stopped,1)
    def test_existing_request_never_nonfatal_or_replayed(self):
        with self.db.tx():
            self.db.db.execute('INSERT INTO db12_operation VALUES(?,?,?,?,?)',
                              ('b'*32,self.sid,'{}',100,p.budget._json({'status':'done'})))
        with self.assertRaises(p.c.Error):
            self.run_refusal(p.PreReserveExpiry('expired immutable source'))
        self.assertEqual(self.stopped,1)
    def test_original_frame_age_only_after_all_original_validation(self):
        owner={'mode':'main','main':{'id':'101','x':0,'y':0,'w':1088,'h':770},'root':[0,0,1920,1200]}
        frame={'id':'c'*32,'at':100,'policy':'profile','owner':owner}
        with patch.object(p.u.Engine,'record',return_value=frame) as record,\
             patch.object(p.cal,'account_provenance',return_value={'owner':owner}),\
             patch.object(p.o,'validate',side_effect=lambda x:x),patch.object(p.o,'same_main',return_value=True),\
             patch.object(p.time,'time',return_value=280):
            with self.assertRaises(p.PreReserveExpiry):
                p.original_frame(self.engine,'c'*32,self.state)
            self.assertFalse(record.call_args.kwargs['fresh'])
        with patch.object(p.u.Engine,'record',side_effect=p.c.Error('immutable captured PNG required')):
            with self.assertRaises(p.c.Error) as caught:
                p.original_frame(self.engine,'c'*32,self.state)
            self.assertNotIsInstance(caught.exception,p.PreReserveExpiry)
    def test_geometry_failure_before_age_not_exempt(self):
        owner={'mode':'main','main':{'id':'101','x':0,'y':0,'w':600,'h':500},'root':[0,0,1920,1200]}
        frame={'id':'c'*32,'at':100,'policy':'profile','owner':owner}
        with patch.object(p.u.Engine,'record',return_value=frame),\
             patch.object(p.cal,'account_provenance',return_value={'owner':owner}),\
             patch.object(p.o,'validate',side_effect=lambda x:x),patch.object(p.o,'same_main',return_value=True),\
             patch.object(p.time,'time',return_value=280):
            with self.assertRaises(p.c.Error) as caught:
                p.original_frame(self.engine,'c'*32,self.state)
            self.assertNotIsInstance(caught.exception,p.PreReserveExpiry)
    def test_source_map_exactly_21_immutable_budget_and18(self):
        files=p.build()
        self.assertEqual(len(files),21)
        self.assertEqual(files[BUDGET],a.OLD_BUDGET)
        original={k:v for k,v in files.items() if k!=ADDON}
        original[NAME]=a.OLD_PRODUCER
        a._composition(original,files)
        wrong=dict(files)
        wrong['controller_db_ui_20261012.py']='0'*64
        with self.assertRaises(RuntimeError):
            a._composition(original,wrong)
        with self.assertRaises(RuntimeError):
            a.composition_ok(self.db,{'files':original},files)
    def test_new_halt_not_masked_by_historical_exception(self):
        with self.db.tx():
            a._tables(self.db)
            self.db.db.execute('INSERT INTO cp14v3_rule_amendment VALUES(?,?)',(p.SCOPE,'{}'))
            self.db.db.execute('INSERT INTO cp14v3_stop VALUES(?,?,?)',(p.SCOPE,'Error',1791971065.2647989))
        with patch.object(a,'record_value',return_value={}):
            self.assertFalse(a.report(self.db)['stopped'])
            a.stop(self.db,'post-reserve/native failure')
            self.assertTrue(a.report(self.db)['stopped'])
            with self.assertRaises(RuntimeError):
                a.healthy(self.db)

if __name__=='__main__':
    unittest.main(verbosity=2)
```

- [ ] **3. 红灯。**

```bash
python3 -I -B /tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_rulefix.py
```

预期非零：缺少 `PreReserveExpiry`/`zero_input_snapshot`，或源闭包仍 20。不得先改测试让红灯失效。

- [ ] **4. producer exact replacements。** 以下脚本是完整机械编辑说明；writer可逐项 exact replace，也可直接复制脚本运行。它只写 C 中 producer，禁止写 SOURCE/R。脚本每项恰好一次，否则停止。旧 decision shape、old_history、review_image、expired_unreviewed_frame 的函数文本保持原样。

```bash
python3 -I -B - <<'PY'
from pathlib import Path
path=Path('/tmp/wxview92/cp14_v3_rulefix_20261014/controller_db_contacts_producer_20261014.py')
text=path.read_text()
def replace(old,new):
    global text
    assert text.count(old)==1,repr(old)
    text=text.replace(old,new)
replace('import controller_db_contacts_budget_v3_20261014 as budget\n',
        'import controller_db_contacts_budget_v3_20261014 as budget\nimport controller_db_contacts_v3_recovery_20261014 as recovery\n')
replace("for name in (*fixed,'controller_db_contacts_budget_v3_20261014.py',Path(__file__).name):",
        "for name in (*fixed,'controller_db_contacts_budget_v3_20261014.py','controller_db_contacts_v3_recovery_20261014.py',Path(__file__).name):")
replace("c.need(decision['files']==files,'independent exact producer build required')",
        'recovery.composition_ok(engine.db,decision,files)')
replace("(Desktop.pointer_snapshot,'controller_db_round_ui_20261013.py'),(run,Path(__file__).name)):",
        "(Desktop.pointer_snapshot,'controller_db_round_ui_20261013.py'),\n       (recovery.record_value,'controller_db_contacts_v3_recovery_20261014.py'),\n       (recovery.reserve,'controller_db_contacts_v3_recovery_20261014.py'),(run,Path(__file__).name)):")
replace("c.need(decision['files']==build(),'independently approved closure required')",
        'recovery.composition_ok(db,decision,build())')
replace("frame=u.Engine.record(engine,eid,dict(state,latest=eid))\n    account=cal.account_provenance(engine,state)",
        "frame=u.Engine.record(engine,eid,dict(state,latest=eid),fresh=False)\n    account=cal.account_provenance(engine,state)")
replace("           and c.rect(value['main'])[2:]==[1088,770],'fresh current same-main1088 geometry; mismatch is diagnostic stop')\n    return frame",
        "           and c.rect(value['main'])[2:]==[1088,770],'fresh current same-main1088 geometry; mismatch is diagnostic stop')\n    age=time.time()-frame['at']\n    c.need(age>=0,'capture timestamp cannot be in the future')\n    if age>=180:raise PreReserveExpiry('immutable same-SID source capture expired before reservation')\n    c.need(0<=age<180,'latest session capture under180 required')\n    return frame")
# Exactly every producer-side budget API call that influences effective stop.
# budget.KINDS/CAPS/_json/install and immutable budget source remain untouched.
for name in ('report','healthy','admit','reserve','stop'):
    old='budget.'+name+'('
    assert old in text,name
    text=text.replace(old,'recovery.'+name+'(')
replace('    changed=None\n    try:\n        qvalue(q);',
        '    changed=None;snapshot=None\n    try:\n        qvalue(q);')
replace("        c.need(db.db.execute('SELECT 1 FROM cp14v3_admission WHERE sid=?',(engine.sid,)).fetchone(),'default deny')\n        a=q['action'];",
        "        c.need(db.db.execute('SELECT 1 FROM cp14v3_admission WHERE sid=?',(engine.sid,)).fetchone(),'default deny')\n        snapshot=zero_input_snapshot(db,engine.sid)\n        a=q['action'];")
replace('    except BaseException as exc:\n        if changed is not None:fail(db,q,changed,exc)\n        else:\n',
'''    except BaseException as exc:
        if type(exc) is PreReserveExpiry and changed is None and snapshot is not None:
            try:
                with db.tx():
                    c.need(owned(engine,cred,base,decision)==state,'pre-reserve refusal ownership drift')
                    r.no_unresolved(db);recovery.healthy(db)
                    c.need(zero_input_snapshot(db,engine.sid)==snapshot,'pre-reserve refusal changed state or journal')
                    c.need(db.db.execute('SELECT 1 FROM db12_operation WHERE id=?',(q['operation'],)).fetchone() is None,
                           'pre-reserve refusal request already journaled')
                    c.need(db.db.execute('SELECT 1 FROM cp14v3_reservation WHERE operation=?',(q['operation'],)).fetchone() is None,
                           'pre-reserve refusal request already reserved')
                    counts=recovery.report(db)
                return dict(status='refused-pre-reserve-expiry',operation=q['operation'],
                            session=engine.sid,action=q['action'],reason=str(exc),
                            reserved=False,native_called=False,budget=counts)
            except BaseException:
                try:recovery.stop(db,'changed or unverifiable pre-reserve expiry refusal')
                except BaseException:pass
                raise
        if changed is not None:fail(db,q,changed,exc)
        else:
''')
# Dedicated exception creation is restricted to original_frame AFTER validation.
replace('def original_frame(engine,eid,state):\n',
'''class PreReserveExpiry(c.Error):
    """Validated immutable same-SID frame failed only the strict180 age gate."""


def zero_input_snapshot(db,sid):
    # Full read-only journal/session/capture snapshot, without printing secrets.
    # Capture files themselves are authenticated by original Engine.record.
    tables=('db12_operation','db12_session','db12_capture','db12_intent',
            'cp14v3_decision','cp14v3_admission','cp14v3_reservation','cp14v3_stop')
    rows={table:[dict(row) for row in db.db.execute('SELECT * FROM '+table+' ORDER BY 1')]
          for table in tables}
    for table in ('cp14v3_rule_amendment','cp14v3_halt'):
        if db.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
            rows[table]=[dict(row) for row in db.db.execute('SELECT * FROM '+table+' ORDER BY 1')]
    return d.hash_value(dict(rows=rows,state=db.session(sid),lease=db.meta('lease')))


def original_frame(engine,eid,state):
''')
path.write_text(text)
PY
```

说明：`native_called=False` 由结构保证，run 的所有 Desktop/native/park/capture 调用都在 reserve 成功之后；没有新增任何调用。`changed is None` 仅为必要条件，专用异常类型、初始 snapshot、重验 owned/full no_unresolved/healthy 与相同 snapshot/无 operation/reservation 一起才允许非 fatal。reserve后即使出现同一个专用异常也仍走 `fail` unknown+hardhalt，不能返回非 fatal。freshness在每次 original_frame/boundary仍检查180，不延长已有图寿命。

- [ ] **5. 新增 exact-history / reserved 测试到同一 Task 2 测试文件、同一 `RulefixTests` 类中。** 插入在最后 `if __name__` 前、维持类缩进；完整方法如下。此处用真实 terminal audit 的**只读复制数据**作为非 secret 合成 fixture；不连接生产、不读capture图片、不发native。已知 terminal中 state为简略 projection，故真实 closed_authority/全 state hash 无法用它造假；相关方法 patch 只用于各自明确的测试边界，报告注明。

```python
    def test_historical_five_done_and_failed_request_zero_journal(self):
        audit=json.loads(Path('/tmp/wxview92/cp14_v3_terminal_readonly_1791971205137650989.jsonl').read_text())
        decision=json.loads(Path('/tmp/wxview92/cp14_v3_checkpoint_approved_20261014.json').read_text())['decision']
        with self.db.tx():
            self.db.db.execute('DELETE FROM cp14v3_admission')
            self.db.db.execute('DELETE FROM cp14v3_decision')
            self.db.db.execute('INSERT INTO cp14v3_decision VALUES(?,?)',(p.SCOPE,p.budget._json(decision)))
            self.db.save_session(a.HIST_SID,audit['state'])
            review=json.loads(Path('/tmp/wxview92/cp14_v3_sid_approved_20261014.json').read_text())
            self.db.db.execute('INSERT INTO cp14v3_admission VALUES(?,?,?)',
                               (a.HIST_SID,p.SCOPE,p.budget._json(review)))
            self.db.db.execute('INSERT INTO cp14v3_stop VALUES(?,?,?)',(p.SCOPE,'Error',1791971065.2647989))
            for row in audit['operations']:
                self.db.db.execute('INSERT INTO db12_operation VALUES(?,?,?,?,?)',
                    tuple(row[k] for k in ('id','session','request','started','result')))
                q=json.loads(row['request'])
                self.db.db.execute('INSERT INTO cp14v3_reservation VALUES(?,?,?,?,?)',
                    (row['id'],row['session'],q['action'],row['started'],row['request']))
            for row in audit['captures']:
                self.db.db.execute('INSERT INTO db12_capture VALUES(?,?,?)',
                    tuple(row[k] for k in ('id','session','data')))
        raw,actual=a._registered(self.db)
        self.assertEqual(p.d.hash_value(actual),a.DECISION_SHA)
        self.assertEqual(a._stop(self.db),a.STOP)
        self.assertEqual(p.budget.report(self.db)['consumed'],a.CONSUMED)
        with patch.object(p.cal,'closed_authority'),\
             patch.object(self.db,'get',create=True,return_value={'owner':{'main':{'id':'39845906'}}}):
            a._history(self.db)
            with self.db.tx():
                self.db.db.execute('INSERT INTO db12_operation VALUES(?,?,?,?,?)',
                                  (a.FAILED_REQUEST,a.HIST_SID,'{}',1,'{}'))
            with self.assertRaises(RuntimeError):
                a._history(self.db)

    def test_amendment_binds_original_bytes_stop_baseline_and_exact21(self):
        decision=json.loads(Path('/tmp/wxview92/cp14_v3_checkpoint_approved_20261014.json').read_text())['decision']
        with self.db.tx():
            self.db.db.execute('DELETE FROM cp14v3_decision')
            self.db.db.execute('INSERT INTO cp14v3_decision VALUES(?,?)',
                               (p.SCOPE,p.budget._json(decision)))
            self.db.db.execute('INSERT INTO cp14v3_stop VALUES(?,?,?)',
                               (p.SCOPE,'Error',1791971065.2647989))
        raw=self.db.db.execute('SELECT data FROM cp14v3_decision').fetchone()[0]
        record=dict(kind='exact-v3-pre-reserve-expiry-amendment',authority=a.AUTHORITY,
            decided_at=a.DECIDED_AT,scope=p.SCOPE,verdict='APPROVED',reviewer='synthetic independent review',
            test_reference='synthetic fixture only',files=p.build(),original_decision_sha256=a.DECISION_SHA,
            original_decision_data_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            stop_preimage=dict(a.STOP),baseline=decision['baseline'],legacy_scope_tables=decision['legacy_scope_tables'],
            historical_session_sha256='f'*64,evidence=dict(a.EVIDENCE),
            account_binding_sha256=decision['account_binding_sha256'],environment=decision['environment'],
            db_identity=decision['db_identity'],display=':1',at=1791971208.0)
        # Production original raw decision/stop/maps are real; only unavailable
        # complete state, preceding ledger, actual account/environment are seams.
        with patch.object(a,'_history',return_value='f'*64),\
             patch.object(a,'_baseline',return_value=decision['baseline']),\
             patch.object(p,'sealed_legacy_tables'),\
             patch.object(self.db,'get',create=True,return_value={'synthetic_account':True}),\
             patch.object(p.d,'hash_value',side_effect=lambda value:
                 decision['account_binding_sha256'] if value=={'synthetic_account':True}
                 else hashlib.sha256(p.c.dumps(value).encode()).hexdigest()),\
             patch.object(p.f,'session_environment',return_value=decision['environment']),\
             patch.dict(p.os.environ,DISPLAY=':1'):
            self.assertEqual(a.record_value(self.db,record),record)
            for key,value in (('authority','wrong'),('original_decision_data_sha256','0'*64),
                              ('stop_preimage',dict(a.STOP,at=0)),('baseline',{}),
                              ('legacy_scope_tables',{}),('evidence',{}),
                              ('historical_session_sha256','0'*64),('files',decision['files'])):
                wrong=copy.deepcopy(record);wrong[key]=value
                with self.assertRaises(RuntimeError,msg=key):
                    a.record_value(self.db,wrong)
        self.assertEqual(raw,self.db.db.execute('SELECT data FROM cp14v3_decision').fetchone()[0])

    def test_post_reserve_expiry_always_unknown_and_hard_stop(self):
        q=dict(self.q,action='cp-capture',evidence=None,observed={'pointer_park':None})
        state=dict(self.state,latest=None)
        with self.db.tx():
            self.db.save_session(self.sid,state)
        def owned(engine,cred,base,decision,current=None,q=None):
            if current is not None:
                raise p.PreReserveExpiry('age crossed after reserve')
            return copy.deepcopy(state)
        with patch.object(p,'owned',side_effect=owned),\
             patch.object(a,'healthy',side_effect=lambda db:p.budget.report(db)),patch.object(a,'report',side_effect=lambda db:p.budget.report(db)),\
             patch.object(a,'stop',wraps=a.stop) as stopped,\
             patch.object(self.db,'end_operation',create=True) as end:
            with self.assertRaises(p.PreReserveExpiry):
                p.run(self.engine,q,{}, {},self.decision)
        self.assertEqual(p.budget.report(self.db)['consumed']['operations'],1)
        self.assertEqual(end.call_args.args[1]['status'],'unknown')
        self.assertGreaterEqual(stopped.call_count,1)
```

- [ ] **6. 绿灯及精确 unchanged-function 检查。** 不重跑旧 34 全套；只这 9+11 定向测试与静态比较。测试需报告 11 中实际 mock 范围：run 的 owned/qvalue/original_frame seams，实际帧失败分层测试，journal/预算 SQLite真实，历史fixture只读 terminal复制且 closed_authority mock；这不是全old_history、实际独审或现场输入认证。

**Verification (copy-paste):**

```bash
python3 -I -B /tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_recovery.py
python3 -I -B /tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_rulefix.py
python3 -I -B - <<'PY'
import ast,hashlib,json
from pathlib import Path
S=Path('/tmp/wxview92/cp14_v3_evidence_20261014')
C=Path('/tmp/wxview92/cp14_v3_rulefix_20261014')
name='controller_db_contacts_producer_20261014.py'
def function(path,name):
    text=path.read_text(); node=next(x for x in ast.parse(text).body if isinstance(x,ast.FunctionDef) and x.name==name)
    return ''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno])
for f in ('old_history','approval','review_image','expired_unreviewed_frame','qvalue','park_value','input_value','checkpoint','sealed_legacy_tables','legacy_history_sids'):
    assert function(S/name,f)==function(C/name,f),f
assert hashlib.sha256((S/name).read_bytes()).hexdigest()=='0f693073a2c33b2dff2f5ed6438c30f349f7dff5c84a514d73e23ce7ca66f7ad'
assert hashlib.sha256((S/'controller_db_contacts_budget_v3_20261014.py').read_bytes()).hexdigest()=='fcf1f91f334bdf2865956ffb22b4fdba0d840658a252f58b2a808c09c4dab760'
for file in C.glob('*.py'): ast.parse(file.read_text(),filename=str(file))
print('SOURCE immutable; ten historical/geometry functions byte-identical; candidate AST OK')
print(json.dumps({x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(C.glob('*.py'))},indent=2))
PY
```

期望：9 tests/OK，11 tests/OK，静态命令打印 `SOURCE immutable; ten historical/geometry functions byte-identical; candidate AST OK` 和候选4文件sha256。任何失败只修本任务新文件；不得修改旧fixtures、pin常量或 SOURCE让测试通过。

## 父任务接续契约（不是 writer task，不执行外部操作）

1. 文档 append-only更正旧“需新用户决定”结论；绑定本次用户/manager既有authority，不再询问授权，不新scope。旧diag保留为历史分析，已知180超期不重诊断。
2. 对候选两个runtime源码及真实21 map做必要独审；不把这些本地mock测试当 live APPPROVED。独审特别核 source_guard→composition_ok→record_value绑定原019f decision；对实际全 closed state/lease provenance、5done/5reservation/2capture、失败7fbd无journal/reservation、原stop前像、actual8legacymap、full no_unresolved、账户/DB/env/display、排scope original baseline与完整 old_history重新只读核对。
3. sole parent原锁与idle下做精确source placement（保存原producer前像、21map/receipt，budget fcf不动）；传外部独审 `{verdict,reviewer,test_reference,files}` 至 `recovery.make_record(db,approval)`，然后 `recovery.install(db,record)`。install先验证当前 exactly 5/2/1/0/0/1；任何新工作/未知即拒绝，不修改旧4表。原decision文件不写，register不重调；旧base/old_nav_review不替换。
4. 后续 parent transport需使用 `p.recovery.report/healthy/stop` 的**有效**语义，`p.budget.report`仅作旧historical stop/不可退款计数。若仍使用旧transport的except `budget.stop` +关闭，会重新误停；父仅在明确返回 `status=refused-pre-reserve-expiry,reserved=False,native_called=False` 时按非fatal处理，不重放q、不调用hard stop；其他异常仍 `p.recovery.stop`。不得 catch整个Error类。默认stop行永不删除。
5. 新 owned SID（第2/3个）的审查仍用**原decision_sha256019f**与fresh perSID checkpoint，另保留amendment/21map关联的增量审证据；不修改旧 SID review/decision。按既有open、full history、fresh owned/账号、独立 SID review、admit+account-history、首capture序列。budget wrappers继承全部remaining，不退款，不重启160或80计数。
6. 首capture从**实际当前**Contacts建立新review；原notch已done，不重放。旧SID图只留历史，不拿它作为新SID的latest/overlap/current evidence；新的capture→review→单格操作→park→capture→whole-image overlap必须重新建立实际链。
7. parent观察deadline=`min(所有所需当前/source图at+180, lineage相关端点时限)`，检查原before与after同时<180，360仅额外lineage约束。首review/capture/单格/overlap在source deadline前完成；不足时间不发input、不伪时，不用“图间167<360”替180。专用nonfatal refusal不是新视觉权、retry权或替换原before证据；state无变化如仍需新观测而现有overlap永远过期，诚实no-input close（明确保留未完成review）后按remaining/新SID独审继续，不能复活closed。
8. clean close仍要求真实latest review/无park；existing `close` 的unclean error会hard halt，故因非fatal纯时效且确需放弃当前SID时父应直接走既有 `f.close_owned` 诚实关闭，不虚称clean/完成coverage，也不经 `p.close`制造“unclean closure”新stop。前置全journal done/无unresolved/无未知input仍必要。若已reserved/unknown/changed/native错误，无此例外。
9. 完成应报告旧stop retained/historical_stopped=true、effective stopped=false（直到新hard error）、actual计数remaining与newSID闭环；不得称top/tail/full inventory/画像已完成，除非随后真实证据满足原规则。下游发送准入仍另行绑定既有发送守卫，本变更不授发送。

## 自检记录

- SPEC COVERAGE：Task1绑定原decision字节/019f、stop前像、5done、7fbd零journal、实际8legacymap与原baseline；同scope剩余预算/闭合21map；Task2仅专用pre-reserve非native年龄拒绝，unknown/changed/reserved仍硬停；父契约覆盖新SID2/3、fresh SID review、capture/overlap重新建立、source deadline、文档/独审不重问授权。
- COMPLETENESS：两个task各2文件，全部新增/修改代码与命令完整给出，无泛化框架或后续占位实现；原预算不修改。
- CROSS-TASK：recovery名、21map新增名、PreReserveExpiry/zero_input_snapshot、API report/healthy/admit/reserve/stop一致；Task2显式依赖Task1。
- WEAK EXECUTOR TEST：最复杂Task2提供原producer精确hash、复制命令、每个机械替换、独立launcher及完整定向测试；无需额外查架构或选择策略。
- NON-GOALS：两task均明确本地/不动旧事实/不放宽守卫，外部动作仅父负责。

## Task Index

| ID | Title | Files | Verification | Depends_on |
|---|---|---|---|---|
| 1 | Exact v3 amendment and immutable-budget wrappers | /tmp/wxview92/cp14_v3_rulefix_20261014/controller_db_contacts_v3_recovery_20261014.py; /tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_recovery.py | python3 -I -B /tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_recovery.py | — |
| 2 | Minimal producer wiring and zero-reserve expiry refusal | /tmp/wxview92/cp14_v3_rulefix_20261014/controller_db_contacts_producer_20261014.py; /tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_rulefix.py | python3 -I -B /tmp/wxview92/cp14_v3_rulefix_20261014/test_v3_rulefix.py | 1 |
