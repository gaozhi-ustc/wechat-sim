# WeChat externally reviewed inventory — SEND HARD DISABLED

This controller records externally reviewed visual evidence, contact-list coverage and exact profile IDs, and produces a persistent SQLite deduplicated **dry-run** manifest. It does not recognize images, enumerate contacts automatically, fetch articles, or send messages. `submit` always prints `ERROR: SEND_DISABLED` and exits 2 before opening a database, acquiring locks, or running a tool. There is no send-enable flag or environment switch.

Implementation tests do not establish real UI coverage, recipient identity or legacy article mappings. No production database was initialized during implementation.

## Invocation and runtime safety

```text
PYTHONDONTWRITEBYTECODE=1 python3 controller.py COMMAND --data JSON [--token TOKEN]
```

`--data` defaults to `{}` and must be a JSON object. Commands print JSON on success (exit 0); rejected commands print an error to stderr (exit 2). `--help` is side-effect free. `init`, `claim`, and disabled `submit` do not require a token; all other commands require the current token.

The database is always `ledger.sqlite3` beside the script. No `--db` or `--state` override exists. Runtime locations are restricted to:

* `/tmp/wxview92/upgrade_20261010T1529/` (development only)
* `/home/gaozhi/fav_forward_20261010/upgrade_20261010T1529/` (future single production ledger)

Do not alternate independent ledgers for production. Tests use cleaned temporary directories beneath the development directory.

Every runtime command except rejected `submit` holds a nonblocking `controller.lock` process flock and the existing `<legacy_state>.lock`, opened **O_RDONLY**, without creating/writing/deleting it. Missing, symlinked or busy old locks fail closed. The old JSON must initially match the complete v1 pilot history (assfox, File Transfer, cherry-pku, all confirmed, fixed title/source). Its path, snapshot and SHA-256 are bound on initialization; subsequent calls reject changed content. The old lock inode is checked against the opened descriptor during each acquisition, not persistently bound across commands. Operators must confirm the old controller is stopped and the correct lock inode/path is used before handoff.

`claim` creates a persistent random token lease stored as a token hash. There is no expiry, takeover, reset or recovery shortcut. Preserve the token privately; losing it requires operator reconciliation, not database deletion. The old lock is released between calls; this does not provide OS-level exclusive desktop ownership. Other actors can change UI without changing geometry. Exclusive desktop access and immediate external review remain mandatory.

## Supported commands and JSON fields

Each review requires a nonempty `reviewer`. Geometry is `{id,x,y,w,h,title,wm_class}` with decimal-string window ID and integer root coordinates/dimensions. Live `wm_class` is the second (class) string from read-only `xprop -id WINDOW WM_CLASS`, not the first instance string; unavailable xprop or missing/malformed WM_CLASS fails closed without installing anything. Rectangles are `[root_x,root_y,width,height]`.

