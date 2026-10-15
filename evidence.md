# 新附件：流程提速证据与定位
来源为用户提供的 `wx.tar(1).gz` 中 `wechat-sim/p1_live/`。以下是静态源码核对、既有运行日志计算和本次离线回放；未在目标微信会话执行输入，未取得改造后的实机耗时。
## 关键计时
- 原记录总耗时：34.479 秒。
- start 事件至 send_clicked：31.999 秒。
- start 事件至通讯录点击：7.695 秒（冷启动、账号等准备的现场段，并非每一毫秒都可删除）。
- send_clicked 至 finish 事件：2.479 秒。
- 无重试成功路径中显式 sleep 合计 9.9 秒，另有点击方法每次 0.08 秒。
| 阶段 | 报告 perceive 秒数 | 成功路径 OCR 调用次数 |
|---|---:|---:|
| ready | 0.931 | 0 |
| account | 1.835 | 1 |
| ready2 | 0.960 | 0 |
| contacts | 2.461 | 1 |
| profile | 2.226 | 1 |
| chat | 2.940 | 1 |
| favorites | 5.197 | 3 |
| selected | 4.307 | 3 |

`perceive` 包含 capture；capture 包含两次 observe、抓屏、PNG 写盘及事件记录。不要把上表全部称为 OCR 推理时间。

| 阶段 | capture 事件至 observation 事件的时间差（秒） |
|---|---:|
| ready | 0.002 |
| account | 0.812 |
| ready2 | 0.002 |
| contacts | 1.555 |
| profile | 1.152 |
| chat | 1.986 |
| favorites | 4.242 |
| selected | 3.327 |

这些差值更接近识别/规则部分，但包含少量杂项，也不是纯模型计时。聊天与两个收藏状态合计约 9.55 秒；只表示可替换段落的规模，不能保证修改后逐秒等额下降。

## 本次无 OCR 回放
见同包 `replay_result.json`：11 张原附件真实截图（7 张面板、4 张非面板）和 3 个合成负例，共 14/14 得到预期分类。基于原模板和同布局截图，不是独立泛化验证。纯视觉正例运行 210 次，P50 3.116 ms、P95 3.654 ms；不含文件读取、抓屏、窗口检查、OCR、输入、日志、账本与 UI 等待。
这个探针不证明收件人、全局列表顶部、屏外选中项、窗口归属或消息送达，不能单独作为 Send 许可。

## E1 报告口径与限制

来源：`p1_live/P1_REPORT.md:16–35`。

```text
  16 ## 耗时（秒，端到端 34.479）
  17 
  18 init:ocr_model 0.701 · ready 0.931 · account 1.835 · ready2 0.960 · contacts 2.461 · profile 2.226 · chat 2.940 · favorites 5.197 · selected 4.307 · input:send 0.085。其余是动作后的固定等待（0.8–1.5s/步）和截图/窗口检查。
  19 
  20 ## 步骤与证据
  21 
  22 1. P0：真实采样 `evidence/p0_explore/`，共 9 帧，覆盖账号弹窗、通讯录、资料、聊天、收藏面板未选/已选/hover，最后 Cancel，无 Send。
  23 2. 离线回放：`python3 -I ocr_mvp_v1.py replay`，正向全路径通过；3 个错误窗口负样本均返回 UNKNOWN 被拒；未选中行不会误判为选中。
  24 3. 实机 dry-run：`evidence/run_20261014T171246_nosend/`，34.9s 到达唯一已选态后 Cancel。
  25 4. P1 实机：`evidence/run_20261014T171331_send/`。`events.jsonl` 记录每次输入、帧和观察；`result.json` 是结果；`ledger_ocr_mvp_v1.sqlite3` 是账本。发送后截图里聊天中出现 17:14 卡片，但只作附带证据，不作为送达证明（post_send_proof=false）。
  26 
  27 ## 边界与已知限制
  28 
  29 - 账本是本验证专用的新 SQLite（`ledger_ocr_mvp_v1.sqlite3`），没有写入生产 `ledger_8027.sqlite3`。两者合并属于后续工作。
  30 - 固定配置：主窗口 1088x770、面板 770x610、浅色主题、100% 缩放。布局变化需要重新校准，不会自动适配。
  31 - 每个状态只有 1–2 份真实样本，低于计划中每状态 5–10 帧的起始样本量。P2 前应补采样。
  32 - 去重键用的是 OCR 读到的 Weixin ID；同一 request 再次运行会被账本拒绝。
  33 - P2（同页多人）、P3（滚动/尾部）、P4（性能）未开始。
```

