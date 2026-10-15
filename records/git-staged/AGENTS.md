# Project rules

Scope: 92 WeChat reviewed-controller continuation only. ZERO real sends until a separate manager authorization and reviewed approval integration; old Q3 RPA untouched. Never change legacy complete state or create a second production ledger. Preserve historical evidence. See README.md for CLI/evidence/locking contracts, CONTINUATION_20261010T1620.md for handoff and unresolved mappings.

Runtime production DB: /home/gaozhi/fav_forward_20261010/upgrade_20261010T1529/ledger.sqlite3 only. Local tests use cleaned temporary fixtures. No credentials, leases, DB, contact exports, screenshots, old pilot state or runtime logs in Git.

Targeted sender verification: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_controller_sender_v2. No live UI during tests; don't rerun unaffected original tests. External reviewer evidence does not authenticate identity by itself. Current submit CLI must stay denied.

Source-only main Git repository initialized at continuation delivery; initial commit blocked by missing Git author identity (not fabricated). Allowlist staged original controller/test, new sender/test, README, this file, .gitignore. Review meaningful changes and commit locally; no push authorized. Evidence and delivery reports remain untracked artifacts alongside source.
