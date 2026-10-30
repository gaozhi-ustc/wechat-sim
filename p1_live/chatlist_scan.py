"""chatlist_scan: read-only scan of the Chats list (name / time / last-message preview of every conversation).

No chat is opened: only the list is scrolled (paced wheel) and OCR'd page by page; consecutive pages must overlap.
Output: JSON lines {name, time, preview, y, page} -> evidence/chatlist_<ts>.jsonl
Usage: python3 -I chatlist_scan.py [--max-pages N]
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wxio  # noqa: E402
import wxfast  # noqa: E402
from batch_v2 import canon  # noqa: E402
import numpy as np  # noqa: E402

LIST = (61, 81, 240, 689)        # window-relative chat list area
ROW_H = 65


def parse(texts, g):
    """-> rows [(name, time, preview, y)] of complete rows on the page."""
    rel = [(t[0].strip(), t[2][0] - g['x'], t[2][1] - g['y'], t[2][3]) for t in texts]
    times = [r for r in rel if r[1] >= 190]
    # a name line carries the time stamp on the same line; preview lines (also at x~118) do not
    names = [r for r in rel if 105 <= r[1] <= 135 and any(abs(t[2] - r[2]) <= 8 for t in times)]
    rows = []
    for n, x, y, h in sorted(names, key=lambda r: r[2]):
        if y < LIST[1] + 4 or y > LIST[1] + LIST[3] - 45:
            continue                                       # partially visible row
        tm = [r[0] for r in times if abs(r[2] - y) <= 8]
        pv = [r for r in rel if 105 <= r[1] < 200 and 12 <= r[2] - y <= 30]
        prev = ' '.join(r[0] for r in sorted(pv, key=lambda r: r[1]))
        rows.append(dict(name=n, time=' '.join(tm), preview=prev, y=y))
    return rows


def main():
    max_pages = int(sys.argv[sys.argv.index('--max-pages') + 1]) if '--max-pages' in sys.argv else 2000
    q = wxfast.XQ(); pid = wxio.wechat_pid(); X = wxio.X()
    o = q.observe(pid); g = o['main']['geom']
    assert len(o['wechat']) == 1, 'close WeChat popups first'
    out = wxio.OUT / ('chatlist_%s.jsonl' % time.strftime('%Y%m%dT%H%M%S'))
    fo = out.open('w')

    def wheel(n, button):
        X.move(g['x'] + 180, g['y'] + 400)
        for i in range(n):
            X.xt.XTestFakeButtonEvent(X.d, button, 1, 0); X.xt.XTestFakeButtonEvent(X.d, button, 0, 0)
            X.x.XSync(X.d, 0); time.sleep(0.03)
        X.move(g['x'] + 700, g['y'] + 16)

    def grab_stable():
        prev = None
        for i in range(15):
            time.sleep(0.25)
            im = wxio.ImageGrab.grab(xdisplay=':1').convert('RGB')
            a = np.asarray(im.crop((g['x'] + LIST[0], g['y'] + LIST[1], g['x'] + LIST[0] + LIST[2], g['y'] + LIST[1] + LIST[3])))
            if prev is not None and np.array_equal(a, prev):
                return im, a
            prev = a
        return im, a

    X.click(g['x'] + 31, g['y'] + 113)                     # Chats tab
    time.sleep(0.8)
    wheel(3000, 4)                                         # to the top
    seen, last_names, same, total = set(), None, 0, 0
    for page in range(max_pages):
        im, a = grab_stable()
        texts = wxio.ocr(im, [g['x'] + LIST[0], g['y'] + LIST[1], LIST[2], LIST[3]])
        rows = parse(texts, g)
        names = [canon(r['name']) for r in rows]
        if last_names and not (set(names[:3]) & set(last_names[-4:])):
            wheel(2, 4)                                    # no overlap with the previous page: step back
            im, a = grab_stable()
            texts = wxio.ocr(im, [g['x'] + LIST[0], g['y'] + LIST[1], LIST[2], LIST[3]])
            rows = parse(texts, g)
            names = [canon(r['name']) for r in rows]
        new = 0
        for r in rows:
            k = (canon(r['name']), canon(r['preview']), r['time'])
            if k in seen:
                continue
            seen.add(k); new += 1; total += 1
            fo.write(json.dumps(dict(r, page=page), ensure_ascii=False) + '\n')
        fo.flush()
        print('page', page, 'rows', len(rows), 'new', new, 'total', total, names[:1], names[-1:], flush=True)
        same = same + 1 if new == 0 else 0
        if same >= 2:
            break                                          # bottom of the list
        last_names = names
        wheel(5, 5)
    fo.close()
    print('written', out, total)


if __name__ == '__main__':
    main()