## E2 聊天 OCR 与收藏面板的三次 OCR

来源：`p1_live/ocr_mvp_v1.py:173–207`。

```text
 173 def perceive_chat(image, g):
 174     title = ocr(image, absbox(g, W_CHAT_TITLE))
 175     comp = np.asarray(image.crop(tuple(absbox(g, W_COMPOSER)[:2]) + (
 176         g['x'] + W_COMPOSER[0] + W_COMPOSER[2], g['y'] + W_COMPOSER[1] + W_COMPOSER[3])))
 177     nonbg = int((np.abs(comp.astype(int) - 250).max(axis=2) > 12).sum())
 178     send_px = image.getpixel(abspt(g, W_CHAT_SEND))
 179     cubes = match_all(image, absbox(g, W_TOOLBAR), TPL['cube'], 0.80)
 180     if len(cubes) != 1 or cubes[0][0] < 0.92:
 181         raise Unknown('favorites toolbar icon not unique: %r' % cubes)
 182     return dict(title=' '.join(t[0] for t in title), composer_nonbg=nonbg,
 183                 composer_empty=nonbg <= 60, send_disabled=close(send_px, GRAY_BTN, 8),
 184                 send_px=send_px, cube=cubes[0][1:], cube_score=cubes[0][0])
 185 
 186 
 187 def perceive_panel(image, p):
 188     header = ocr(image, absbox(p, P_HEADER))
 189     search = ocr(image, absbox(p, P_SEARCH))
 190     send_px = image.getpixel(abspt(p, P_SEND))
 191     send = 'enabled' if close(send_px, GREEN_BTN, 25) else 'disabled' if close(send_px, GRAY_BTN, 8) else 'unknown'
 192     empty = match_all(image, absbox(p, P_RADIOS), TPL['radio_empty'], 0.85)
 193     checked = match_all(image, absbox(p, P_RADIOS), TPL['radio_checked'], 0.85)
 194     radios = sorted([dict(y=y, x=x, checked=False, score=s) for s, x, y in empty]
 195                     + [dict(y=y, x=x, checked=True, score=s) for s, x, y in checked], key=lambda r: r['y'])
 196     for a, b in zip(radios, radios[1:]):
 197         if abs(a['y'] - b['y']) < 30:
 198             raise Unknown('ambiguous radio state at y=%d' % a['y'])
 199     if not radios:
 200         raise Unknown('no favorite items visible (loading?)')
 201     first = radios[0]
 202     title = ocr(image, [first['x'] + 30, first['y'] - 45, 360, 30])
 203     return dict(header=' '.join(t[0] for t in header), search_text=' '.join(t[0] for t in search),
 204                 all_favorites=close(image.getpixel(abspt(p, P_ALLFAV)), GREEN_ROW, 12),
 205                 send=send, send_px=send_px, radios=radios,
 206                 first_at_top=abs(first['y'] - (p['y'] + P_FIRST_RADIO_Y)) <= 4,
 207                 first_title=' '.join(t[0] for t in title))
```

## E3 每个状态固定等待及重试

来源：`p1_live/ocr_mvp_v1.py:286–303`。

