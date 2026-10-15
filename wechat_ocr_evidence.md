# 微信 OCR 方案：附件核查与原文证据

本文件区分“本次直接核查”“历史记录所述”和“方案建议”。历史日志中的测试通过、现场时间和批准状态未在本次复测。路径均相对于解压后的 `wechat-sim/`。

## A0. 本次直接核查：附件并非完整 snapshot

```json
{
  "archive": "wx.tar.gz",
  "sha256": "32964991355a0292a1bdfcf22075508a1b1ca5042ed89fa53c19c7de65f83584",
  "compressed_bytes": 1831632,
  "tar_members": 33,
  "regular_files": 28,
  "uncompressed_file_bytes": 9421000,
  "snapshot_members": 0,
  "manifest_entries": 13073,
  "missing_manifest_files": 13047,
  "missing_snapshot_files": 13047,
  "scope": "Local archive inspection only. No target desktop, network connection to target, OCR inference, deployment, or sending."
}
```

压缩包包含 28 个普通文件，`snapshot/` 为零。历史清单中的 13047 个 snapshot 文件均不在本附件。`records/final-verification.json` 所述 13075 个文件是当时原始归档的记录，不能作为当前 tar 内容完整的证据。当前可见业务源码是 `records/git-staged/` 的早期版本，不是最新部署源码。

## A1. 当前轮与历史轮的不同状态

来源：`records/agent-introduction.md:13–20`。文件 SHA-256：`daecc3435e3bb034bfa3fd453384b9a8ce0cf290b856bad258b3f143f92d71bf`。

```text
0013 | ## 2. 当前真实状态：必须分请求/分环境
0014 | 
0015 | - **当前请求 `msg_mv6nn1hjqjrlfm6nuy9`（8027新一轮）：0发送，0真实 `send_clicked`；全自动发送未开始。** 用户20:25优先要求先一个普通好友OCR全链，但在本session得到首个clicked前，21:15暂停指令已取代继续推进。不能沿用上轮10人complete、旧11待办或到列表尾作为这轮完成。
0016 | - 最后现场证据是暂停前20:54合法锁内只读 `snapshot/ocr_first_terminal_readonly_1791982429309891739.jsonl`，epoch `1791982433.8309324`；remote_exit0/stderr空。唯一生产DB inode `[2050,5791809]`；third已closed、all_closed、lease_empty、full_no_unresolved=true；原exact21源码核对成功。
0017 | - CP v3已消费20operations/8captures/3notches/0rows/0Contacts-entry/3sessions；剩140/72/45/24/1/**0sessions**。历史stop保留，effectivehealthy。第三SID `2f86a0deb1b54318b1aee3f492b3f10e` 已20:37诚实close；closed不可复活、不能开第四CP或退款。两次row只有parent裕量不足not-attempted，**没有cp-row输入/消费/资料关联**。
0018 | - 暂停后父没有SSH/UI/OCR/Send/install或现场刷新。20:54不是21:15后再核验，也不保证未来现场。没有已知活跃owned lease需额外收尾；全部子任务已停止，见records/pause-and-children.md。
0019 | - 历史旧请求：2026-10-13 14:03上轮 `msg_mv61novv99ftwes71kb` 有10普通好友attempted/10原生卡片confirmed、3排除、13ordered/top+tail完整，0uncertain/remaining。那是上轮独立结论，非当前0发送的矛盾。完整周期均值717.646s/n10，含修复的总through-close13921.248s；未实现<60s。见归档NEW_ROUND_DELIVERY和final report。
0020 | - 更早2026-10-11：Citrus原生卡片发送及随后reconcile；另四位URL文字是真实交付，用户接受不补发例外，不能追认卡片。后续历史总10不重发与旧round/source/account/provenance保留。此记录不把此前总发送说成0。
```

## A2. 真实 OCR 的 ROI 拒绝原因

来源：`agent.md:1124–1130`。文件 SHA-256：`86e388c80c581e69d082e6f62104a8a26b0d17d7f8b915cf7e5f1aacd6b168f7`。

