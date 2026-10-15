"""Minimal X11 capture/input + OCR helpers for the ocr_mvp_v1 first real flow.

Reuses the production adapter's approach (PIL ImageGrab, ctypes XTest) but without the
checkpoint/approval machinery. No LLM calls anywhere.
"""
import ctypes as C
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SITE = os.environ.get('WX_SITE', '/home/gaozhi/fav_forward_20261010/upgrade_20261010T1529/ocr_site_20261013T1355')
if SITE not in sys.path:
    sys.path.insert(0, SITE)

from PIL import Image, ImageGrab  # noqa: E402
import numpy as np  # noqa: E402

os.environ['DISPLAY'] = ':1'
OUT = Path(__file__).resolve().parent / 'evidence'
OUT.mkdir(mode=0o700, exist_ok=True)


class Stop(Exception):
    """Unrecoverable: stop, never retry blindly."""


def need(cond, msg):
    if not cond:
        raise Stop(msg)


def sh(args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=5, env=dict(os.environ, DISPLAY=':1')).stdout.decode()


def wid_props(w):
    return sh(['xprop', '-id', str(w), '_NET_WM_PID', 'WM_CLASS', 'WM_TRANSIENT_FOR',
               '_NET_WM_WINDOW_TYPE', 'WM_NAME', '_NET_WM_NAME'])


def geometry(w):
    t = sh(['xwininfo', '-id', str(w)])
    g = {}
    for k, label in (('x', 'Absolute upper-left X'), ('y', 'Absolute upper-left Y'),
                     ('w', 'Width'), ('h', 'Height')):
        m = re.search(r'^\s*' + label + r':\s*(-?\d+)', t, re.M)
        need(m is not None, 'missing geometry')
        g[k] = int(m.group(1))
    g['viewable'] = 'Map State: IsViewable' in t
    return g


def root_context():
    t = sh(['xprop', '-root', '_NET_ACTIVE_WINDOW', '_NET_CLIENT_LIST_STACKING'])
    m = re.search(r'_NET_ACTIVE_WINDOW.*?(0x[0-9a-fA-F]+)', t)
    active = int(m.group(1), 16) if m else 0
    line = next((s for s in t.splitlines() if s.startswith('_NET_CLIENT_LIST_STACKING(')), '')
    stack = [int(v, 16) for v in re.findall(r'0x[0-9a-fA-F]+', line)]
    return active, stack


def wechat_pid():
    pids = [int(p) for p in os.listdir('/proc') if p.isdigit()
            and _comm(p) == 'wechat']
    need(len(pids) == 1, 'exactly one wechat process required, got %r' % pids)
    return pids[0]


def _comm(p):
    try:
        return Path('/proc/%s/comm' % p).read_text().strip()
    except OSError:
        return ''


def observe():
    """Window ownership snapshot: main WeChat window, active window, WeChat windows."""
    pid = wechat_pid()
    active, stack = root_context()
    wins = []
    for w in stack:
        p = wid_props(w)
        m = re.search(r'_NET_WM_PID\(CARDINAL\) = (\d+)', p)
        if not m or int(m.group(1)) != pid:
            continue
        g = geometry(w)
        if not g['viewable']:
            continue
        name = re.search(r'_NET_WM_NAME\(UTF8_STRING\) = "(.*)"', p)
        tr = re.search(r'WM_TRANSIENT_FOR.*?(0x[0-9a-fA-F]+)', p)
        wtype = re.search(r'_NET_WM_WINDOW_TYPE\(ATOM\) = (\S+)', p)
        wins.append(dict(id=w, name=name.group(1) if name else '', geom=g,
                         transient=int(tr.group(1), 16) if tr else None,
                         type=wtype.group(1) if wtype else None))
    mains = [w for w in wins if w['name'] == 'Weixin' and w['transient'] is None]
    need(len(mains) == 1, 'exactly one visible Weixin main window required: %r' % mains)
    return dict(pid=pid, active=active, stack=stack, wechat=wins, main=mains[0],
                active_is_wechat=any(w['id'] == active for w in wins),
                top_is_wechat=bool(stack) and any(w['id'] == stack[-1] for w in wins))