```text
 286     def perceive(self, tag, fn, want_panel=False, check=None, wait=1.0):
 287         last = None
 288         for attempt in range(POLICY['observation_retries_per_state']):
 289             time.sleep(wait if attempt == 0 else 1.0)
 290             s = time.time()
 291             f = self.observe(tag + ('' if attempt == 0 else '_r%d' % attempt), want_panel)
 292             try:
 293                 v = fn(f)
 294                 if check:
 295                     check(v)
 296                 self.t('perceive:' + tag, s)
 297                 self.rec.event(kind='observation', tag=tag, frame=f['id'],
 298                                value={k: v[k] for k in v if k != 'texts'})
 299                 return f, v
 300             except Unknown as e:
 301                 last = str(e)
 302                 self.rec.event(kind='unknown', tag=tag, frame=f['id'], reason=last)
 303         raise Stop('needs_review after %d observations at %s: %s' % (POLICY['observation_retries_per_state'], tag, last))
```

## E4 冷启动与本人账号校验

来源：`p1_live/ocr_mvp_v1.py:305–350`。

```text
 305     def run(self):
 306         T0 = time.time()
 307         lockfd = os.open(PROD_LOCK, os.O_RDWR)
 308         try:
 309             fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
 310         except BlockingIOError:
 311             raise Stop('production controller lock busy; unique controller not available')
 312         ledger = Ledger(LEDGER)
 313         need(not ledger.unresolved(), 'ledger has unresolved operations: %r' % ledger.unresolved())
 314         self.rec.event(kind='start', policy=POLICY, request=REQUEST_ID, send=self.send)
 315         s = time.time(); wxio.ocr_engine(); self.t('init:ocr_model', s)
 316 
 317         # READY: activate, verify account.
 318         o = wxio.observe()
 319         g = o['main']['geom']
 320         need((g['w'], g['h']) == MAIN_SIZE, 'main geometry not calibrated')
 321         if not o['active_is_wechat'] or o['active'] != o['main']['id']:
 322             need(len(o['wechat']) == 1, 'unexpected WeChat transient at start')
 323             self.epoch += 1
 324             self.rec.event(kind='input', label='activate', point=abspt(g, W_ACTIVATE), epoch=self.epoch)
 325             self.x.click(*abspt(g, W_ACTIVATE))
 326         f = self.perceive('ready', lambda f: {}, wait=0.8)[0]
 327         self.act(f, abspt(g, W_AVATAR), 'avatar', [g['x'], g['y'], g['w'], g['h']])
 328 
 329         def account(f):
 330             pops = [w for w in f['owner']['wechat'] if w['id'] != f['owner']['main']['id']]
 331             if len(pops) != 1 or pops[0]['type'] != '_NET_WM_WINDOW_TYPE_UTILITY,':
 332                 raise Unknown('self profile popup not unique')
 333             return perceive_account(f['image'], pops[0]['geom'])
 334         time.sleep(1.0)
 335         s = time.time()
 336         f = self.rec.capture('account'); v = None
 337         try:
 338             v = account(f)
 339         finally:
 340             self.epoch += 1
 341             self.x.key('Escape')   # dismiss popup regardless
 342         self.t('perceive:account', s)
 343         self.rec.event(kind='observation', tag='account', value=v)
 344         need(v['weixin_id'] == ACCOUNT, 'wrong account: %r' % v['weixin_id'])
 345 
 346         # CONTACTS
 347         f = self.perceive('ready2', lambda f: {}, wait=0.8)[0]
 348         self.act(f, abspt(g, W_CONTACTS_TAB), 'contacts-tab', [g['x'], g['y'], g['w'], g['h']])
 349         f, c = self.perceive('contacts', lambda f: perceive_contacts(f['image'], f['owner']['main']['geom']),
 350                              check=lambda c: None if c['top_proof'] and c['rows'] else (_ for _ in ()).throw(Unknown('no top proof/rows')))
```

## E5 收件人资料、聊天、收藏关联与选择

来源：`p1_live/ocr_mvp_v1.py:363–413`。