```text
1124 | ## 2026-10-14 00:08+08 — 真OCR根因收敛，最小非Send校准进入实施
1125 | 
1126 | agent_a0d966dc8f12诊断B/db13_real_text_roi_failure_diagnosis_20261013.md完成：40ROI13接受/17unexplained/9overlap/1confidence；40crop哈希匹配、0edgeink、0出ROI框，9皆真实框重叠非裁切；不存在已证单一floorceil/padding修复。全incidental/history强制OCR框完整像素分区与真实RapidOCR能力不匹配，不盲重跑、不扩大框/降critical置信度。结论不是生产准入。
1127 | 
1128 | agent6c0规划docs/plans/2026-10-13-finite-calibration-navigation.md交付，现agent_6debe16eb7de按完整内联bounded规范实施两个新文件controller_db_calibration_navigation_20261013.py及tests：全新独立审批checkpoint/session的one-shot导航，captures≤16、scroll总≤6，Contacts/row/Messages/cube/select/Cancel各1，选择需额外独立exactq批准，无Send/旧coverage变更/旧recovery重开。待精确审查后才parent部署现场；这不是已部署或成功导航。源文件旧pins不动。
1129 | 
1130 | agent_aab9d41acd48并行最小PAGE兼容plan：以真实OCR失败证据区分非交互boundedtext像素证明和criticalcontrol/recipient正证；考虑positivefinitefull-label roster而非虚构ordinaryRGB，旧语义不静默放宽。尚无实现/批准。私有layoutpack仅片段批准；caret有后续真实测量但未纳入candidate，旧报告special/header说法已撤回，top40px绿色是可能clippedHu行不能当special或完整54行。
```

## A3. 时效不足和重复审查成本

来源：`agent.md:497–503`。文件 SHA-256：`86e388c80c581e69d082e6f62104a8a26b0d17d7f8b915cf7e5f1aacd6b168f7`。

```text
0497 | ## 2026-10-14 20:23+08 — 局部性能根因已定位；不继续无效capture/不猜降低110裕量
0498 | 
0499 | research3630只读结论：patched V嵌套validation让每owned同boundary重建21闭包10次(hash/AST)，review4owned合44build/capture5owned56/row+park8owned86；闭包826955B/167560AST节点。本机单buildparse0.366-.416s不能当现场，但actualreview三次39.7/40.4/40.0s、postcapture尾19.1/20.5s解释余90.619/99.692低于110。非native慢；没有PIL重复解码（旧PIL故障只是immutable历史认证）。parentbatch已消除操作间等待(8ms)，继续recapture在条件未变仍无效，暂停所有UI输入。
0500 | 
0501 | plannerde36仅离线有限owned内部重复计算最小修+sameSID合法appendonly exactcostdelta规划，distinctcandidate B/cp14_v3_owned_cost_20261014，不覆盖现已审源码。每boundary仍全hash/parse21一次、origins/exacttype/历史/current/account/owner/pending检查必须原样，无跨boundarycache/历史memo/改180360/110；同boundary已核map传递私有helper而非任意map绕过。原一次patchd717/77f3/019f/原review与账/消耗/名额都不改；最后已admitSID不得close再open绕sessions0。下一appendonly修复只能独审/locked freshsameSID完整before checkpoint/前像合法部署，不直接swap旧map或自动grant。当前third已持ownedlease、最后latest已review、无park/未知，实际consume20/8/3/0/0/3/row0/0send，覆盖未闭，原anchor累计85604.098s at20:14检查点(非自动性能)。
0502 | 
0503 | 更正覆盖口径：历史13只是上轮实际order，不是当前数量认证；当前画面计数字样不能代替逐行全量，旧“13非33”不可作本scope全量结论；本次只正向认证已真实看见7full rows/top，tailunknown，新增完整inventory仍未完成。历史昵称/class事实与新pixels关联分开。
```

## A4. 已有 max_contacts=1，仍被布局/未知尾部阻挡

来源：`agent.md:463–489`。文件 SHA-256：`86e388c80c581e69d082e6f62104a8a26b0d17d7f8b915cf7e5f1aacd6b168f7`。

