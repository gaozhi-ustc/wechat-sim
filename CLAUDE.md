# CLAUDE.md — wechat-sim 接手须知

微信 OCR 自动化（加星、审计、删除不可达好友、群发收藏）。完整开发史与历次运行记录见 [agent.md](agent.md)（很长，按需查阅）；运行结果见 [result.md](result.md)。

## 1. 仓库内容约定：哪些能提交

`.gitignore` 规定：`p1_live/` 下**只跟踪 `*.py` 和 `templates/`**。截图证据、账本 sqlite、远端日志、运行报告都含联系人姓名/微信号，只留本地。

提交时：
- 只 `git add p1_live/*.py`（如有模板变动再加 `p1_live/templates/`），不要 `git add -A`。
- 根目录的 `*.log`（`audit_starred_* / delete_unreachable_* / send_nonstarred_* / star_v1_*`）和 `supervise.jsonl` 是运行日志，**不提交**。
- `xixi` 是凭据/会话文件，已忽略，绝不提交。
- 提交前先 grep 一遍新增的 `.py` 有没有硬编码联系人姓名或微信号，有就挪到本地被忽略的文件里。
- 只在用户要求时提交/推送；远端 `origin = git@github.com:gaozhi-ustc/wechat-sim.git`，分支 `main`。

## 2. 禁发名单（do-not-send）

- 用户的永久指令：名单里的人**任何活动都不能发消息**。
- 代码 `p1_live/do_not_send.py` 已提交，名单数据在 **`p1_live/do_not_send.json`**（git 忽略，只在本地）。格式：`[["weixin_id", "显示名"], ...]`。
- JSON 缺失或为空时 `do_not_send.py` 在 import 时直接报错，所有发送路径都跑不起来（故意的安全设计）。从 GitHub 新 clone 或换机器时，必须先从本机拷贝这个 JSON，不要为了让程序跑起来就去掉这个检查。
- 检查点：`batch_v2.process`（资料页 OCR 后，结果为 `EXCLUDED_DO_NOT_SEND`）和 `ocr_mvp_v1.Ledger.put(..., 'PREPARED')`（每次点 Send 前）。新写的发送脚本必须走这两处之一。
- 用户要增减名单时，只改 JSON。
- **部署注意**：`~/wechat_batch/p1_live/do_not_send.py` 目前还是旧版（名单硬编码），能正常工作。下次把仓库代码同步到 `~/wechat_batch/p1_live/` 时，要把 `do_not_send.json` 一起拷过去，否则发送脚本 import 失败。

## 2.5 群发收藏到聊天群（send_groups.py，2026-10-31 新增）

用途：把**当前最新的收藏**（Favorites 第一张）推进所有**成员数 ≥ 20** 的聊天群，排除群名含 `科大` / `65周年` 的群；服务号/公众号（Official/Service Accounts）忽略。

- 脚本 `p1_live/send_groups.py`，**默认 dry run**，必须显式 `--send` 才真发。
- 三种模式：
  - 全量枚举 `--send`：逐个打开 Chats 列表里的会话，用标题末尾的 `(N)` 取成员数；`Minimized Groups` 子列表也会进去枚举。
  - 定向 `--only names.txt`：每行一个群名，可写 `群名<TAB>成员数`；用 Chats 搜索框（GTK 剪贴板 + Ctrl+V 支持中文）定位。
  - 名单 `--roster groups_roster.json`：按已知群名单逐个搜索发送，最快；接受少量漏发。
- 本地文件（git 忽略、含群名，**不要提交**）：
  - `p1_live/sent_groups.json`：本 campaign 已成功发送的群（name/members/request/at）。同一活动（REQUEST_ID 相同）再跑时会**按行名模糊匹配直接跳过**，不再打开。
  - `p1_live/groups_roster.json`：已知 20+ 人群名单（name/members），下次活动可直接 `--roster` 用它。