| Command | Data / behavior |
|---|---|
| `init` | `legacy_state`: existing absolute complete old-state JSON path. Imports immutable history, idempotent only for the same path/hash. |
| `claim` | `owner`: nonempty attribution; returns token, no lease stealing. |
| `release` | `{}` plus token; clears only the current lease. |
| `status` | `{}`; returns meta/evidence/pages/contacts/events/ledger/legacy, omitting the lease token hash. Evidence is not revalidated by this audit-only command. |
| `windows` | `{}`; lists visible class-regex candidates using xdotool/xwininfo/xprop. No automatic resolution of ambiguous candidates. A zero-match xdotool search may return a tool error rather than an empty list. |
| `capture` | `reviewer`, `main_window:true`, optional `window_id` (required unless exactly one candidate). Dynamically crops the root window with ImageMagick `import`; before/after geometry must match. Returns PNG path/hash/evidence ID. Review the PNG before further action. |
| `record-evidence` | `path` inside the upgrade directory, `sha256`, `captured_at` epoch, `geometry`, `geometry_source:"xwininfo"`, `reviewer`, `main_window:true`. Records externally acquired PNG evidence after hash/signature/IHDR-dimension checks. Does not itself query geometry or decode the complete PNG. |
| `navigate` | `evidence`, `reviewer`, `safe_navigation:true`, `screen`, `action`, `target`, `x`, `y`; scrolling also `from_page`. Only contacts screen actions `contacts-tab`, `contact-row`, `scroll-down` and profile action `profile-close` are allowed. Latest evidence age must be less than 180 seconds, file hash intact, live geometry equal, window active. Commits navigation intent before one click or one wheel-down notch; captures afterward; failure records uncertain, no automatic retry. Scroll target must equal source page pane. |
| `record-scroll` | External input attestation: `before`, `after`, `from_page`, `pane`, `reviewer`, `direction:"down"`, `notches:1`, `actual_input:true`, `list_focused:true`. Requires source-page screenshot, different evidence IDs, strictly increasing capture times and equal geometry. Records explicit external-review origin by default. |
| `record-page` | `evidence`, `reviewer`, `pane`, `rows:[{oid,label,box}]`, `all_visible_rows:true`. First page requires `at_top:true`, `top_visible:true`; each later page requires `scroll` event ID linking previous page's evidence to new evidence. Rows must be ordered/nonoverlapping/inside pane; sufficient suffix-prefix occurrence overlap is required (2 if both pages have at least 3 rows, otherwise 1). After the maximum overlap, every appended oid must be globally new; earlier IDs outside the overlap are rejected. Identical full-page no-progress captures remain allowed. No pages after sealed end proof. |
| `record-contact` | Identified profile: `oid`, `evidence`, `reviewer`, `same_row:true`, `field:"WeChat ID"`, exact `friend_id`, `kind:"friend"`, `status:"identified"`. Without ID: `kind:"friend"`, `status:"pending"`, `reason`, no friend_id. Special row: `kind:"special"`, `status:"skipped"`, `reason`, no friend_id. Identified identity cannot change. Accepted ID syntax: letter followed by 2–63 letters/digits/underscore/hyphen. |
| `record-end` | `reviewer`, `bottom_visible:true`, `no_progress:true`. Requires last three pages with identical ordered occurrence IDs, three distinct evidence IDs/files and two actual down-scroll edges; checks evidence hashes. Equal pixel hashes are allowed because genuine bottom captures may be identical. |
| `record-article` | `evidence`, `reviewer`, `title`, `source`, `first_favorite:true`, `exactly_one:true`; verified URL additionally requires `url`, `url_observed:true`, `association_note` describing inspected URL/first-favorite relationship. Missing/invalid URL stays pending and creates no fake article key. A verified article cannot be changed or downgraded in this run. |
| `map-legacy` | `friend_id` assfox or cherry-pku, `evidence`, `reviewer`, `url`, `same_original_card:true`, `url_observed:true`, `association_note`, `legacy_confirmation_sha256` matching imported confirmation. Must attest the actual historically sent card URL, matching the current verified article key. Creates confirmed history; cannot overwrite nonconfirmed pairs. File Transfer never maps into friend ledger. |
| `dry-run` | `{}`; returns article, coverage/occurrence manifest, every identified unique friend queue entry, pending/special/duplicate exclusions and legacy records; always `send_enabled:false`, `automatic_vision:false`. Only identified, real-article-key, non-unmapped pairs are inserted as pending. Coverage-incomplete pairs may be stored pending but are explicitly blocked in queue reasons; pending is inventory, not send authorization. Mapped legacy evidence is revalidated before queue processing; missing/corrupt evidence fails closed without changing or downgrading confirmed history. Repeated calls preserve pair uniqueness and all existing statuses. |
| `submit` | Always `SEND_DISABLED`, including malformed data; no UI/DB/lock change. |

Title/source review conditions are exactly:

* `分治法 vs 端到端？ Attention is All You Need!`
* `高志创业笔记`

The article key accepts only standard `http[s]://mp.weixin.qq.com/s` URLs with one nonempty `__biz`, `mid`, `idx`, `sn` each (numeric mid/idx). It normalizes to HTTPS, preserving all four identity fields and removing tracking/fragment. Short links, titles, screenshots and hashes cannot be keys. The parent-reported favorite URL is:

```text
https://mp.weixin.qq.com/s?__biz=MzkzODYyNjkxNA==&mid=2247484469&idx=1&sn=2b0ab0628938686baef0f9c0dfbf40bc
```