```text
0463 | ## 2026-10-14 21:13+08 — 首viewport私有真实拒绝收敛；tail本地完成独审中
0464 | 
0465 | writer903d完成B/ocr_first_viewport_20261014 blockedcandidate f97b3e3a/evidencef4921e31/6tests44.965OK/117事件228输入不变：七full54 rows/7唯一avatar22/28ring/5完整groupbands/green/全partition、原chat/panel/selected/profile片段复用通过。不是Detector准入；具体缺口positive-onlyTOP缺absent、tailunknown、相反selectedlabel/marker无原生采样、Contacts嵌入profilekind、同帧scene和currentrow因果、首行whiteaccessorylabelpalette。无伪造态、无native/OCR。profileequal不能证明新rowassociation。
0466 | 
0467 | writer92fc完成B/ocr_first_tail_20261014 Ac3868654731d8a31184107ba89c0380a09a1dc2ebe5db1d2ed2fc63e28c56dfe/test79dd8965/10focusedtests68.101OK；仅rows.tail unverified-nativecrop exact0，historyonly/zero-scroll/Sessionmax1constructor+run约束，false=无正向尾证非认证absent，覆盖门不变。reviewer642423独立exactdelta审中，不能称APPROVED/部署。旧H89ed保持。planner468518仅有限<=2boundedtasks处理上列实际剩余constructor/config缺口，不重复tail/launcher/全量inventory，不扩性能。launcher4458仍NEW候选/离线测尚在进行，无现场权限。待结果不足时可结束本轮但不结束总任务，收结果后继续实施审查部署/真实首Send。实际最新只读terminal20:54仍空lease/全closed/无未决，CPsessions0不续。原request候选已按真实c.dumps ensure_asciiFalse修正未批fileSHA5d8c60be6ccb92195dabde0c79e8be5ca9794487a3278df64759589e4f23eb8d。0send/自动未开始/整体未完成/anchor不变。
0468 | 
0469 | ## 2026-10-14 20:54+08 — 首流程最小实施并行；生产terminal只读真实通过
0470 | 
0471 | 父实际锁内只读 B/ocr_first_terminal_readonly_1791982429309891739.jsonl exit0/stderr空：zcx-la/8027/唯一inode[2050,5791809]、third closed/all_closed/lease_empty/full_no_unresolved=true、原exact21及CP消费20/8/3/0/0/3保持，无UI/输入/新会话/账修改。环境取真实environment_identity而非拼造；原request候选 B/ocr_first_original_request_20261014.json 保留msg_mv6nn1hjqjrlfm6nuy9原文/来源/起点/all-ordinary-nonself，待与layout/runtime数据级独审，不把20:25通知做新发送request。
0472 | 
0473 | writer903d仅NEW首viewport四场景layout候选；writer92fc仅NEW honest unverified-tail局部约束候选；writer4458仅NEW same-process stdlib-first launcher和focused离线负测。research2270完成：旧probe不返回registry、旧blank及旧root manifest不能生产复用；新launcher须helper-pin/精确新identity、同进程bootstrap→F.run_automatic(max_contacts=1)→honestclose，仍无CopyURL/发后核验。未变16闭包复用已审结论，只新增或真正受影响delta独审。无第四CP、无性能方案扩展、Git继承AM/A保留未commit。本轮send_clicked=0，automatic未开始，整体未完成；原anchor不重置。244Q3不触。
0474 | 
0475 | ## 2026-10-14 20:40+08 — CP真实诚实关闭；直接复用单人入口，最小layout任务与runtime准备并行推进
0476 | 
0477 | 父actual cp14_v3_embedded_close-noinput_1791981463823986058.jsonl exit0/stderr空：third2f86a closedtrue/unresolvedops[]/intents[]，原consume20/8/3/0/0/3、sessions0/effectivehealthy/historicalstoptrue保留，最后图已review允许不fresh关闭，无recapture/UI/Send。不能重开closed或第四CP。后续是独立已授权原request普通发送flowSID，不算续CP观测/增预算，freshstart另准入，不混scope。
0478 | 
0479 | researchdff8源码实证Hautomation1048 fourmode仍all-ordinary-nonself(更正20:37 explicit-visible建议：不能用于此v3)，真实top建立首order即可先处理remaining，tail只整轮completion；max_contacts1首clicked后contact-limit是首人成功非整体complete，无发后图。可见layout内所有7头像须正向roster，但不需整个联系人后端库存先认证。双态boundarytail目前不能unknown，不能伪absent模板；source若真阻断只加必要honeststate局部修，非全套。
0480 | 
0481 | writer903d已派self-contained一boundedNEW B/ocr_first_viewport_20261014 privateartifact组装(源H三已审+V13不改)：复用chat/panel/selected/profilefragment、actualtop1bb648及durablef83freview；完整visible7row/static/group/avatars/provenancepartition，诚实记录tailunknown/selected-state/geometry拒绝，不OCR/live/Send。research2270只read-only最小生产rootmanifest/modelinventory/opaquebootstrapsameprocess/originalrequest调用recipe准备，并行与layout互不修改。父不再宽泛planner/复审未变16，不扩性能，首clicked仍0未完成，累计anchor不重置。范围244Q3未触。
0482 | 
0483 | ## 2026-10-14 20:37+08 — 性能planner已确认killed；单人自动入口原有max_contacts=1，不假设必须全量先完成
0484 | 
0485 | performance plannerde36 Output真实statuskilled/exit1，只有只读接口结论，无PLAN_PATH/候选/部署；不等待其交付，不称性能修复完成。父已核four-scene PRIVATE source：automation.run1438..1565本就max_contacts1在首成功_success后break(1554)且不发后核验；explicit-visible可选择可见目标，不要求程序先等coverage_complete。真正剩余是本次可见ordinary-rows/embeddedprofilelayout和four-scene原生runtime/dependency/exactsource/session准入，不能把原review中全量roster/top/tail覆盖外部前置继续强压单人。研究dff8精确分离这些要求中，父无UI追加/不降deadline或扩性能计划。
0486 | 
0487 | ## 2026-10-14 20:28+08 — 最新user优先单个真实OCR完整流程；暂停扩展性能修复
0488 | 
0489 | manager转user20:25 msg_mv832cxswsb1u3vtomf『第一步先用OCR把流程跑通，不用在意是否在60秒之内完成』。权威OCR_FIRST_FLOW_PRIORITY_20261014.md与AGENTS/README顶部同步：先普通好友row/profile→Messages→nativefirstFavorite→oneSend/durableclicked，nofollowupdelivery，不等全部top/tail/profilecoverage；整轮后续，不把取消60s误为取消180360。gaozhiordinary/selfgaozhi-xinshu/sys排除、OCRsingleadvisory允许错/empty都不变。
```