class Recorder:
    def __init__(self, run_id):
        self.dir = OUT / run_id
        self.dir.mkdir(mode=0o700, exist_ok=True)
        self.log = (self.dir / 'events.jsonl').open('a')
        self.n = 0

    def event(self, **kw):
        kw.setdefault('t', time.time())
        self.log.write(json.dumps(kw, ensure_ascii=False, default=str) + '\n')
        self.log.flush()
        os.fsync(self.log.fileno())
        print('EVENT', json.dumps(kw, ensure_ascii=False, default=str)[:600], flush=True)

    def capture(self, tag):
        before = observe()
        at = time.time()
        im = ImageGrab.grab(xdisplay=':1').convert('RGB')
        after = observe()
        need(before['main']['geom'] == after['main']['geom'] and before['active'] == after['active'],
             'window context changed during capture')
        self.n += 1
        path = self.dir / ('%02d_%s.png' % (self.n, tag))
        im.save(path)
        os.chmod(path, 0o400)
        frame = dict(id=self.n, tag=tag, path=str(path), at=at, owner=after, image=im)
        self.event(kind='capture', frame=self.n, tag=tag, path=str(path),
                   active=after['active'], main=after['main'], active_is_wechat=after['active_is_wechat'],
                   wechat=[(w['id'], w['name'], w['geom'], w['transient']) for w in after['wechat']])
        return frame


class X:
    def __init__(self):
        self.x = C.CDLL('libX11.so.6')
        self.xt = C.CDLL('libXtst.so.6')
        self.x.XOpenDisplay.argtypes = [C.c_char_p]; self.x.XOpenDisplay.restype = C.c_void_p
        self.x.XSync.argtypes = [C.c_void_p, C.c_int]
        self.x.XKeysymToKeycode.argtypes = [C.c_void_p, C.c_ulong]; self.x.XKeysymToKeycode.restype = C.c_ubyte
        self.x.XStringToKeysym.argtypes = [C.c_char_p]; self.x.XStringToKeysym.restype = C.c_ulong
        self.xt.XTestFakeMotionEvent.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_ulong]
        self.xt.XTestFakeButtonEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        self.xt.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        self.d = self.x.XOpenDisplay(b':1')
        need(bool(self.d), 'XOpenDisplay failed')

    def move(self, x, y):
        need(self.xt.XTestFakeMotionEvent(self.d, -1, int(x), int(y), 0), 'motion failed')
        self.x.XSync(self.d, 0)

    def click(self, x, y, button=1):
        self.move(x, y)
        time.sleep(0.08)
        need(self.xt.XTestFakeButtonEvent(self.d, button, 1, 0), 'press failed')
        # Never repeat a possibly delivered press.
        need(self.xt.XTestFakeButtonEvent(self.d, button, 0, 0), 'release failed')
        self.x.XSync(self.d, 0)

    def key(self, name):
        code = self.x.XKeysymToKeycode(self.d, self.x.XStringToKeysym(name.encode()))
        need(code, 'no keycode for ' + name)
        need(self.xt.XTestFakeKeyEvent(self.d, code, 1, 0), 'key press failed')
        need(self.xt.XTestFakeKeyEvent(self.d, code, 0, 0), 'key release failed')
        self.x.XSync(self.d, 0)


_OCR = None


def ocr_engine():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    return _OCR


def ocr(image, box):
    """OCR a screen-absolute box [x,y,w,h]; returns [(text, score, abs_box)]."""
    x, y, w, h = box
    crop = np.asarray(image.crop((x, y, x + w, y + h)))[:, :, ::-1].copy()
    res, _ = ocr_engine()(crop)
    out = []
    for quad, text, score in res or []:
        xs = [p[0] for p in quad]; ys = [p[1] for p in quad]
        out.append((text, float(score), [int(x + min(xs)), int(y + min(ys)),
                                         int(max(xs) - min(xs)), int(max(ys) - min(ys))]))
    return out


def center(b):
    return b[0] + b[2] // 2, b[1] + b[3] // 2