This is contextual information only: it is not preloaded, not proof of first-favorite association, and never automatically maps old history. Runtime recording still requires reviewed evidence.

## Coverage and identity workflow

Externally review contacts at top, record every visible middle-list row including special entries, scroll one notch retaining overlap, and record continuous pages. At bottom perform two further actual down scrolls and record unchanged pages before `record-end`. Opaque `oid` values identify visually tracked **row occurrences**, never nickname-derived IDs. Reuse only for established overlap. Same-name rows can be different friends; multiple occurrences with the same exact profile ID deduplicate by that stable ID.

Prefer collecting the full page chain before opening profiles. Scroll source evidence must exactly match its page; profile visits/new captures do not silently reconnect an interrupted chain. Gaps or order changes fail closed; there is no reset command. Missing profile IDs remain explicit pending; special entries remain separate skipped exclusions. Unmapped assfox/cherry-pku history blocks those friends globally until actual historical-card URL proof. File Transfer remains separate legacy/special history.

Review fields are attribution/attestation, not authentication or machine vision. PNG hashes detect file changes, not semantic truth. Distinct tail files/time attestations do not prove real inputs by themselves; an external reviewer must honestly observe them. Arbitrary coordinates cannot be proved safe automatically; do not navigate unless the current target is visually reviewed as one of the permitted actions.

## Persistence-only future interface

SQLite enforces unique `(friend_id, article_key)` and statuses pending/submitting/confirmed/uncertain. `Store.intent()` commits pending → submitting before any hypothetical send; `Store.transition()` allows only submitting/uncertain → uncertain/confirmed. There is no backward transition or retry. These are internal persistence primitives tested with synthetic attestations, **not a semantic send authorization API**. No enabled CLI invokes them for sending. A future sender needs separate design review and explicit authorization.

## Isolated verification

```sh
cd /tmp/wxview92/upgrade_20261010T1529
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_controller
PYTHONDONTWRITEBYTECODE=1 python3 controller.py --help
PYTHONDONTWRITEBYTECODE=1 python3 controller.py submit
code=$?
test "$code" -eq 2
```

28 isolated tests include the supplied 17 plus article immutability, latest/active-window rejection, strictly chronological scrolls, re-registered-file tail rejection, committed navigation intent before synthetic input failure, exact xprop class parsing/fail-closed behavior, complete mocked capture success, rejection of row recurrence outside overlap, and missing/corrupt legacy mapping evidence without confirmed-state mutation. Test PNGs are synthetic headers; tests do not touch desktop, network or real legacy files. Do not run init/capture/navigate against live state during development verification. Parent must independently compare real old-file hashes and validate deployment handoff/full UI traversal; those checks are not claimed here.

## Sender v2 — adapter implemented, approval NOT opened

`controller_sender_v2.py` imports the original controller and uses the **same ledger.sqlite3** beside the scripts. Original `controller.py` remains unchanged, including its `SEND_DISABLED` response. V2 implements actual xdotool click and ImageMagick post-capture commands with an injectable bytes-returning executor, not a disabled sender stub. Nevertheless, **ZERO new real sends** are permitted in this continuation. The development and future production v2 CLI reject `submit` with `APPROVAL_REQUIRED` and exit 2 before parsing JSON, opening a DB, locking or invoking any tool. No CLI flag, JSON field or environment variable opens the approval gate.

`submit(store, request, token, desktop=None, *, approval=deny_approval)` is the one-shot library entry point. Its default policy always rejects. Tests alone inject a fake Desktop executor and a synthetic approving callback. The callback is a privileged integration seam, not a user approval token and not authorization to use real tools now. Do not call it with an approving callback and the real Desktop during this continuation. `Desktop(execute=None)` defaults to the existing bounded `controller.tool` executor; injected executors accept one argv list and return bytes, raising on errors. There are no retries.

Future opening requires a separate explicit manager decision specifying the authorized recipient/article scope and send limit, followed by a separately reviewed CLI approval-verification integration that binds that decision to the exact request and retains all lease/legacy/process locks and evidence checks. No such approval issuer/verifier is installed by v2. Changing a boolean, passing `approved:true`, or treating a reviewer name as authorization is not the future approval flow. Keep current CLI denial until that later review is complete.