## A5. 最新版业务语义：send_clicked、连续 OCR、当前第一收藏

来源：`agent.md:1274–1284`。文件 SHA-256：`86e388c80c581e69d082e6f62104a8a26b0d17d7f8b915cf7e5f1aacd6b168f7`。

```text
1274 | ## 最新成功标准 msg_mv6efvp5mkzqt63y89s（覆盖冲突正文）
1275 | 
1276 | 见 `SEND_CLICKED_AUTHORITY_20261013.md`：当前第一收藏选中且Send输入调用明确成功返回即记 `send_clicked`（已点击发送，未核验送达/卡片）。正常路径不再发后open-info/profile/peer、卡片增量或时间核验，不冒用历史confirmed。输入失败/不明仍failed/unknown，账号/收件人/锁/记账/单次输入不变。仍仅本地实现与隔离验证，不现场、不部署。历史内容保留，但不得将被替代的发后核验门槛带入新模式。
1277 | 
1278 | ## 同次追加 msg_mv6bzyano3ttnkkobgo — 程序内OCR连续流程
1279 | 
1280 | 参见 `OCR_AUTOMATION_ADDENDUM_20261013.md`：正常路径用局部页面OCR/布局锚点/状态机连续驱动，LLM调用结构目标0，异常停止；不把页面OCR当精确身份、不重复联系人辅助OCR，不恢复旧完美ID门槛。与聊天内第一收藏无CopyURL路径一并实施。此次仅本地合成/mock测试及精确独审，不现场、不部署、不声称实机<60秒；旧执行链的操作间隔不能全部归因LLM。
1281 | 
1282 | ## 最新流程变更 msg_mv6bprnf7befrjzqudk — 仅本地实施，未新增现场授权
1283 | 
1284 | 以 `DIRECT_FIRST_FAVORITE_AUTHORITY_20261013.md` 为最新冲突处理正文：目标聊天直接原生收藏面板→当前第一条→Send；新路径不再以Favorites页/menu/CopyURL/冻结URL相等作硬门槛。历史confirmed不绝对阻断未来明确目标请求，但同一次输入的幂等与unknown不盲重放不变，旧账/旧轮结果保留。此次只代码/规则更新、隔离测试和精确独审，不连接现场、不发消息、不重开已完成10人轮；未审不得部署。其他账号/收件人/时限/ownership/锁/凭据/记账/发后核验边界不变。旧文中的“永久不重发/逐人CopyURL”对于未来明确请求按此授权取代，不倒改历史。
```