```text
 363         # PROFILE
 364         def prof_check(p):
 365             if not p['selected']:
 366                 raise Unknown('clicked row not shown selected')
 367         f, p = self.perceive('profile', lambda f: perceive_profile(f['image'], g, target['band']), check=prof_check)
 368         need(p['weixin_id'] != ACCOUNT and p['name'] not in SELF_NAMES, 'profile is self')
 369         need(p['friend_profile'] and p['calls'], 'profile is not a clearly ordinary friend')
 370         need(norm(p['name']) == norm(target['name']) and norm(p['name']),
 371              'row/profile association mismatch: %r vs %r' % (target['name'], p['name']))
 372         self.chain.update(profile_frame=f['id'], profile_name=p['name'], weixin_id=p['weixin_id'])
 373         op_key = '%s|%s|wxid:%s' % (REQUEST_ID, ACCOUNT, p['weixin_id'])
 374         st = ledger.state(op_key)
 375         need(st is None, 'logical operation already exists in ledger (%s); no re-dispatch' % st)
 376         self.act(f, p['messages'], 'profile-messages', [g['x'], g['y'], g['w'], g['h']])
 377 
 378         # CHAT
 379         def chat_check(ch):
 380             if norm(p['name']) not in norm(ch['title']):
 381                 raise Unknown('chat title %r does not match profile %r' % (ch['title'], p['name']))
 382         f, ch = self.perceive('chat', lambda f: perceive_chat(f['image'], g), check=chat_check, wait=1.5)
 383         need(ch['composer_empty'], 'composer has unexplained content (draft?)')
 384         need(ch['send_disabled'], 'chat Send not in disabled state')
 385         self.chain.update(chat_frame=f['id'], chat_title=ch['title'])
 386         self.act(f, ch['cube'], 'favorites-entry', [g['x'], g['y'], g['w'], g['h']])
 387 
 388         # FAVORITES (zero-select baseline)
 389         def base_check(v):
 390             if v['send'] != 'disabled' or any(r['checked'] for r in v['radios']):
 391                 raise Unknown('panel not at zero-select baseline: send=%s' % v['send'])
 392         f, pv = self.perceive('favorites', lambda f: perceive_panel(f['image'], f['panel']['geom']),
 393                               want_panel=True, check=base_check, wait=1.5)
 394         panel = f['panel']
 395         need(norm(p['name']) in norm(pv['header']) and norm(pv['header']).startswith('Sendfavoritesto'),
 396              'panel header not bound to recipient: %r' % pv['header'])
 397         need(pv['all_favorites'] and 'SearchFavorites' in norm(pv['search_text']), 'panel filter/search not default')
 398         need(pv['first_at_top'], 'first favorite not at calibrated top position')
 399         self.chain.update(panel_frame=f['id'], panel_id=panel['id'], panel_header=pv['header'])
 400         first = pv['radios'][0]
 401         pg = panel['geom']
 402         self.act(f, (first['x'], first['y']), 'select-first', [pg['x'], pg['y'], pg['w'], pg['h']])
 403 
 404         # SELECTED
 405         def sel_check(v):
 406             if v['send'] != 'enabled' or [r['checked'] for r in v['radios']] != [True] + [False] * (len(v['radios']) - 1):
 407                 raise Unknown('not exactly first selected: send=%s radios=%r' % (v['send'], [r['checked'] for r in v['radios']]))
 408         f, sv = self.perceive('selected', lambda f: perceive_panel(f['image'], f['panel']['geom']),
 409                               want_panel=True, check=sel_check, wait=0.8)
 410         need(f['panel']['id'] == panel['id'] and f['panel']['geom'] == pg, 'panel identity changed')
 411         need(norm(p['name']) in norm(sv['header']), 'panel recipient binding lost')
 412         need(abs(sv['radios'][0]['y'] - first['y']) <= 2, 'list moved after selection')
 413         send_pt = abspt(pg, P_SEND_CLICK)
```

## E6 发送事务与发后等待

来源：`p1_live/ocr_mvp_v1.py:424–444`。

