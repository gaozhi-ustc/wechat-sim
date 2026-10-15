# agent.md — 微信项目从头开发记录与暂停交接入口

> **当前最高优先级：PAUSED。** 2026-10-14 21:15+08 用户 `msg_mv84uv9r7cdtmlcumwi` 要求归档至 `wechat-sim`、记录全部开发过程并暂停交接其他 session。归档不等于微信业务完成，不得据此自动恢复。没有向未知 session 委派。

## 1. 记录方法、真实性和完整性边界

本记录基于本地已有规则/方案/测试/独审/部署/异常回执、CURRENT_HANDOFF及本session工具回执整理；不是把任务描述复制成成功事实。下文先按阶段说明开发、有效要求与纠偏，再完整纳入早期验收/接续/交接文档及累计3370行历史日志，并提供全部文档和原始/脱敏回执索引。历史日志原来主要倒序记录，**后文明确保留原顺序/原断言**，不能把某个阶段“待授权”“未完成”“COMPLETE”脱离对应请求当当前事实。历史错误与修复原文并存，置顶暂停和后续明确纠偏优先。

本地开发源根 `/tmp/wxview92`，项目规则根 `/tmp/wxview92/upgrade_20261010T1529`；此次复制在开发主机 `X79` 的 `/tmp/wxview92/wechat-sim/snapshot/`。原绝对路径与归档映射见README。全部原本地源码、测试、配置、公开ABI参考、OCR bundle/原生依赖/模型、私有候选、原图、大JSON、日志、审查/部署文档都采用保留相对目录的复制；没有只放链接壳、没有破坏性移动、没有改旧源码路径。

缺失范围：本地最早可核历史为2026-10-10已有旧发送事实的升级开发；此前原始人类聊天、所有session完整逐工具对话、远端才有的DB/操作日志/secret和被历史任务删除的临时文件未能在本地恢复。本次不联网、不下载未知来源补齐、不编造缺失过程。两个在 `/tmp` 根的已知微信计划已额外复制。Git元数据未复制，但真实只读status、index列表与原7个staged源码版本单独保存。缓存、DB备份、真实secret/lease文件被排除并记录安全源路径，不读取secret；部分JSON/日志授权值脱敏，source SHA与archive SHA分列，脱敏内容不能当原始证据/重新批准。

## 2. 当前真实状态：必须分请求/分环境