## A6. 最后候选与同进程 launcher 的实际完成边界

来源：`records/agent-introduction.md:74–80`。文件 SHA-256：`daecc3435e3bb034bfa3fd453384b9a8ce0cf290b856bad258b3f143f92d71bf`。

```text
0074 | ### 4.7 暂停前最后局部成果与中断
0075 | 
0076 | **Viewport Task1 DONE_WITH_CONCERNS**：`snapshot/ocr_first_viewport_20261014/`实际5files，candidate f97b3e3a9e2881fc11f26f237f88a0d388ec3217c3b6ca288cd09b4cd89553e5；6tests44.965OK/117聚焦事件/228输入hash权限不变。七full54row/7nativeavatar22/28ring/5groupband/唯一green/fullpartition、历史chat/panel/selected/profile84surfaces88allocations559143px原像通过。H.Detector真实拒绝：top缺absent、tailunknown、反selectedlabel/marker未测、Contacts不接受embeddedprofile kind、首rowwhiteaccessorypalette、sameframe两scene区分、currentrow→profile因果及park。没伪造oppositestate/absent，profile像素相同不等于current关联。
0077 | 
0078 | **Tail Task2 DONE_WITH_CONCERNS**：`snapshot/ocr_first_tail_20261014/`候选A SHA `c3868654731d8a31184107ba89c0380a09a1dc2ebe5db1d2ed2fc63e28c56dfe`、test79dd8965…e6e51e、10聚焦tests68.101OK，仅6defs改。rows.tail unverified-tail acceptedfullcrop tol0/exactv3/historyonly/scrollbudget0/Sessionmax1入构造与run前检查；False=无正向尾证，不伪absent/覆盖complete。legacybinary/no sourcegrant/singleSend/_success unchanged，generatedloop completion是seam。independent reviewer6424在完成结论前被21:15暂停取消，**没有APPROVED或部署**。
0079 | 
0080 | **Launcher Task3部分落盘后killed**：`snapshot/ocr_first_launcher_20261014/`source/test/inherited_before/offline_tests4files。旧probe不returnregistry，新std­lib-first file-backed -I-S-B helper-pin/samePIDbootstrap→F.admit/open/runmax1/honestclose设计，没有使用registry export或fakeapproval。8离线seamtests0.749OK日志保留，但writer最后修open_session先persistSID再raise清理边界时被stop、无最终RESULT/独审，不能断言最终source与日志完全对应/缺陷闭合。未运行nativeOCR/DB/SSH。
```

## A7. 运行时依赖成功不等于生产准入

来源：`records/agent-introduction.md:84–96`。文件 SHA-256：`daecc3435e3bb034bfa3fd453384b9a8ce0cf290b856bad258b3f143f92d71bf`。