```text
 424         # DISPATCH: durable intent first, then exactly one Send.
 425         ledger.put(op_key, 'PREPARED', intent=intent, recipient_ref=json.dumps(self.chain, ensure_ascii=False))
 426         need(time.time() - f['at'] < POLICY['capture_max_age_s'], 'frame expired before dispatch')
 427         live = wxio.observe()
 428         need(live['active'] == panel['id'] and live['main']['geom'] == g, 'context changed before dispatch')
 429         ledger.put(op_key, 'DISPATCHING', result=dict(at=time.time()))
 430         try:
 431             s = time.time()
 432             self.epoch += 1
 433             self.rec.event(kind='input', label='SEND', point=send_pt, frame=f['id'], epoch=self.epoch, op_key=op_key)
 434             self.x.click(*send_pt)
 435             self.t('input:send', s)
 436         except BaseException as e:
 437             ledger.put(op_key, 'UNKNOWN', result=dict(error=repr(e)))
 438             self.rec.event(kind='send_unknown', error=repr(e))
 439             raise
 440         ledger.put(op_key, 'SEND_CLICKED', result=dict(at=time.time(), frame=f['id']))
 441         self.rec.event(kind='send_clicked', op_key=op_key)
 442         time.sleep(1.5)
 443         self.rec.capture('after_send_evidence_only')
 444         return self.finish('send_clicked', T0, intent)
```

## E7 窗口扫描与同步截图记录

来源：`p1_live/wxio.py:81–136`。

```text
  81 def observe():
  82     """Window ownership snapshot: main WeChat window, active window, WeChat windows."""
  83     pid = wechat_pid()
  84     active, stack = root_context()
  85     wins = []
  86     for w in stack:
  87         p = wid_props(w)
  88         m = re.search(r'_NET_WM_PID\(CARDINAL\) = (\d+)', p)
  89         if not m or int(m.group(1)) != pid:
  90             continue
  91         g = geometry(w)
  92         if not g['viewable']:
  93             continue
  94         name = re.search(r'_NET_WM_NAME\(UTF8_STRING\) = "(.*)"', p)
  95         tr = re.search(r'WM_TRANSIENT_FOR.*?(0x[0-9a-fA-F]+)', p)
  96         wtype = re.search(r'_NET_WM_WINDOW_TYPE\(ATOM\) = (\S+)', p)
  97         wins.append(dict(id=w, name=name.group(1) if name else '', geom=g,
  98                          transient=int(tr.group(1), 16) if tr else None,
  99                          type=wtype.group(1) if wtype else None))
 100     mains = [w for w in wins if w['name'] == 'Weixin' and w['transient'] is None]
 101     need(len(mains) == 1, 'exactly one visible Weixin main window required: %r' % mains)
 102     return dict(pid=pid, active=active, stack=stack, wechat=wins, main=mains[0],
 103                 active_is_wechat=any(w['id'] == active for w in wins),
 104                 top_is_wechat=bool(stack) and any(w['id'] == stack[-1] for w in wins))
 105 
 106 
 107 class Recorder:
 108     def __init__(self, run_id):
 109         self.dir = OUT / run_id
 110         self.dir.mkdir(mode=0o700, exist_ok=True)
 111         self.log = (self.dir / 'events.jsonl').open('a')
 112         self.n = 0
 113 
 114     def event(self, **kw):
 115         kw.setdefault('t', time.time())
 116         self.log.write(json.dumps(kw, ensure_ascii=False, default=str) + '\n')
 117         self.log.flush()
 118         os.fsync(self.log.fileno())
 119         print('EVENT', json.dumps(kw, ensure_ascii=False, default=str)[:600], flush=True)
 120 
 121     def capture(self, tag):
 122         before = observe()
 123         at = time.time()
 124         im = ImageGrab.grab(xdisplay=':1').convert('RGB')
 125         after = observe()
 126         need(before['main']['geom'] == after['main']['geom'] and before['active'] == after['active'],
 127              'window context changed during capture')
 128         self.n += 1
 129         path = self.dir / ('%02d_%s.png' % (self.n, tag))
 130         im.save(path)
 131         os.chmod(path, 0o400)
 132         frame = dict(id=self.n, tag=tag, path=str(path), at=at, owner=after, image=im)
 133         self.event(kind='capture', frame=self.n, tag=tag, path=str(path),
 134                    active=after['active'], main=after['main'], active_is_wechat=after['active_is_wechat'],
 135                    wechat=[(w['id'], w['name'], w['geom'], w['transient']) for w in after['wechat']])
 136         return frame
```

