# wechat-sim — 微信项目暂停归档（2026-10-14）

**状态：PAUSED / HANDOFF ONLY。禁止自动执行、部署、恢复会话或发送。**

用户最新指令 `msg_mv84uv9r7cdtmlcumwi`：将微信项目文档和代码集中存入 `wechat-sim`，把从头开始的详细开发记录存入 `agent.md`，然后暂停并交接给其他 session。本目录不是已完成发送项目，也不是可直接启用的生产控制器。

## 实际位置与入口

- 开发环境主机：`X79`（本次本地 `hostname` 实测）。
- 规范绝对目录：`/tmp/wxview92/wechat-sim/`。
- 详细记录与交接入口：[agent.md](agent.md)。
- 项目源码/测试/规则入口：[snapshot/upgrade_20261010T1529/](snapshot/upgrade_20261010T1529/)。
- 全部私有候选、源码依赖、运行时 bundle、原图/布局 JSON、测试/独审/部署/故障回执，按原相对结构完整复制在 `snapshot/`，不是空链接。
- 文件清单、每文件 SHA-256/字节数：[records/copy-manifest.jsonl](records/copy-manifest.jsonl)；最终整个归档清单与核验见 `records/final-file-manifest.jsonl`、`records/final-verification.json`。
- 排除项：[records/excluded-files.json](records/excluded-files.json)；脱敏变更：[records/archive-copy-summary.json](records/archive-copy-summary.json)。
- Git 原工作树及继承暂存状态：`records/git-status.txt`、`records/git-index-files.txt`、`records/git-staged/`。未复制 `.git`，未提交、未伪造作者、未改原工作树/索引。

**未在远端 8027 存放此目录。** 本次归档未运行 SSH/UI/OCR/Send/install，没有获取生产 DB、远端凭据或额外现场状态。生产位置只作历史引用，不能据此误称已同步：`gaozhi@192.168.0.92:8027`，`/home/gaozhi/fav_forward_20261010/upgrade_20261010T1529/`。

## 旧绝对路径映射

| 原开发路径 | 本归档相对路径 |
|---|---|
| `/tmp/wxview92/upgrade_20261010T1529/...` | `snapshot/upgrade_20261010T1529/...` |
| `/tmp/wxview92/<候选或证据目录>/...` | `snapshot/<候选或证据目录>/...` |
| `/tmp/wxview92/<根脚本或回执>` | `snapshot/<根脚本或回执>` |
| 两个 `/tmp/*plan*.md` 外部微信计划 | `external-plans/`；逐项源路径/哈希见 `records/external-file-manifest.jsonl` |
| 远端生产绝对路径 | 不映射为本地生产；仅记录安全引用，未访问/复制生产 DB 或 secret |

原文件**未破坏性移动**、不改源码中的原路径。归档不是运行位置重定位：原 root/source-origin/manifest-helper/pin 约束仍有效，在归档目录直接运行可能拒绝，禁止通过改 pins 或伪造 origins 来规避。脱敏文件具有新的 archive SHA，原始 source SHA 同时保留；其内容不能当原始不可变证据或重新签发的批准。`agent.md` 中旧条目按原历史上下文解释，置顶暂停指令和后续明确纠偏优先。

## 私密与不包含范围

目录均0700，文件均0600。图片、联系资料、OCR原始返回等仅保存在此私有本地归档，不对外发布。排除原始 credential/secret/lease-token/私钥文件、全部 SQLite/DB备份、Python缓存及 Git元数据；不新建生产账、不清库、不修改旧账或远端状态。日志/JSON里非空私有授权值已脱敏，路径引用保留。测试中的明确虚构 token 不是真实凭据；见检查说明。244 GPU/D1/TQ、Q3 RPA、已完成 Bot安装不在本项目归档范围；历史文档中的排除说明保留，不表示恢复这些资产。

## 新 session 接续

1. 先读 `agent.md`、归档 `AGENTS.md` 和最新有效授权/停止记录，确认这是暂停交接，不是恢复发送授权。
2. 待用户在其他 session 明确接手安排后，重新确认权限、唯一现场控制器、现场状态/锁/租约/未决和精确源码基线；本次20:54最后只读回执不是未来现场保证。
3. 旧closed SID不可复活；CP观测sessions余0不可退款或开第四个；正常发送事务不得借CP批准。原账、原起点、旧confirmed/uncertain/源批准保留。
4. 首viewport候选仍被真实schema拒绝；tail源码完成但审查被用户暂停中断；launcher部分完成、没有最终独审/生产manifest/Layout准入。不得部署或称首个clicked完成。
5. 不以归档/交接成功替代微信业务目标完成，不向未知session私自委派。
