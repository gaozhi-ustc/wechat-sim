"""Permanent do-not-send list (user instruction 2026-10-26): never send any message to these friends.

Checked twice on every send path:
  * batch_v2.process: right after the profile OCR -> outcome EXCLUDED_DO_NOT_SEND (no chat/panel opened);
  * ocr_mvp_v1.Ledger.put(..., 'PREPARED'): the durable intent written before every Send click (ocr_mvp_v1,
    fast_v2, batch_v2 and everything built on them) -> raises, so Send is never clicked.
Matching: Weixin ID case/glyph-folded with one OCR substitution allowed, or the display name appearing in any
recipient text (profile name, row name, panel header "Send favorites to ..."). Matching is deliberately broad:
a false positive only skips a send.
The list itself lives in do_not_send.json next to this file ([[weixin_id, display_name], ...]); it holds contact
names / Weixin IDs, so it is git-ignored. A missing or empty list fails the import, so no send path can run without it.
"""
import json
import os
import re

_LIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'do_not_send.json')
with open(_LIST, encoding='utf-8') as _f:
    BLOCKED = tuple((bid, bname) for bid, bname in json.load(_f))
if not BLOCKED:
    raise RuntimeError('do-not-send list %s is empty' % _LIST)

_FOLD = str.maketrans({'o': '0', 'l': '1', 'i': '1', '|': '1', 's': '5', 'z': '2', 'b': '8', 'q': 'g'})


def _fold_id(w):
    return (w or '').lower().translate(_FOLD).replace('_', '').replace('-', '')


def _canon(s):
    return re.sub(r'[\s"“”\'‘’()（）<>《》:：,，.。★]+', '', s or '').lower()


def blocked(weixin_id=None, *texts):
    """-> reason string when the recipient is on the do-not-send list, else None."""
    w = _fold_id(weixin_id)
    for bid, bname in BLOCKED:
        b = _fold_id(bid)
        if w and (w == b or (len(w) == len(b) and sum(x != y for x, y in zip(w, b)) <= 1)):
            return 'do-not-send: Weixin ID %r ~ %r (%s)' % (weixin_id, bid, bname)
        n = _canon(bname)
        for t in texts:
            if t and n in _canon(t):
                return 'do-not-send: %r contains %r (%s)' % (t, bname, bid)
    return None