- 每次发送前四道校验：行名↔聊天标题一致、信息面板确认是群、面板头 `Send favorites to "<群名>"` 绑定、面板第一张收藏标题与 campaign 一致；全过才点 Send。账本 `PREPARED→DISPATCHING→SEND_CLICKED`，同一活动不重复发。
- 现场注意：微信通知窗口（WeChatAppEx 进程）会抢焦点，脚本用 X11 `XSetInputFocus` 抢回；Chats 列表随新消息不断重排，点击前会二次核对行名，点偏时以**实际打开的会话标题**为准（不会发错群）。
- **群名以聊天标题为准**：若发现名录里的群名与实际标题不一致（改名、被截断），自动改写 `groups_roster.json` 的 `name` 字段并记 `roster_renamed` 事件；仅当两者互为子串（确属同一个群）时才改，子串搜索命中别的群则不动。
- 已知限制：群标题的 `(N)` 偶发 OCR 读不到（用 roster 里的成员数兜底，否则记为 `NOT_A_GROUP`/`TITLE_TRUNCATED` 并在 groups.jsonl 里可见）；全名搜索偶尔不命中，会退化为子串搜索。

### 2.5.1 链接 + 文字必须成对发送（用户规则 2026-11-12）

如果一次活动既要发链接又要发一段文字，**必须在同一个群里发完链接后立刻发文字**，再切下一个群。
不要"先跑一遍所有群发链接，再跑一遍所有群发文字"——两条消息会相隔几十分钟甚至几小时，群成员看到的上下文是断的。

已实现（2026-11-12）：`send_groups.py --text-file FILE`（或 `--text "…"`）。点完 Send 退出面板后，在**同一个聊天**里点输入框、清空残留、粘贴文字、核对输入框、回车、再核对消息出现在聊天中（`text_sent` 事件，`verified` 字段）。文字失败不影响该群已发出的链接（只记 `text_not_filled`/`text_error`，不中断）。
2026-11-12 那次因为先发完 59 个群的链接再统一发文字，被用户指出不连贯；那次 59 个群里有 31 个第二遍连群都没打开（`CHAT_NOT_OPENED`），进一步说明成对发送更可靠。

## 2.6 运行环境变量（2026-11-01 实测，代码默认值已全部失效）

代码里的默认路径指向 `/home/gaozhi/fav_forward_20261010/upgrade_20261010T1529/`，**该目录已不存在**。现在跑任何脚本都必须显式给全这四个变量（缺 `WX_SITE` 会 `ModuleNotFoundError: numpy/cv2`，缺 `WX_LOCK` 会 `FileNotFoundError`）：

```
WX_SITE=/home/gaozhi/wechat_batch/ocr_site_20261013T1355      # cv2/numpy/onnxruntime/rapidocr 都在这里
WX_ACCOUNT=assfox
WX_LEDGER=/home/gaozhi/wechat_batch/ledger_assfox.sqlite3     # 真实账本（含 campaigns 表）；p1_live 下那几个是历史账
WX_LOCK=/home/gaozhi/wechat_batch/controller.lock
```

完整示例（定向发一个群，先 dry run 再真发）：

```bash
cd p1_live
ENV="WX_SITE=/home/gaozhi/wechat_batch/ocr_site_20261013T1355 WX_ACCOUNT=assfox \
WX_LEDGER=/home/gaozhi/wechat_batch/ledger_assfox.sqlite3 WX_LOCK=/home/gaozhi/wechat_batch/controller.lock"
printf '群名\n' > only_x.txt            # p1_live/*.txt 已被忽略
env $ENV python3 -I send_groups.py --no-send --only only_x.txt
env $ENV python3 -I send_groups.py --send    --only only_x.txt
```

注意：`python3 -I` 会屏蔽 user site-packages，所以 `WX_SITE` 不是可选项——numpy/cv2 只有这个目录里有。查某个活动发过哪些群，去 `~/wechat_batch/ledger_assfox.sqlite3` 的 `ops`（`op_key LIKE '%|group:%'`）和 `campaigns` 表，不要看 `p1_live/*.sqlite3`。