```text
0084 | ## 5. 精确源码闭包与批准层次（非自动准入）
0085 | 
0086 | 已有history-only私有三source：
0087 | - H Automation `89edcaca66c788efd0326565066e5ecf41f9bf351498436ab72b0114b586c6a4`。
0088 | - H RoundUI `ac364a1239dc9a29c949732c5d9fb75b63e47d60636f59118fdd3c136def4535`。
0089 | - H RoundForward `6538906c913b1ed6922e6a56d082d21cce7eeec4666290571f165f1def09e894`。
0090 | - V其他13，包括publicUI必须 `245d856488dd78d686bd5248aafd11f900be99cee46d710825c732eb31f87238`，不取R旧publicUI8e469。
0091 | 
0092 | 全16精确map见 `snapshot/history_entry_scene_profile_20261014/task2_evidence/composition_pins.json`；privateclosure独审报告 `snapshot/v3_single_accepted_control_20261014/verification_composition/db14_history_entry_profile_review_20261014.md` SHA93f561e48b77aba6daa9e8863ec13e304d6fb7f232ce36b533450000aeaff7c5。tail只新Ac386待审，launcher新helper待审，非替代既有map“全部已批准”。所有源码实际归档hash见manifest，对未变source byteidentity核验，不重复运行旧长suite。
0093 | 
0094 | 生产CP P=`adb854a6911540fd0a3a4825c61a6d400a9b08bd034913df094444ebafebe6d3`、recovery=`f7fb788105c59022fb97088857dc8ad1da8a68dd76fff2fa7b4bceb8803a8ea1`，budget=`fcf1f91f334bdf2865956ffb22b4fdba0d840658a252f58b2a808c09c4dab760`，thirdparent3c10a5…。原decision019f/amend77f3/patchd717及exact21maps/receipt保留。源批准、父代码批准、现场checkpoint批准、SID批准、layout/runtime批准、发送批准各独立；不得用一类替代另一类。
0095 | 
0096 | Runtime库存/ABI先前3653files/116native metadata/9packages14trees3models、旧blankREAL_BLANK_BOOTSTRAP_OK成功证据可复用兼容结论，不复用registry。builder148864d614ec5e446d931412fd24c6ed06d76df484b0b51fde80c9bef39312b5位于原R，site生产ocr_site_20261013T1355，旧manifest root=ocr_probe_source不是生产root。新rootmanifest/exact16＋helper/sourcewrapper＋layout/canonicaldigest/dependencyidentity/同进程registry仍缺最终生产准入；不得把modelbootstrap或已审profile fragment叫真全链。
```

## A8. 早期源码：完整覆盖在 dry_run 中产生阻断原因

来源：`records/git-staged/controller.py:393–425`。文件 SHA-256：`18ec3ce9cdf64916733c85c1c42a0fc6c6ec902144557c7941483d6284c14639`。

```text
0393 |         complete = bool(pages and self.get('end_proof'))
0394 |         with self.db:
0395 |             for oid, occurrence in manifest.items():
0396 |                 row = contacts.get(oid)
0397 |                 if not row or row['status'] != 'identified':
0398 |                     excluded.append(dict(occurrence, reason='special_skipped' if row and row['kind'] == 'special' else 'identity_pending',
0399 |                                          details=row.get('reason') if row else 'profile WeChat ID not reviewed'))
0400 |                     continue
0401 |                 self.evidence(row['evidence'])
0402 |                 fid = row['friend_id']
0403 |                 if fid in seen:
0404 |                     excluded.append(dict(occurrence, reason='duplicate_stable_id', friend_id=fid))
0405 |                     continue
0406 |                 seen.add(fid)
0407 |                 reasons = ['send_disabled']
0408 |                 if not complete:
0409 |                     reasons.append('coverage_incomplete')
0410 |                 if not key:
0411 |                     reasons.append('article_pending')
0412 |                 if fid in unmapped:
0413 |                     reasons.append('legacy_unmapped')
0414 |                 if key and fid not in unmapped:
0415 |                     self.db.execute('INSERT OR IGNORE INTO ledger VALUES(?,?,?,?)',
0416 |                                     (fid, key, 'pending', dumps({'origin': 'dry-run'})))
0417 |                 pair = self.db.execute('SELECT status FROM ledger WHERE friend_id=? AND article_key=?', (fid, key)).fetchone()
0418 |                 status = pair[0] if pair else None
0419 |                 if status in ('confirmed', 'submitting', 'uncertain'):
0420 |                     reasons.append(status)
0421 |                 queue.append(dict(occurrence, friend_id=fid, article_key=key, status=status, reasons=reasons))
0422 |         return {'send_enabled': False, 'automatic_vision': False, 'article': article,
0423 |                 'coverage': {'enumeration_complete': complete, 'pages': len(pages),
0424 |                              'observations': len(manifest), 'distinct_identified_friends': len(seen),
0425 |                              'end_proof': self.get('end_proof'), 'manifest': list(manifest.values())},
```