- **当前请求 `msg_mv6nn1hjqjrlfm6nuy9`（8027新一轮）：0发送，0真实 `send_clicked`；全自动发送未开始。** 用户20:25优先要求先一个普通好友OCR全链，但在本session得到首个clicked前，21:15暂停指令已取代继续推进。不能沿用上轮10人complete、旧11待办或到列表尾作为这轮完成。
- 最后现场证据是暂停前20:54合法锁内只读 `snapshot/ocr_first_terminal_readonly_1791982429309891739.jsonl`，epoch `1791982433.8309324`；remote_exit0/stderr空。唯一生产DB inode `[2050,5791809]`；third已closed、all_closed、lease_empty、full_no_unresolved=true；原exact21源码核对成功。
- CP v3已消费20operations/8captures/3notches/0rows/0Contacts-entry/3sessions；剩140/72/45/24/1/**0sessions**。历史stop保留，effectivehealthy。第三SID `2f86a0deb1b54318b1aee3f492b3f10e` 已20:37诚实close；closed不可复活、不能开第四CP或退款。两次row只有parent裕量不足not-attempted，**没有cp-row输入/消费/资料关联**。
- 暂停后父没有SSH/UI/OCR/Send/install或现场刷新。20:54不是21:15后再核验，也不保证未来现场。没有已知活跃owned lease需额外收尾；全部子任务已停止，见records/pause-and-children.md。
- 历史旧请求：2026-10-13 14:03上轮 `msg_mv61novv99ftwes71kb` 有10普通好友attempted/10原生卡片confirmed、3排除、13ordered/top+tail完整，0uncertain/remaining。那是上轮独立结论，非当前0发送的矛盾。完整周期均值717.646s/n10，含修复的总through-close13921.248s；未实现<60s。见归档NEW_ROUND_DELIVERY和final report。
- 更早2026-10-11：Citrus原生卡片发送及随后reconcile；另四位URL文字是真实交付，用户接受不补发例外，不能追认卡片。后续历史总10不重发与旧round/source/account/provenance保留。此记录不把此前总发送说成0。

## 3. 环境、SSH和不变安全边界

早期2026-10-10/11通过 `gaozhi@192.168.0.92` 原默认SSH22、DISPLAY=:1操作原环境，DB为原生产 `ledger.sqlite3`。原process/legacy双锁规则用于该阶段；历史窗口ID77594749/PID2522627/XRes同clientbase等都是当时事实，**不能硬编码到现环境**。当前明确有效环境从后续用户隔离决定起变为仅 `ssh -T -p8027 -o BatchMode=yes -o ConnectTimeout=12 gaozhi@192.168.0.92`、host `zcx-la`、DISPLAY=:1、账号 `gaozhi-xinshu`，唯一活动 `ledger_8027.sqlite3`。禁止旧22/8127/244/Q3。同IP同目录不等于相同session/进程/账；8027现场实际已证实的是f.locked的cutover/inode/lease+controller.lock flock，**没有额外legacy_guard证据，不能声称双锁**。

归档未连接8027，也未在8027写wechat-sim。现开发环境为X79。本地备份DB不作为第二控制器台账，不复制DB供执行。原credential只在既有远端私有路径，归档引用路径不含明文值；不得读取旧closedcredential恢复或换request清账。

发送安全仍是：唯一控制器/原账/所有权与账号/独占lease/来源pin；operation durable先行、intent/reservation先单次Send，真实返回原子持久clicked；unknown/submitted/orphan不可重放，历史confirmed不改；capture/source<180s、profile/scroll lineage<360s、两帧overlap各<180s，rows→row同帧、input使latest失效。取消60s目标不取消180/360。最新业务`send_clicked`只说明Send调用成功且持久化，未核验送达/已读；禁止CopyURL和发送后卡片/时间核验。全量尾证据只用于最终coverage，首人仍需真实top和可见行全分类。本人/系统排除，普通gaozhi不当本人；昵称advisory允许错误/空/重复，一人至多一次辅助OCR，不把精确昵称变身份门槛。

## 4. 从头的分阶段开发与关键纠偏

### 4.1 2026-10-10：升级dry-run与安全发送适配器

最早升级加入SQLite联系人/规范文章键/证据manifest/持久租约/锁，真实17页连续覆盖15条目、13普通+2特殊；9个精确ID、4个字符歧义，旧两人短链unmapped保守阻塞。新版submit实测SEND_DISABLED、28隔离测试及独审，不假称全自动发送。详见后文完整DELIVERY。

接续核四个ID、真实导航移动窗口使旧geometry拒绝，再新图成功；短链经实测遇captcha无法canonical mapping，不猜同标题。新增sender_v2单click+durableintent/uncertain守卫，21新隔离测试独审、CLI默认拒绝，未真实发测试消息。Git源代码repo首次创建后作者缺失，7文件staged/no commits，未伪造作者或改全局config。原Q3不动。详见完整CONTINUATION及BATCH/CONTACTS_REPAIR交付文档。

### 4.2 2026-10-11：有效自主接手、时效策略、Citrus与资料所有权

早期“只截图”委托已作废，原worker停止closed；新控制器接受06:54自主修复、07:37左侧好友顺序/当前绿色下一位/微信号/Messages/第一收藏/尾后回查前部，10:53继续。原anchor Cherry n02，首待办Citrus n03，旧11不能最终覆盖。收藏原Attention文章由sentinel→CopyURL核定（后来新workflow取消此固定文章条件）。

真实picker流程因profile180s与工具往返不足失败；不是让人重复授权。same-session-binding-v1保持globalMAX_AGE180、profile/article原证据同连续合法事务360不续期，current/final180、preintent/preclick双deadline、immutablewatermark。Citrus02:44:23UTC一次Send显示Forwarded；intent/submitting/pairreservation永久保留，后续不能重发。修returnChats独审部署，只见articlecard/time不等于全reconcile。聊天标题实际chat-info sidebar、侧栏avatar才精确popup；hiddenleader/transient超main旧guard安全停，实际已输入capture失败不可洗成未输入。XRes只读双采样和公开ABI资料支持popup所有权，独立continuation-only新模块、sourcepins，禁止全局放宽BatchDesktop或伪main_active。Task1/2独审有效、Task3/4旧审中断需补，当时7–9未做不是后来永久未做；后续实现/审查/现场闭环在累计日志逐条保留。

用户后改顺序直发URL路径，四人URL真实交付；18:13质疑卡片形态暂停，18:18用户接受四人不补发、Citrus卡片保留、恢复剩余原生收藏卡片。cube语义经用户明确只打开收藏选择窗、另选另Send。原生panel WM_TRANSIENT_FOR=main vs旧profilehiddenleader再次安全停止；Favorite专用owner规则和stopped-open恢复独审。PERF1重复历史审计实测导致180s失败，不能凭绿色mock测试批准；修同栈重复计算及PERF2真实readonly审计2.482s（非每人吞吐）。Cancel预算已burn不可退款，22:34用户一次Cancel及类似低风险自主决策授权，经独立append-only例外一次真Cancel/主窗验证close。

### 4.3 2026-10-11晚至12早：列表恢复、原生卡片/精确身份与尾前部

新增Contacts reanchor、native prepare/send/reconcile、Session admission与crash/cancel tests；CE、NSR、partialrow、movingheader、nativeFriends再测等有限实际缺口持续最小修复独审，不重放成功input。n08资料短alias错误按append-only精确fullID纠正，历史错误保留，不悄改旧身份。n09/n10/n13/n14/n15原生卡片真实confirmed，系统项排除，尾部真实建立后仍回查前部；parent requestshape/missingattestation错误诚实stopclose。最终原旧十人历史事实保留，包括四URL例外，不把URL当card。

### 4.4 2026-10-12：DB简化、不同8027环境与第一收藏规则

用户10:08改简化DB去重脚本并允许recovery-from-recovery，旧递归source阻塞不代表授权永久缺口。DB store/UI/CLI/native adapter独审；实际8027与旧环境不同，用户12:38明确environment isolation，原ledger不能盲迁移当前账号。原第一收藏不符Attention时没有新发，后12:19用户明确只发当前第一条；文章key绑定本round，旧confirmed依旧文章不是新文章全局排除。独立ledger8027初始化/准入后的CopyURL transition缺陷等定点修复，2026-10-12 07:51UTC该轮完成（详细计数取对应final文档，不能移用到本新轮）。之后OCR优化可用局部页面锚点/state-machine，OCR不替代准确身份，外部上传或测速重复发不授权。

### 4.5 2026-10-12晚至13：OCR依赖、bootstrap/bridge/launcher与上一新round完成

持续本地独审的OCR vision/roster/region完整partition/页面ROI限制、bridge framedbackend/opaque registry/来源native metadata、真实bootstrap依赖闭包。生成OCR模块与sysconfig/ELF ABI解析是实际兼容问题，不能fake origin/registry。conditionalcapture、freshvalidation、native guard、helper enteredseal race、Runner同期等多处NEEDS_FIX由有限修复及独立复审闭合。auditpublication报告曾覆盖问题明确披露不洗历史。每一步synthetic/mock与实机blank/实际UI分开；一套本地成功不等于live全链。

2026-10-13用户明确新round，原request与origin消息绑定、原生卡片singleclick/confirmation流程独审部署。4人confirmed后第5人过期未Send、Cancel诚实close；辅助OCR一次限制在unsent rebind旧raw保留（即使空/错）、新profile/current证据仍fresh。12:48onefileUI rebind独审部署，14:03本独立旧轮10confirmed/13ordered完整，终态allclosed/unresolved空。计时含原始firstselection和修复，不能拿latestbind缩小耗时，不能叫<60成功。

### 4.6 2026-10-13 20:27起：当前8027真OCR新请求，至暂停仍0发送

用户 `msg_mv6nn1hjqjrlfm6nuy9` 原文“使用8027 跑一遍流程，给出时间消耗明细”，来源原微信会话，原首次控制器recordepoch `1791894436943282080`、UTC2026-10-13T12:27:16.943299+00:00（注意原epoch_ns和打印UTC存在微秒表示，保留原记录不改）。原anchor SHA `e69017f7717cca9541e465408e0ea7d9771e10ef5edebe6144b4db182298ae1e`；不以恢复重新计时，elapsed分准备/适配/故障/审查部署/运行OCR/input/journal/interval/缺口。当前自动发送未开始，不把手工非Send流程当自动性能。

A1 requeststore/A2directEngine/BcontinuousOCR/A3ownedAPI各源码组合独审；当前准入stillnotlive。有限noSend真实profile→Messages→chat→cube→panel和第一收藏checkbox/Cancel测样成功、真实blankOCR bootstrap成功，但旧probe root与生产root、进程registry不兼容；不能blankreceipt冒全发送准入。private真实four-scenes/live模板遇palette/regionenvelope/roster中心avatar/pointerhover等拒绝，single-accepted control模式只是显式语义角色局部入口，不全局宽松。

2026-10-14昵称纠偏后advisory+pointermotion-only+单态checkbox/Send候选、chat/panel实像/privateprofilefragment分步独审。本人账号gaozhi-xinshu，gaozhi普通，昵称不精确门槛。account入口路径被六场景strictprofile与真实Contacts嵌入资料阻断，引入explicit authenticated-history-only四场景、无account-open/bind/dismissfallback，Session/Engine/review共同绑定，source-only16闭包已审。

有限Contacts producer v1原预算独立注册后因未审末capture过期stop；用户08:54删除永久errorstop，后v2→v3基线排除错误/ failedSID零work历史形状修复，新v3scope只当时明确新budget合法，不给当前额外名额。原v2exclude错误不是单加v1可修，必须全量baseline与nav历史域分开并sealedoldtables。17:52父错误问新决定经17:53纠正：only reserve前零input零账age-only拒绝可以append-only nonfatal，native/unknown/reserved仍停，180360不改。

v3rulefix exact21独审部署/完整真实history验证；第二SIDoverlap1成功、后旧图expire纯时效refusal零reservation，诚实close；第三前修Contacts embeddedprofile sameSIDrow causal，并append-only exactsourcepatch，原decision019f/77f3amend/patchd717保留。checkpoint reviewer曾错把EXACT5漏files，addendum独审纠正是prompt错误非源码bug，不改父/增字段。第三SID合法opens/admit/history+3captures/3reviews，7steps、没有row输入；两次remaining90.62/99.69低于110只是not-attempted，不能记done/failednative。多重source21build重复成本由只读静态定位，但20:25用户取消60s优先首人，性能planner取消，不能降低freshness或110。

20:37第三CPclose/unresolved空/sessionbudget0。20:54只读terminal再次核空lease/closed/exact21。父原request候选取真实environment_identity/sourcebody/原anchor，不拼host/account；尚无完整independent sendreview/productionlayoutmanifest批准。JSON parentattestation hash初误ensureascii默认True，21:15前按原c.dumps ensure_asciiFalse修正未审候选，file SHA5d8c60be6ccb92195dabde0c79e8be5ca9794487a3278df64759589e4f23eb8d；不是改旧批准。

### 4.7 暂停前最后局部成果与中断

**Viewport Task1 DONE_WITH_CONCERNS**：`snapshot/ocr_first_viewport_20261014/`实际5files，candidate f97b3e3a9e2881fc11f26f237f88a0d388ec3217c3b6ca288cd09b4cd89553e5；6tests44.965OK/117聚焦事件/228输入hash权限不变。七full54row/7nativeavatar22/28ring/5groupband/唯一green/fullpartition、历史chat/panel/selected/profile84surfaces88allocations559143px原像通过。H.Detector真实拒绝：top缺absent、tailunknown、反selectedlabel/marker未测、Contacts不接受embeddedprofile kind、首rowwhiteaccessorypalette、sameframe两scene区分、currentrow→profile因果及park。没伪造oppositestate/absent，profile像素相同不等于current关联。

**Tail Task2 DONE_WITH_CONCERNS**：`snapshot/ocr_first_tail_20261014/`候选A SHA `c3868654731d8a31184107ba89c0380a09a1dc2ebe5db1d2ed2fc63e28c56dfe`、test79dd8965…e6e51e、10聚焦tests68.101OK，仅6defs改。rows.tail unverified-tail acceptedfullcrop tol0/exactv3/historyonly/scrollbudget0/Sessionmax1入构造与run前检查；False=无正向尾证，不伪absent/覆盖complete。legacybinary/no sourcegrant/singleSend/_success unchanged，generatedloop completion是seam。independent reviewer6424在完成结论前被21:15暂停取消，**没有APPROVED或部署**。

**Launcher Task3部分落盘后killed**：`snapshot/ocr_first_launcher_20261014/`source/test/inherited_before/offline_tests4files。旧probe不returnregistry，新std­lib-first file-backed -I-S-B helper-pin/samePIDbootstrap→F.admit/open/runmax1/honestclose设计，没有使用registry export或fakeapproval。8离线seamtests0.749OK日志保留，但writer最后修open_session先persistSID再raise清理边界时被stop、无最终RESULT/独审，不能断言最终source与日志完全对应/缺陷闭合。未运行nativeOCR/DB/SSH。

**Planner Task4与tail独审被取消**：agent4685无最终PLAN_PATH，agent6424无审结论。三个active孩子21:16:59–21:17:01stoprequested，21:17:47Output全killedexit1；既有completed孩子903d/92fc/2270结果保留，未复活。所有已落盘候选连依赖完整归档，不继续实施以凑完成。

## 5. 精确源码闭包与批准层次（非自动准入）

已有history-only私有三source：
- H Automation `89edcaca66c788efd0326565066e5ecf41f9bf351498436ab72b0114b586c6a4`。
- H RoundUI `ac364a1239dc9a29c949732c5d9fb75b63e47d60636f59118fdd3c136def4535`。
- H RoundForward `6538906c913b1ed6922e6a56d082d21cce7eeec4666290571f165f1def09e894`。
- V其他13，包括publicUI必须 `245d856488dd78d686bd5248aafd11f900be99cee46d710825c732eb31f87238`，不取R旧publicUI8e469。

全16精确map见 `snapshot/history_entry_scene_profile_20261014/task2_evidence/composition_pins.json`；privateclosure独审报告 `snapshot/v3_single_accepted_control_20261014/verification_composition/db14_history_entry_profile_review_20261014.md` SHA93f561e48b77aba6daa9e8863ec13e304d6fb7f232ce36b533450000aeaff7c5。tail只新Ac386待审，launcher新helper待审，非替代既有map“全部已批准”。所有源码实际归档hash见manifest，对未变source byteidentity核验，不重复运行旧长suite。

生产CP P=`adb854a6911540fd0a3a4825c61a6d400a9b08bd034913df094444ebafebe6d3`、recovery=`f7fb788105c59022fb97088857dc8ad1da8a68dd76fff2fa7b4bceb8803a8ea1`，budget=`fcf1f91f334bdf2865956ffb22b4fdba0d840658a252f58b2a808c09c4dab760`，thirdparent3c10a5…。原decision019f/amend77f3/patchd717及exact21maps/receipt保留。源批准、父代码批准、现场checkpoint批准、SID批准、layout/runtime批准、发送批准各独立；不得用一类替代另一类。

Runtime库存/ABI先前3653files/116native metadata/9packages14trees3models、旧blankREAL_BLANK_BOOTSTRAP_OK成功证据可复用兼容结论，不复用registry。builder148864d614ec5e446d931412fd24c6ed06d76df484b0b51fde80c9bef39312b5位于原R，site生产ocr_site_20261013T1355，旧manifest root=ocr_probe_source不是生产root。新rootmanifest/exact16＋helper/sourcewrapper＋layout/canonicaldigest/dependencyidentity/同进程registry仍缺最终生产准入；不得把modelbootstrap或已审profile fragment叫真全链。

## 6. Git与归档检查

原repo `main` **No commits yet**，`.gitignore/AGENTS/README/controller/controller_sender_v2` AM，原两个tests A，多untracked，作者/继承staged归属未解决。保留原staged7版本与status，不stage、不commit/push、不改config、不建立嵌套仓库、不假称干净。源码sourcehash与归档hash逐项验证，原文件只读；完整排除/脱敏表、每文件sizehash及最终权限敏感信息扫描另存records。

目录0700/文件0600，私有图片/联系资料仅本地私有保存、不外披。真实secret、lease-token文件完全不读取不复制；JSON/log的非空privateauthority值脱敏，路径reference可保留。source中的明确fake/mock短token与launcher长syntheticfixture不作真实secret（已人工查其MOCK注释/fixture，原source完整保存）。保留匿名检查依据但不打印凭据值。

## 7. 下一接手者最小步骤——仅未来用户安排接手后

1. 先确认最新暂停决定仍有效；阅读本入口/README/原AGENTS的最新优先条款和各request区别，不能沿早期只截图/未联网阶段/旧回查count/旧确认门槛执行。
2. 用户在其他session安排接手后重新确认权限与唯一控制器、原环境/source/DB/锁/lease/allclosed/no_unresolved；20:54历史证据不能当当前。禁止访问范围外244/Q3/8127/旧22。
3. 对归档候选仅核本次未完delta：tail独审未结、launcherfinallyclose新credentialpersistedge未最终核；planner未完成。复用已有效旧tests/reviews，不先重长套，不先做性能framework。
4. 优先修具体Detector/config真实缺口：positive top/unknowntail/反selected态/Contacts嵌入profile完整验证/samecapture expected-scene因果/小accessory独立nativepartition，不能合成RGB、忽略可见行/泛mask/降低OCR置信或让unknownordinary。
5. source/layout/runtime/rootmanifest/helper＋真正Sendrequest准入分别独立必要审查后，只有合法普通flow事务可真实OCRrunmax1；CPsessions0不是第四次观测入口。保留原request/计时anchor/账/unknown不重放。先取得真实durableclicked再报告OCR/steps/耗时，后续整轮覆盖仍单独目标。
6. 此session只归档交接，**不执行以上恢复步骤、不向别的session自动派发**。

---

## 8. 下文的完整历史正文与详细索引

下文纳入已有早期真实交付和全部累计开发日志；各阶段旧授权限制、完成断言、正在审查措辞按历史时间阅读。所有引用路径可按README映射在snapshot寻找；丢失/远端-only文件见路径/排除索引，不伪造成功。后文还列出全部Markdown正文与精确复制回执索引，供逐次实现/测试/独审/部署/失败闭环核查。