## 3. GitHub SSH 走 443 端口

本机网络连 `github.com:22` 能建 TCP，但 SSH 握手一直卡住（`git push` 无输出挂起）。已在 `~/.ssh/config` 配好（2026-10-31）：

```
Host github.com
    HostName ssh.github.com
    Port 443
    User git
    HostKeyAlias github.com
```

- `HostKeyAlias github.com` 让 ssh 复用 `known_hosts` 里已有的 github.com 主机密钥，不用另加信任。
- 验证：`ssh -T git@github.com` 显示 `Hi gaozhi-ustc! ...` 即正常（返回码 1 是 GitHub 不给 shell 的正常结果）。
- 配好后正常 `git push origin main` 即可，remote 不用改。
- 如果配置丢失又卡住，临时绕过办法：
  `GIT_SSH_COMMAND='ssh -o HostKeyAlias=github.com -p 443' git push ssh://git@ssh.github.com:443/gaozhi-ustc/wechat-sim.git main`

## 5. 与 LLM 交互的约定（用户规则 2026-11-01）

- **非必要不带图片请求 LLM 端点**：截图/证据图只在确实需要“看图判断”时才附上；能从 OCR 文本、`events.jsonl` / `groups.jsonl` / `result.json`、日志、代码推断出来的，一律不要带图。
- 单次请求最多 16 张图；确实需要更多就拆成多次请求。
- 纯命令/文本类操作（`git add/commit/push`、`grep`、`ls`、编译、读代码、看日志）**不需要也不应该**带图片。
- 需要看图时优先裁切到相关区域、必要时先降分辨率，避免整屏大图。

## 4. 操作记录

- 2026-10-30：提交 `121a940`。新增 `star_v1 / star_apply / audit_starred / chatlist_scan / delete_unreachable / delete_by_id / notice_ids / send_starred / send_nonstarred / do_not_send`，并更新了 `batch_v2 / ocr_mvp_v1 / supervise`。同时把禁发名单从代码挪到本地 JSON。推送时遇到 22 端口卡住，改走 443 成功。
- 2026-10-31：配置 `~/.ssh/config`（见第 3 节），`ssh -T` 和 `git fetch` 验证通过。
- 2026-10-31：新增 `p1_live/send_groups.py`（群发收藏到 20+ 人群，排除含 `科大`/`65周年` 的群）。首次 campaign `fav_assfox_20261031T182950`（收藏 `【SDD系列06】老板的终极梦想，让业务参与开发！`），全量枚举 + 定向补发 + 名单复查共发送 40 个群；本地生成 `sent_groups.json` / `groups_roster.json` 供下次模糊搜索复用。
- 2026-11-01：用户发布新收藏 `【SDD系列07】代码都让AI开发了，人类做什么？`（campaign `fav_assfox_20261101T004150`），再次全量扫描（954 个不同会话，扫描到滚动上限后改用 `--roster` 补齐）并发送 45 个群；新发现 6 个之前没发过的群（杭州六小龙丨创新生态 455、2018湖北网商大会 344、第十八届中国工业论坛1 192、元界财经AI+群 153、2025&2026年-燕园叶话-线下参会群 44 等）；`groups_roster.json` 去重后 45 个群。按规则排除 6 个含 `科大`/`65周年` 的群。
- 2026-11-01：提交 `a3e89ec` 并推送 `p1_live/send_groups.py`（群发收藏到 20+ 人群，含 `--only` / `--roster` 搜索模式与本地已发记录）。同日修掉 3 个漏发缺陷（点开后旧标题误读、面板切换晚导致放弃、失败仍登记已访问）并补齐 `016`/`037` 两个 AI 区块链群；本活动累计 48 个群。
- 2026-11-01：新收藏 `【SDD系列08】AI开发的业务系统能不能打？新系统的真正大考！`（campaign `fav_assfox_20261101T155714`）。15:57 全量枚举发 22 群（15:50/15:57 两次均因窗口几何/`chats_top` 未就绪提前中止，15:57 这次仍有 22 群成功），16:33 再全量枚举发 32 群，17:13 roster 补发 3 群 → 累计 **57 群**。
  - 17:13 轮报的两个 `SEARCH_FAILED` 中，`算力百科IDeepSeek前瞻12群` 其实本活动早已 `SEND_CLICKED`（16:14，账本可查），属于本地 `sent_groups.json` 漏记导致的重复搜索；真正没发出去的只有 `AI之光4群+`（搜索命中了 `A之光群计(361)`，行名不符）。
  - 教训：`sent_groups.json` 可能与账本不同步（`record_sent` 只在 `members` 非空时补登），核对“本活动发了哪些群”**以 `~/wechat_batch/ledger_assfox.sqlite3` 为准**。