### Sender request contract

Upstream external review must first prepare the final send-confirmation screen; v2 does not navigate to a chat, choose favorites or type recipients. Use `submit` only in the future authorized integration. Each request is a JSON-compatible object with these fields:

* `reviewer`, `oid`, exact profile `friend_id`, canonical `article_key`.
* `profile`: `reviewer`, `evidence`, matching `oid` and `friend_id`, `field:"WeChat ID"`, `same_row:true`.
* `favorite`: `reviewer`, `evidence`, `url`, fixed original `title`/`source`, `first_favorite:true`, `exactly_one:true`, `url_observed:true`, nonempty `association_note` explaining the actual URL association.
* Final screen: `evidence`, `screen:"send-confirmation"`, `recipient_id` matching the profile, integer `recipient_count:1`, integer `article_count:1`, `recipient_matches_profile:true`, `article_matches_favorite:true`, `url` resolving to the same article key, `send_control:true`, `target:[root_x,root_y,width,height]`, integer click `x` and `y` within that reviewed target.

Profile, favorite and final captures must have distinct evidence IDs, intact hashes and be under 180 seconds old. Final evidence must be latest and no earlier than the other two captures. The stored contact mapping and article are revalidated. Live full geometry/class/title and active window must still match final evidence immediately before intent and again after intent. A moved window invalidates the old coordinates; recapture and re-review, never scale or reuse them. Once intent exists, geometry failure blocks retry even if no click occurred.

`current_queue(store)` reuses reviewed page first-occurrence order and exact-ID deduplication, never contact insertion order or nicknames. It returns the existing dry-run report plus `next` and `reconciliation_required`; it remains `send_enabled:false` and does not grant approval. It may materialize pending pairs just like original dry-run. Confirmed entries are skipped. Unmapped legacy and unidentified rows remain explicitly blocked/excluded. Any submitting/uncertain pair for the current article pauses all new sends. Only the first remaining eligible pending pair may be requested.

### Durable submission and reconciliation

The adapter holds the original process lock, read-only old-state lock and persistent lease. It commits pending → submitting before exactly one button-1 click, then captures a fresh dynamic-window PNG and records an event. Successful tool execution is not confirmation: status stays submitting. Input/post-capture failures become uncertain if the recovery write succeeds; a crash before recovery leaves submitting. Both statuses survive restart and block re-click. Never reset them to pending, delete the DB, or retry.

`reconcile(store, review, token)` and the v2 `reconcile --data JSON --token TOKEN` command perform **no UI input**. They can change only an existing submitting/uncertain sender intent to confirmed, using **new recipient/article/time evidence**. The review must include `reviewer`, `friend_id`, `article_key`, fresh latest `evidence` captured after intent at a different path than the pre-send capture, matching `recipient_id`, `recipient_verified:true`, `outgoing:true`, `exactly_one:true`, actual outgoing-card `url`, `url_observed:true`, nonempty `association_note`, numeric `observed_at` between intent and capture, `time_visible:true`, and nonempty `time_note` describing the visible send timestamp and association. Review the post-send screenshot or acquire a new capture; merely reusing an old confirmation is forbidden. An ambiguous result stays blocked: there is no negative-result retry/reset command. Reconciliation cannot approve pending or already confirmed pairs.

These are external semantic attestations, not autonomous visual recognition or authenticated reviewer identities. The reviewer must honestly associate the exact recipient, outgoing card URL and visible time with this intent. A screenshot hash alone proves neither delivery nor recipient identity. Keep exclusive desktop ownership; geometry checks cannot detect all same-window semantic changes by another actor.

### Targeted development verification

Run only the new isolated suite, with all desktop executors faked:

    cd /tmp/wxview92/upgrade_20261010T1529
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_controller_sender_v2

Do not run init/capture/navigate/reconcile against live data or inject approving callbacks with real executors during development. Existing safe navigation is sufficient; parent may independently move the actual window under its own lease and recapture/re-review. Parent separately verifies historical-card URLs and any deployment handoff. Mock tests do not establish those real-world facts. No alternate production ledger is introduced.