## A9. 早期源码：队列只接受没有其他阻断原因的条目

来源：`records/git-staged/controller_sender_v2.py:19–28`。文件 SHA-256：`d0100bac2fb4d0d3985f279513fb766953665df547392dd1384f7a55bd7cbec6`。

```text
0019 | def current_queue(store):
0020 |     report = store.dry_run()
0021 |     key = report['article'].get('article_key')
0022 |     blocked = [r['friend_id'] for r in store.list('ledger')
0023 |                if r['article_key'] == key and r['status'] in ('submitting', 'uncertain')]
0024 |     eligible = [r for r in report['queue']
0025 |                 if r['status'] == 'pending' and set(r['reasons']) == {'send_disabled'}]
0026 |     report['reconciliation_required'] = blocked
0027 |     report['next'] = eligible[0] if eligible and not blocked else None
0028 |     return report
```

## A10. 早期源码：精确身份、固定收藏与 URL 门槛

来源：`records/git-staged/controller_sender_v2.py:48–84`。文件 SHA-256：`d0100bac2fb4d0d3985f279513fb766953665df547392dd1384f7a55bd7cbec6`。

```text
0048 | def validate_request(store, d):
0049 |     c.reviewed(d)
0050 |     report = current_queue(store)
0051 |     item = report['next']
0052 |     c.need(item is not None, 'no eligible next recipient; reconcile blocked intents first')
0053 |     c.need(all(d.get(k) == item[k] for k in ('oid', 'friend_id', 'article_key')),
0054 |            'next recipient/order/article mismatch')
0055 |     profile, favorite = d['profile'], d['favorite']
0056 |     c.reviewed(profile)
0057 |     c.reviewed(favorite)
0058 |     p = recent(store, profile['evidence'])
0059 |     a = recent(store, favorite['evidence'])
0060 |     final = store.evidence(d['evidence'], fresh=True)
0061 |     c.need(len({p['id'], a['id'], final['id']}) == 3,
0062 |            'separate profile, favorite and final captures required')
0063 |     c.need(max(p['captured_at'], a['captured_at']) <= final['captured_at'], 'review chronology mismatch')
0064 |     contact = store.item('contacts', item['oid'])
0065 |     c.need(contact['kind'] == 'friend' and contact['status'] == 'identified'
0066 |            and contact['friend_id'] == d['friend_id'], 'stored identity mismatch')
0067 |     c.need(profile.get('oid') == d['oid'] and profile.get('friend_id') == d['friend_id']
0068 |            and profile.get('field') == 'WeChat ID' and profile.get('same_row') is True,
0069 |            'profile identity mismatch')
0070 |     c.need(favorite.get('title') == c.TITLE and favorite.get('source') == c.SOURCE
0071 |            and favorite.get('first_favorite') is True and favorite.get('exactly_one') is True
0072 |            and favorite.get('url_observed') is True and favorite.get('association_note')
0073 |            and c.article_key(favorite.get('url')) == d['article_key'], 'first favorite URL mismatch')
0074 |     c.need(d.get('screen') == 'send-confirmation' and d.get('send_control') is True
0075 |            and d.get('recipient_id') == d['friend_id']
0076 |            and d.get('recipient_matches_profile') is True
0077 |            and d.get('article_matches_favorite') is True
0078 |            and c.article_key(d.get('url')) == d['article_key'], 'final recipient/article mismatch')
0079 |     c.need(type(d.get('recipient_count')) is int and d['recipient_count'] == 1
0080 |            and type(d.get('article_count')) is int and d['article_count'] == 1,
0081 |            'exactly one recipient and article required')
0082 |     c.need(c.inside(d['target'], c.rect(final['geometry'])), 'target outside reviewed window')
0083 |     c.need(type(d.get('x')) is int and type(d.get('y')) is int
0084 |            and c.inside([d['x'], d['y'], 1, 1], d['target']), 'click outside reviewed target')
```