- 2026-11-01 22:05：定向新增群 `模型训练小组`（57 人）。先 `--no-send` 校验通过（四道校验全过、收藏标题 ratio 1.0），再 `--send` 发送成功，账本 `SEND_CLICKED`。`groups_roster.json` 增至 56 个群，`sent_groups.json` 已按账本回填至 146 条（三个 campaign 逐一对齐 40/48/58）。同日确认并记录第 2.6 节的环境变量（原默认路径已失效）。
- 2026-11-02 18:43：新收藏 `【SDD系列09】文档就是生产力！《文档驱动开发操作实践》`（campaign `fav_assfox_20261102T184343`）。用 `--roster all_recorded_groups.json`（roster 56 群 ∪ sent_groups 去重后仍是 56 群）跑全量定向，**56/56 群全部 `SEND_CLICKED`**，用时 1118s。
  - 唯一漏发是 roster 里的旧名 `算力百科IDeepSeek前瞻12群`：真实群名是 `算力百科|DeepSeek前瞻12群(440)`（早先 OCR 丢了 `|`），全名搜不到、子串 `算力百科` 才命中。已用 `--only`（先 `--no-send` 验证）补发成功，roster 里的错名已改成真名。
  - 经验：`SEARCH_FAILED` 且搜索结果里有近似名时，先用 `--no-send --only` 试更短的子串查询，确认打开的是同一个群再 `--send`；`groups_roster.json` 的群名应以实际聊天标题为准（含 `|`、`@` 等符号）。