## E8 epoch、窗口归属与单次点击

来源：`p1_live/ocr_mvp_v1.py:272–284`。

```text
 272     def act(self, frame, point, label, window_rect):
 273         """Single click bound to the frame it was decided on."""
 274         need(time.time() - frame['at'] < POLICY['capture_max_age_s'], 'frame expired before input')
 275         need(frame['epoch'] == self.epoch, 'stale ui_epoch')
 276         live = wxio.observe()
 277         need(live['active'] == frame['owner']['active'] and live['main']['geom'] == frame['owner']['main']['geom'],
 278              'live window context changed since frame')
 279         x, y = point
 280         rx, ry, rw, rh = window_rect
 281         need(rx <= x < rx + rw and ry <= y < ry + rh, 'target outside owning window')
 282         self.epoch += 1
 283         self.rec.event(kind='input', label=label, point=point, frame=frame['id'], epoch=self.epoch)
 284         self.x.click(x, y)
```

## E9 通讯录行提取

来源：`p1_live/ocr_mvp_v1.py:117–145`。

```text
 117 def perceive_contacts(image, g):
 118     texts = ocr(image, absbox(g, W_LIST))
 119     texts.sort(key=lambda t: t[2][1])
 120     find = lambda pat: [t for t in texts if re.search(pat, re.sub(r'\s+', '', t[0]))]
 121     search, manage = find(r'^\W?Q?Search$'), find(r'ManageContacts$')
 122     official, header = find(r'OfficialAccounts'), find(r'^\W?V?Contacts$')
 123     if not (search and manage and header):
 124         raise Unknown('contacts pane markers missing: %r' % [t[0] for t in texts])
 125     hy = header[0][2][1] + header[0][2][3]
 126     # Top proof: Search then Manage Contacts are the first two items, nothing hidden above;
 127     # between Manage Contacts and the Contacts header only the collapsed Official Accounts header.
 128     top = (search[0] is texts[0] and manage[0] is texts[1]
 129            and manage[0][2][1] - g['y'] < 120
 130            and all(t in official or t in header for t in texts[2:texts.index(header[0]) + 1]))
 131     rows = []
 132     for t in texts:
 133         if t[2][1] <= hy:
 134             continue
 135         tx = t[2][0] - g['x']
 136         if tx < 100 and re.fullmatch(r'[A-Z#]', t[0].strip()):
 137             continue  # letter index
 138         if tx < 70:
 139             continue
 140         cy = t[2][1] + t[2][3] // 2
 141         band = [g['x'] + 61, cy - 27, 240, 54]
 142         complete = band[1] >= hy + 4 and band[1] + band[3] <= g['y'] + g['h'] - 2
 143         rows.append(dict(name=t[0].strip(), score=t[1], text_box=t[2], band=band, complete=complete,
 144                          center=(g['x'] + 170, cy)))
 145     return dict(top_proof=top, header_count=[t[0] for t in texts if re.fullmatch(r'\d+', t[0])],
```

## 核对文件 SHA-256

```json
{
  "ocr_mvp_v1.py": "d59587c9fea325fcf7c8d28c8325bf4d5bed913f578eb878eac37eef3e63c827",
  "wxio.py": "db44698f92cb1707e2a13f0545f9b6b12a3412b738a9b3345251940981c5cae6",
  "P1_REPORT.md": "498a57ecf9b09686a7fd670d9f583c39ec322b42fbc65f9046c3c9fae39134fc",
  "evidence/run_20261014T171331_send/result.json": "c6cd8417f7788534a17d065836299445fd2bd5e7e09a78925326b6eecfb6d317",
  "evidence/run_20261014T171331_send/events.jsonl": "a7b2be453dbe5a9dedb3b691791fc8b17467d9354fe2c50fd452b677afc8150f"
}
```
