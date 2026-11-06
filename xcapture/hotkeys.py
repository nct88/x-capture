"""Phím tắt toàn cục bằng XGrabKey trên cửa sổ root (X11)."""
import os
import select
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

try:
    from Xlib import X, XK, display as xdisplay, error as xerror
    HAVE_XLIB = True
except ImportError:  # pragma: no cover
    HAVE_XLIB = False

QT_TO_XK = {
    "Esc": "Escape", "PgUp": "Prior", "PgDown": "Next", "Del": "Delete", "Ins": "Insert",
    "Return": "Return", "Enter": "KP_Enter", "Space": "space", "Backspace": "BackSpace",
    "ScrollLock": "Scroll_Lock", "SysReq": "Sys_Req", "Print": "Print", "Pause": "Pause",
    "Tab": "Tab", "Home": "Home", "End": "End", "Left": "Left", "Right": "Right",
    "Up": "Up", "Down": "Down", "Menu": "Menu",
}


def parse_sequence(seq):
    """'Ctrl+Shift+Print' -> (keysym, modmask) hoặc None."""
    if not HAVE_XLIB or not seq:
        return None
    parts = seq.split("+")
    # Phím '+' tự nó: 'Ctrl++'
    if seq.endswith("++"):
        parts = seq[:-2].split("+") + ["plus"]
    mods = 0
    key = None
    for p in parts:
        if p == "Ctrl":
            mods |= X.ControlMask
        elif p == "Shift":
            mods |= X.ShiftMask
        elif p == "Alt":
            mods |= X.Mod1Mask
        elif p in ("Meta", "Super"):
            mods |= X.Mod4Mask
        else:
            key = p
    if not key:
        return None
    name = QT_TO_XK.get(key, key.lower() if len(key) == 1 else key)
    sym = XK.string_to_keysym(name)
    if not sym:
        return None
    return sym, mods


class HotkeyManager(QObject):
    triggered = pyqtSignal(str)
    status = pyqtSignal(dict)  # hành động -> True (đã đăng ký) / False (bị chiếm)
    kind = "x11"

    def __init__(self):
        super().__init__()
        self.available = HAVE_XLIB and bool(os.environ.get("DISPLAY"))
        self.results = {}
        self._pending = None
        self._lock = threading.Lock()
        self._rfd, self._wfd = os.pipe()
        self._last = {}
        if self.available:
            threading.Thread(target=self._run, daemon=True).start()

    def shutdown(self):
        pass

    def set_bindings(self, mapping):
        with self._lock:
            self._pending = dict(mapping)
        os.write(self._wfd, b"x")

    def _apply(self, d, root, mapping, grabbed):
        for keycode, mods in grabbed:
            for extra in self._extras:
                root.ungrab_key(keycode, mods | extra)
        grabbed.clear()
        table = {}
        results = {}
        for action, seq in mapping.items():
            parsed = parse_sequence(seq)
            if not parsed:
                if seq:
                    results[action] = False
                continue
            sym, mods = parsed
            keycode = d.keysym_to_keycode(sym)
            if not keycode:
                results[action] = False
                continue
            ec = xerror.CatchError(xerror.BadAccess)
            for extra in self._extras:
                root.grab_key(keycode, mods | extra, True, X.GrabModeAsync, X.GrabModeAsync, onerror=ec)
            d.sync()
            if ec.get_error():
                for extra in self._extras:
                    root.ungrab_key(keycode, mods | extra)
                d.sync()
                results[action] = False
            else:
                grabbed.append((keycode, mods))
                table[(keycode, mods)] = action
                results[action] = True
        self.results = results
        self.status.emit(results)
        return table

    def _run(self):
        try:
            d = xdisplay.Display()
        except Exception:
            self.available = False
            return
        root = d.screen().root
        # Bỏ qua CapsLock / NumLock / ScrollLock khi so khớp.
        num = X.Mod2Mask
        self._extras = [0, X.LockMask, num, X.LockMask | num]
        relevant = X.ControlMask | X.ShiftMask | X.Mod1Mask | X.Mod4Mask
        grabbed = []
        table = {}
        while True:
            r, _, _ = select.select([d.fileno(), self._rfd], [], [], 1.0)
            if self._rfd in r:
                os.read(self._rfd, 64)
                with self._lock:
                    mapping, self._pending = self._pending, None
                if mapping is not None:
                    try:
                        table = self._apply(d, root, mapping, grabbed)
                    except Exception:
                        table = {}
            while d.pending_events():
                ev = d.next_event()
                if ev.type != X.KeyPress:
                    continue
                action = table.get((ev.detail, ev.state & relevant))
                if not action:
                    continue
                now = time.monotonic()
                if now - self._last.get(action, 0) < 0.35:
                    continue
                self._last[action] = now
                self.triggered.emit(action)


class NullHotkeys(QObject):
    """Phiên Wayland không có cách đăng ký phím toàn cục: dùng phím tắt của desktop gọi `x-capture --rect`..."""
    triggered = pyqtSignal(str)
    status = pyqtSignal(dict)
    kind = "none"
    available = False
    results = {}

    def set_bindings(self, mapping):
        pass

    def shutdown(self):
        pass


def create_hotkeys(labels):
    """KDE (X11 lẫn Wayland): kglobalaccel; X11 khác: XGrabKey; Wayland khác: không có."""
    from . import session
    if session.is_kde():
        try:
            from . import kde
            mgr = kde.KGlobalAccelHotkeys(labels)
            if mgr.available:
                return mgr
        except ImportError:
            pass
    if not session.is_wayland():
        return HotkeyManager()
    return NullHotkeys()