- 2026-11-03：给**所有非星标好友**发送 `【SDD系列09】`（campaign `fav_assfox_20261102T184343`，与群发同一活动，账本里 `|wxid:` 与 `|group:` 键并存）。
  - 用户确认口径：**以 `ledger_star_assfox.sqlite3` 为准**判断"星标"（账本 679 条 STARRED，微信 Starred 分区当时只显示 77 人），这 500+ 人一律跳过。`send_nonstarred.py` 的 `exclude_recipient` 就是这个口径，不要改成按微信 UI 判断。
  - 14:15 从顶部全量扫（`--from-top`）：第 1 轮 2338 人、发 1768，因"连续两次 pre-send 失败"停；第 2 轮 `--from-current` 续跑到列表底部（`scroll_no_change`）再发 352 → **本活动好友共 2121 人 `SEND_CLICKED`**（+ 56 群）。
  - 送达：2084 `DELIVERED` / 20 `SEND_FAILED`（红 !）/ 15 `UNREACHABLE`（需朋友验证，明细在 `evidence/unreachable_20261103.jsonl`）/ 1 `UNCERTAIN`。
  - 未发：37 个 `SKIPPED_PRE_SEND`（校验不过，宁可不发）、14 个 `SKIPPED_UNREADABLE_NAME`（emoji/符号名）、5 `EXCLUDED_UNAVAILABLE`、2 `EXCLUDED_NOT_ORDINARY`、2 禁发名单、1 自己。顶部到底部共 2706 行被处理，与 header 计数 2712 差 6 行（页面边缘的 partial row）。
  - **为跑通修了 3 个真 bug**（都是 `batch_v2.py`，会影响所有批量发送）：
    1. `perceive_page` 把 `Starred` 分区标题当成联系人行 → 点击只展开分组、`row_to_profile` 超时崩溃；现按名字过滤 `starred/tarred`；
    2. `run()` 从顶部起跑时，跳过首页开头"无名字"的行（OCR 漏读的分区标题）；
    3. `sent_folded()` 用 `k.split('|wxid:',1)[1]`，同一 REQUEST_ID 里有 `|group:` 键时抛 `IndexError` —— 群发后再给好友发会当场崩；现只查 `op_key LIKE '%|wxid:%'`。`notice_ids.py` 同样问题已一并修。
  - `send_nonstarred.py` 新增 `--from-top`（全量从顶部扫）；`--from-current` 仍是续跑模式。
  - 长跑用 `/tmp/wx_nonstarred_supervisor.py <start_epoch> <max_attempts> <log>`：到点开跑，Stop 后用 `--from-current --ordinal-base N` 续跑，连续 3 轮零发送则退出。注意它的"完成"判断依赖 `tail.complete`，`--from-current` 模式下 occurrences 不等于 header_count，会误判为未完成（本次第 3–5 轮空转后自行退出，无副作用）。

- 2026-11-03 19:00：用户要求把这篇收藏（`【SDD系列09】`，campaign `fav_assfox_20261102T184343`）再发到所有群聊。
  - 先跑了一次全量枚举（`--send` 无 `--roster`），处理到 167 个会话时用户叫停（`pkill -f send_groups.py`）；这 167 个基本都是 `ALREADY_*`/`NOT_A_GROUP`，但**在被停之前已顺带发出 1 个新群 `2026智源大会参会者群29`（190 人，18:58）**。
  - 用户点名要补的"包含 智源大会 的三个群"（已确认都 >20 人），用搜索框枚举确认全名后定向补发：
    `2026智源大会参会者群29`(190)、`2025智源大会参会者群18`(158)、`2025智源大会智慧医疗交流群`(196) —— 全部 `SEND_CLICKED`。
  - 本活动群数：**59 个唯一群**（账本 op_key 有 60 条，因为同一个群被 OCR 读成 `A 开放计算中国社区` / `A开放计算中国社区` 两种写法）。
  - **修掉一个重复发送漏洞**：`send_groups` 的账本去重只用精确 `op_key`，群名带不带空格就会当成两个群。今天 `A 开放计算中国社区` 就因此被重复发了一次。新增 `campaign_group_state()`：按 `canon(群名)` 建本活动已发索引，精确键未命中时用它兜底（已验证 `A开放计算中国社区` 现在报 `ALREADY_SEND_CLICKED` 而不再重发）。
  - 另：`sent_groups.json` 里 3 条 `backfilled from ledger` 的占位记录与真实记录 canon 重复，已清理（205→202 条）；`groups_roster.json` 现 59 个群，三个智源群已入库。

- 2026-11-04 03:59：群补发复查结论 —— `非凡挚友群`（聊天窗显示"你被'吴畏'移出群聊"、底部横幅 Unable to send message in an exited group chat）和 `算力百科|DeepSeek前瞻12群`（搜索索引已不再返回该群，与被移出/解散吻合）**都已无法发送**；`AI应用实训课-学习答疑服务群` 只剩 9 人。三个群已从 `groups_roster.json` 移除（56 群），`sent_groups.json` 历史记录保留。`fav_assfox_20261103T234048`（SDD大结局）最终：56 群 + 524 位星标好友；星标发送被用户叫停，未收到的约 159 人多为 SKIPPED_PRE_SEND/EXCLUDED_UNAVAILABLE/不在通讯录。