## A11. 早期源码：durable intent、单次点击与失败状态

来源：`records/git-staged/controller_sender_v2.py:149–174`。文件 SHA-256：`d0100bac2fb4d0d3985f279513fb766953665df547392dd1384f7a55bd7cbec6`。

```text
0149 | def submit(store, request, token, desktop=None, *, approval=deny_approval):
0150 |     # Copy input so an injected policy cannot alter the validated request in place.
0151 |     d = json.loads(c.dumps(request))
0152 |     c.need(approval(json.loads(c.dumps(d))) is True, 'APPROVAL_REQUIRED')
0153 |     desktop = desktop if desktop is not None else Desktop()
0154 |     with locked(store, token):
0155 |         final = validate_request(store, d)
0156 |         desktop.guard(store, d)
0157 |         fid, key = d['friend_id'], d['article_key']
0158 |         store.intent(fid, key, d)  # FULL-synchronous commit before any possible click.
0159 |         try:
0160 |             desktop.guard(store, d)  # Recheck latest/hash/age/geometry/active after commit.
0161 |             desktop.click(d)
0162 |             after = desktop.capture(store, final['geometry']['id'], d['reviewer'])
0163 |             store.event({'kind': 'sender-result', 'friend_id': fid, 'article_key': key,
0164 |                          'status': 'submitting', 'before': final['id'], 'after': after['id']})
0165 |             return {'friend_id': fid, 'article_key': key, 'status': 'submitting', 'after': after['id']}
0166 |         except BaseException as exc:
0167 |             # Failure of this recovery write still leaves the already durable submitting intent.
0168 |             try:
0169 |                 store.transition(fid, key, 'uncertain', {'kind': 'sender-failure',
0170 |                     'error': str(exc) or type(exc).__name__, 'before': final['id']})
0171 |             except BaseException:
0172 |                 pass
0173 |             raise
0174 | 
```

## A12. 最新接手说明指出的 Detector / layout 缺口

来源：`records/agent-introduction.md:104–110`。文件 SHA-256：`daecc3435e3bb034bfa3fd453384b9a8ce0cf290b856bad258b3f143f92d71bf`。

```text
0104 | ## 7. 下一接手者最小步骤——仅未来用户安排接手后
0105 | 
0106 | 1. 先确认最新暂停决定仍有效；阅读本入口/README/原AGENTS的最新优先条款和各request区别，不能沿早期只截图/未联网阶段/旧回查count/旧确认门槛执行。
0107 | 2. 用户在其他session安排接手后重新确认权限与唯一控制器、原环境/source/DB/锁/lease/allclosed/no_unresolved；20:54历史证据不能当当前。禁止访问范围外244/Q3/8127/旧22。
0108 | 3. 对归档候选仅核本次未完delta：tail独审未结、launcherfinallyclose新credentialpersistedge未最终核；planner未完成。复用已有效旧tests/reviews，不先重长套，不先做性能framework。
0109 | 4. 优先修具体Detector/config真实缺口：positive top/unknowntail/反selected态/Contacts嵌入profile完整验证/samecapture expected-scene因果/小accessory独立nativepartition，不能合成RGB、忽略可见行/泛mask/降低OCR置信或让unknownordinary。
0110 | 5. source/layout/runtime/rootmanifest/helper＋真正Sendrequest准入分别独立必要审查后，只有合法普通flow事务可真实OCRrunmax1；CPsessions0不是第四次观测入口。保留原request/计时anchor/账/unknown不重放。先取得真实durableclicked再报告OCR/steps/耗时，后续整轮覆盖仍单独目标。
```
