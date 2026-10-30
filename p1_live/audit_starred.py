"""audit_starred: read-only re-check of every starred friend with the current chat classifier.

Walks only the 'Starred' section (send_starred's scan / section end) and runs star_v1's per-row flow in dry-run
mode: open the chat from the row menu, classify since WX_STAR_SINCE (default 2026-10-01). Nothing is starred or
unstarred: rows whose chat does not show a friend message since the cutoff are listed for review.

Usage: python3 -I audit_starred.py [--max-rows N] [--from-current [--ordinal-base N]]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('WX_STAR_ID', 'audit_starred_' + os.environ.get('WX_STAR_SINCE', '2026-10-01'))
import star_v1  # noqa: E402  (env for request id / ledger before batch_v2)
from star_v1 import StarEngine, Stop, Unknown, need  # noqa: E402
import send_starred  # noqa: E402


class AuditEngine(StarEngine):
    scan = send_starred.StarredSendEngine.scan

    def scroll(self, st, f, g, button, notches):
        # past the Starred section: report "list did not move" so the batch ends with its tail record
        if button == 5 and self.section_end:
            self.j.event(kind='section_end')
            return
        return StarEngine.scroll(self, st, f, g, button, notches)

    def __init__(self, max_rows=None):
        super().__init__(False, max_rows)          # dry run: no star / unstar clicks
        self.section_end = False

    def star(self, rec, row, g, f, ledger):
        rec['outcome'] = 'QUALIFIES'               # already starred and still qualifies: nothing to read or click
        return f


if __name__ == '__main__':
    max_rows = int(sys.argv[sys.argv.index('--max-rows') + 1]) if '--max-rows' in sys.argv else None
    eng = AuditEngine(max_rows)
    if '--from-current' in sys.argv:
        eng.from_current = True
        eng.ordinal_base = int(sys.argv[sys.argv.index('--ordinal-base') + 1]) if '--ordinal-base' in sys.argv else 0
    try:
        r = eng.run()
        print(json.dumps({k: v for k, v in r.items() if k not in ('contacts', 'all_stages')}, ensure_ascii=False, indent=1, default=str))
    except (Stop, Unknown, Exception) as e:
        e = Stop('%s: %s' % (type(e).__name__, e)) if not isinstance(e, Stop) else e
        eng.j.event(kind='stop', reason=str(e))
        try:
            eng.finish_batch(eng.T0, eng.seen, dict(stopped=str(e)))
        except Exception as e2:
            print('finish failed', e2)
        print('STOP:', e)
        sys.exit(2)
