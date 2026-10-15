"""fast_v2 helpers: in-process Xlib window queries, in-memory capture, async debug frames.

Same ownership semantics as wxio.observe() (pid-filtered stacking list, unique 'Weixin' main),
but one persistent X connection instead of xprop/xwininfo subprocesses per window.
"""
import ctypes as C
import json
import os
import queue
import threading
import time

import wxio
from wxio import need, ImageGrab

_x = C.CDLL('libX11.so.6')


class XWindowAttributes(C.Structure):
    _fields_ = [('x', C.c_int), ('y', C.c_int), ('width', C.c_int), ('height', C.c_int),
                ('border_width', C.c_int), ('depth', C.c_int), ('visual', C.c_void_p),
                ('root', C.c_ulong), ('c_class', C.c_int), ('bit_gravity', C.c_int),
                ('win_gravity', C.c_int), ('backing_store', C.c_int), ('backing_planes', C.c_ulong),
                ('backing_pixel', C.c_ulong), ('save_under', C.c_int), ('colormap', C.c_ulong),
                ('map_installed', C.c_int), ('map_state', C.c_int), ('all_event_masks', C.c_long),
                ('your_event_mask', C.c_long), ('do_not_propagate_mask', C.c_long),
                ('override_redirect', C.c_int), ('screen', C.c_void_p)]


for name, args, res in (
        ('XOpenDisplay', [C.c_char_p], C.c_void_p),
        ('XDefaultRootWindow', [C.c_void_p], C.c_ulong),
        ('XInternAtom', [C.c_void_p, C.c_char_p, C.c_int], C.c_ulong),
        ('XGetWindowProperty', [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long, C.c_int, C.c_ulong,
                                C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong),
                                C.POINTER(C.c_ulong), C.POINTER(C.c_void_p)], C.c_int),
        ('XGetWindowAttributes', [C.c_void_p, C.c_ulong, C.POINTER(XWindowAttributes)], C.c_int),
        ('XTranslateCoordinates', [C.c_void_p, C.c_ulong, C.c_ulong, C.c_int, C.c_int,
                                   C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_ulong)], C.c_int),
        ('XGetTransientForHint', [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong)], C.c_int),
        ('XFree', [C.c_void_p], C.c_int),
        ('XSync', [C.c_void_p, C.c_int], C.c_int),
        ('XSetErrorHandler', [C.c_void_p], C.c_void_p)):
    f = getattr(_x, name); f.argtypes = args; f.restype = res

_ERR = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)(lambda d, e: 0)  # windows may vanish mid-query
_x.XSetErrorHandler(C.cast(_ERR, C.c_void_p))


class XQ:
    def __init__(self):
        self.d = _x.XOpenDisplay(b':1')
        need(bool(self.d), 'XOpenDisplay failed')
        self.root = _x.XDefaultRootWindow(self.d)
        self.atom = {n: _x.XInternAtom(self.d, n.encode(), 0) for n in (
            '_NET_ACTIVE_WINDOW', '_NET_CLIENT_LIST_STACKING', '_NET_WM_PID', '_NET_WM_NAME',
            'UTF8_STRING', '_NET_WM_WINDOW_TYPE')}

    def prop(self, w, name, kind='card'):
        t, f, n, left, data = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong(), C.c_void_p()
        st = _x.XGetWindowProperty(self.d, w, self.atom[name], 0, 4096, 0, 0, C.byref(t), C.byref(f),
                                   C.byref(n), C.byref(left), C.byref(data))
        try:
            if st != 0 or not data or n.value == 0:
                return [] if kind == 'card' else ''
            if f.value == 32:
                return list(C.cast(data, C.POINTER(C.c_ulong))[:n.value])
            return C.string_at(data, n.value).decode('utf-8', 'replace')
        finally:
            if data:
                _x.XFree(data)

    def geom(self, w):
        a = XWindowAttributes()
        if not _x.XGetWindowAttributes(self.d, w, C.byref(a)):
            return None
        ax, ay, child = C.c_int(), C.c_int(), C.c_ulong()
        _x.XTranslateCoordinates(self.d, w, self.root, 0, 0, C.byref(ax), C.byref(ay), C.byref(child))
        return dict(x=ax.value, y=ay.value, w=a.width, h=a.height, viewable=a.map_state == 2)

    def observe(self, pid):
        active = (self.prop(self.root, '_NET_ACTIVE_WINDOW') or [0])[0]
        stack = self.prop(self.root, '_NET_CLIENT_LIST_STACKING')
        wins = []
        for w in stack:
            if (self.prop(w, '_NET_WM_PID') or [0])[0] != pid:
                continue
            g = self.geom(w)
            if not g or not g['viewable']:
                continue
            tr = C.c_ulong()
            transient = tr.value if _x.XGetTransientForHint(self.d, w, C.byref(tr)) else None
            wins.append(dict(id=w, name=self.prop(w, '_NET_WM_NAME', 'str'), geom=g, transient=transient))
        mains = [w for w in wins if w['name'] == 'Weixin' and w['transient'] is None]
        need(len(mains) == 1, 'exactly one visible Weixin main window required: %r' % mains)
        return dict(pid=pid, active=active, stack=stack, wechat=wins, main=mains[0],
                    active_is_wechat=any(w['id'] == active for w in wins))


class DebugSink:
    """Bounded async PNG writer; drops debug frames when full, never blocks the flow."""

    def __init__(self, directory, maxsize=16):
        self.dir = directory
        self.q = queue.Queue(maxsize)
        self.dropped = 0
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def put(self, name, image):
        try:
            self.q.put_nowait((name, image))
        except queue.Full:
            self.dropped += 1

    def _run(self):
        while True:
            item = self.q.get()
            if item is None:
                return
            name, im = item
            try:
                p = self.dir / name
                if p.exists():
                    p = self.dir / ('%s_%d%s' % (p.stem, int(time.time() * 1000), p.suffix))
                im.save(p, compress_level=1)
                os.chmod(p, 0o400)
            except Exception as e:          # debug frames are best-effort; never kill the writer
                self.errors = getattr(self, 'errors', 0) + 1

    def close(self):
        try:
            self.q.put(None, timeout=5)
        except queue.Full:
            pass
        self.t.join(timeout=30)


class Journal:
    """Buffered event log (no per-event fsync); the send ledger stays synchronous elsewhere."""

    def __init__(self, path):
        self.f = path.open('a')

    def event(self, **kw):
        kw.setdefault('t', time.time())
        line = json.dumps(kw, ensure_ascii=False, default=str)
        self.f.write(line + '\n')
        print('EVENT', line[:300], flush=True)

    def close(self):
        self.f.flush(); os.fsync(self.f.fileno()); self.f.close()


def grab():
    at = time.time()
    return at, ImageGrab.grab(xdisplay=':1').convert('RGB')
