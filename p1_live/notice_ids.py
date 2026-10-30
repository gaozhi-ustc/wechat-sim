"""notice_ids: Weixin IDs of friends whose conversation ends with "开启了朋友验证" (they deleted / blocked the owner),
matched against the send ledger of one campaign.

Input: a chatlist_scan JSONL (name / time / preview of every conversation) and the send ledger (intent has row,
profile, header, weixin_id). Names in the Chats list can be truncated ('...'): exact canonical match first, then
prefix match; several candidates -> AMBIGUOUS (all listed), none -> UNMATCHED (not sent in this campaign).
Usage: python3 -I notice_ids.py <chatlist.jsonl> [campaign_request_id] > out.tsv
"""
import json
import re
import sqlite3
import sys

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from batch_v2 import canon  # noqa: E402

NOTICE = re.compile(r'朋友验[证正]|开[启后]了朋友')
LEDGER = '/home/gaozhi/wechat_batch/ledger_assfox.sqlite3'


def header_name(h):
    m = re.search(r'to\s*["“”]?(.+?)["“”]?\s*$', h or '')
    return m.group(1) if m else ''


def main():
    path = sys.argv[1]
    rid = sys.argv[2] if len(sys.argv) > 2 else 'fav_assfox_20261027T011121'
    db = sqlite3.connect(LEDGER)
    sent = []
    for k, i in db.execute("SELECT op_key,intent FROM ops WHERE request_id=? AND state='SEND_CLICKED'", (rid,)):
        d = json.loads(i or '{}')
        names = {canon(n) for n in (d.get('row'), d.get('profile'), header_name(d.get('header'))) if n} - {''}
        sent.append((k.split('|wxid:', 1)[1], d.get('profile') or d.get('row'), names))
    rows = [json.loads(l) for l in open(path) if l.strip()]
    hits = {}
    for r in rows:
        if NOTICE.search(r['preview']):
            hits.setdefault(canon(r['name']), r)
    print('chat_name\tlist_time\tweixin_id\tsent_name\tmatch')
    for cn, r in hits.items():
        base = re.sub(r'\.+$', '', r['name'])
        cb = canon(base)
        exact = [s for s in sent if cb in s[2]]
        pref = exact or [s for s in sent if cb and len(cb) >= 2 and any(n.startswith(cb) for n in s[2])]
        if len(pref) == 1:
            print('%s\t%s\t%s\t%s\t%s' % (r['name'], r['time'], pref[0][0], pref[0][1], 'exact' if exact else 'prefix'))
        elif pref:
            print('%s\t%s\t%s\t%s\tAMBIGUOUS' % (r['name'], r['time'], ','.join(s[0] for s in pref), '/'.join(s[1] or '' for s in pref)))
        else:
            print('%s\t%s\t\t\tUNMATCHED' % (r['name'], r['time']))


if __name__ == '__main__':
    main()
