"""Tích hợp KDE Plasma qua D-Bus: chụp màn hình (KWin ScreenShot2), danh sách cửa sổ (KWin script)
và phím tắt toàn cục (kglobalaccel). Dùng được cả trên Plasma Wayland lẫn X11."""
import json
import os
import tempfile

from PyQt6.QtCore import QEventLoop, QObject, QRect, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage, QKeySequence

from . import dbusutil as D

KWIN = "org.kde.KWin"
KGA = "org.kde.kglobalaccel"
COMPONENT = "x-capture"
# kglobalaccel: SetPresent (đang chạy, hãy bắt phím) | NoAutoloading (dùng phím X-Capture gửi lên)
SET_FLAGS = 2 | 4


class NotAuthorized(Exception):
    """KWin chỉ cho chụp khi tệp .desktop của tiến trình khai báo X-KDE-DBUS-Restricted-Interfaces."""


def kwin_available():
    return D.HAVE_QTDBUS and D.has_service(KWIN)


# ---------- chụp màn hình ----------
def screenshot():
    """Chụp toàn bộ desktop ở độ phân giải gốc. Trả về QImage; NotAuthorized nếu KWin từ chối."""
    from PyQt6.QtDBus import QDBusUnixFileDescriptor
    rfd, wfd = os.pipe()
    try:
        try:
            meta = D.call(KWIN, "/org/kde/KWin/ScreenShot2", "org.kde.KWin.ScreenShot2", "CaptureWorkspace",
                          {"native-resolution": True, "include-cursor": False},
                          QDBusUnixFileDescriptor(wfd), timeout=10000)[0]
        except D.DBusError as ex:
            if "NoAuthorized" in ex.name or "AccessDenied" in ex.name:
                raise NotAuthorized(str(ex)) from None
            raise
        finally:
            os.close(wfd)  # KWin giữ bản sao; đóng đầu ghi của mình để đọc tới EOF
        data = bytearray()
        while True:
            chunk = os.read(rfd, 1 << 20)
            if not chunk:
                break
            data += chunk
    finally:
        os.close(rfd)
    w, h, stride = int(meta["width"]), int(meta["height"]), int(meta["stride"])
    if len(data) < stride * h:
        raise RuntimeError("KWin ScreenShot2: incomplete image data")
    img = QImage(bytes(data), w, h, stride, QImage.Format(int(meta["format"])))
    return img.copy()  # tách khỏi bộ đệm Python


# ---------- danh sách cửa sổ ----------
WINDOWS_JS = r"""
const ws = workspace;
const list = ws.stackingOrder || (ws.clientList ? ws.clientList() : []);
const act = ws.activeWindow || ws.activeClient;
const desk = ws.currentDesktop;
const vs = ws.virtualScreenGeometry;
function onDesk(w) {
    if (w.onAllDesktops) return true;
    if (w.desktops) return w.desktops.indexOf(desk) >= 0;
    return w.desktop === desk || w.desktop === -1;
}
function onActivity(w) {
    return !w.activities || w.activities.length === 0 || !ws.currentActivity
        || w.activities.indexOf(ws.currentActivity) >= 0;
}
const out = [];
for (let i = 0; i < list.length; i++) {
    const w = list[i];
    if (!w || w.deleted || w.minimized || w.desktopWindow || w.hidden || w.opacity === 0) continue;
    if (!(w.normalWindow || w.dialog || w.dock || w.utility || w.splash)) continue;
    if (!onDesk(w) || !onActivity(w)) continue;
    const g = w.frameGeometry || w.geometry;
    out.push({x: g.x, y: g.y, w: g.width, h: g.height, title: String(w.caption || ""), active: w === act});
}
callDBus("%SERVICE%", "/XCaptureWindows", "io.github.xcapture.Windows", "windows",
         JSON.stringify({vs: {x: vs.x, y: vs.y, w: vs.width, h: vs.height}, windows: out}));
"""

try:
    from PyQt6.QtCore import pyqtClassInfo

    @pyqtClassInfo("D-Bus Interface", "io.github.xcapture.Windows")
    class _WindowsReceiver(QObject):
        received = pyqtSignal(str)

        @pyqtSlot(str)
        def windows(self, data):
            self.received.emit(data)
except ImportError:  # pragma: no cover
    _WindowsReceiver = None

_receiver = None


def windows(timeout=1500):
    """Cửa sổ trên desktop hiện tại, toạ độ logic của Wayland, từ trên xuống.

    Trả về (QRect vùng desktop ảo, [(QRect, tiêu đề, đang hoạt động)]) hoặc None."""
    global _receiver
    if not kwin_available() or _WindowsReceiver is None:
        return None
    b = D.bus()
    if _receiver is None:
        _receiver = _WindowsReceiver()
        if not b.registerObject("/XCaptureWindows", _receiver, D.QDBusConnection.RegisterOption.ExportAllSlots):
            _receiver = None
            return None
    result = []
    loop = QEventLoop()

    def got(data):
        result.append(data)
        loop.quit()

    _receiver.received.connect(got)
    name = f"x-capture-windows-{os.getpid()}"
    fd, path = tempfile.mkstemp(prefix="x-capture-", suffix=".js")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(WINDOWS_JS.replace("%SERVICE%", b.baseService()))
        try:
            D.call(KWIN, "/Scripting", "org.kde.kwin.Scripting", "unloadScript", name)
            sid = D.call(KWIN, "/Scripting", "org.kde.kwin.Scripting", "loadScript", path, name)[0]
            # Plasma 6: /Scripting/ScriptN ; Plasma 5: /ScriptN
            for p in (f"/Scripting/Script{sid}", f"/{sid}", f"/Script{sid}"):
                try:
                    D.call(KWIN, p, "org.kde.kwin.Script", "run")
                    break
                except D.DBusError:
                    continue
            QTimer.singleShot(timeout, loop.quit)
            if not result:
                loop.exec()
        except D.DBusError:
            return None
        finally:
            try:
                D.call(KWIN, "/Scripting", "org.kde.kwin.Scripting", "unloadScript", name)
            except D.DBusError:
                pass
    finally:
        _receiver.received.disconnect(got)
        os.unlink(path)
    if not result:
        return None
    d = json.loads(result[0])
    vs = d["vs"]
    out = [(QRect(round(w["x"]), round(w["y"]), round(w["w"]), round(w["h"])), w["title"], w["active"])
           for w in reversed(d["windows"])]
    return QRect(vs["x"], vs["y"], vs["w"], vs["h"]), out


# ---------- phím tắt toàn cục ----------
def key_code(seq):
    """'Ctrl+Print' -> mã phím Qt gộp (int) như kglobalaccel dùng, hoặc 0."""
    ks = QKeySequence(seq)
    return ks[0].toCombined() if ks.count() else 0


class KGlobalAccelHotkeys(QObject):
    """Cùng giao diện với hotkeys.HotkeyManager nhưng đăng ký phím với kglobalaccel (KWin bắt phím),
    nên chạy được trên Plasma Wayland. Phím tắt hiện trong Cài đặt hệ thống → Phím tắt → X-Capture."""
    triggered = pyqtSignal(str)
    status = pyqtSignal(dict)
    kind = "kde"

    def __init__(self, labels):
        super().__init__()
        self.labels = labels
        self.available = D.HAVE_QTDBUS and D.has_service(KGA)
        self.results = {}
        self.owners = {}   # hành động -> (actionId của chương trình đang giữ phím, mã phím)
        self._ids = {}
        self._connected = False

    def _aid(self, action):
        return [COMPONENT, action, "X-Capture", self.labels.get(action, action)]

    def _call(self, method, *args):
        return D.call(KGA, "/kglobalaccel", "org.kde.KGlobalAccel", method, *args)

    def owner(self, code):
        try:
            aid = self._call("action", code)[0]
        except D.DBusError:
            return None
        return list(aid) if aid and len(aid) >= 2 and aid[0] else None

    def set_bindings(self, mapping):
        QTimer.singleShot(0, lambda: self._apply(dict(mapping)))

    def _apply(self, mapping):
        results, owners = {}, {}
        try:
            for action in mapping:
                aid = self._aid(action)
                self._call("doRegister", D.strings(aid))
                self._ids[action] = aid
            # gỡ phím cũ trước để đổi chỗ phím giữa các hành động của X-Capture không bị coi là trùng
            for action in mapping:
                self._call("setShortcut", D.strings(self._ids[action]), D.ints([]), D.uint(SET_FLAGS))
            for action, seq in mapping.items():
                if not seq:
                    continue
                code = key_code(seq)
                if not code:
                    results[action] = False
                    continue
                own = self.owner(code)
                if own and own[0] != COMPONENT:
                    # kglobalaccel không báo lỗi khi trùng mà lặng lẽ không gán: tự kiểm tra trước
                    results[action] = False
                    owners[action] = (own, code)
                    continue
                self._call("setShortcut", D.strings(self._ids[action]), D.ints([code]), D.uint(SET_FLAGS))
                results[action] = True
            self._connect()
        except D.DBusError:
            self.available = False
            results = {a: False for a, s in mapping.items() if s}
        self.results, self.owners = results, owners
        self.status.emit(results)

    def _connect(self):
        if self._connected:
            return
        try:
            path = self._call("getComponent", COMPONENT)[0]
        except D.DBusError:
            return
        path = path.path() if hasattr(path, "path") else str(path)
        self._connected = D.bus().connect(KGA, path, "org.kde.kglobalaccel.Component",
                                          "globalShortcutPressed", self._pressed)

    @pyqtSlot(str, str, "qlonglong")
    def _pressed(self, component, action, _ts):
        if component == COMPONENT:
            self.triggered.emit(action)

    def shutdown(self):
        """Báo kglobalaccel thôi bắt phím khi X-Capture thoát (phím trở lại bình thường)."""
        for aid in self._ids.values():
            try:
                self._call("setInactive", D.strings(aid))
            except D.DBusError:
                pass

    # ---------- nhường phím từ chương trình khác (vd. Spectacle giữ Print) ----------
    def conflicts(self):
        """{hành động: 'Spectacle: Launch Spectacle'} cho các phím đang bị chương trình khác giữ."""
        out = {}
        for action, (own, _code) in self.owners.items():
            friendly = own[2] if len(own) > 2 and own[2] else own[0]
            label = own[3] if len(own) > 3 and own[3] else own[1]
            out[action] = f"{friendly}: {label}"
        return out

    def release(self):
        """Gỡ các phím trùng khỏi chương trình đang giữ. Trả về bản sao lưu (để khôi phục)."""
        backup = []
        for _action, (own, code) in self.owners.items():
            aid = (own + ["", "", "", ""])[:4]
            try:
                keys = [int(k) for k in self._call("shortcut", D.strings(aid))[0]]
            except D.DBusError:
                continue
            if all(b["id"] != aid for b in backup):
                backup.append({"id": aid, "keys": keys})
            self._call("setForeignShortcut", D.strings(aid), D.ints([k for k in keys if k != code]))
        return backup

    def restore(self, backup):
        # trả phím lại: X-Capture phải nhả trước, nếu không kglobalaccel coi phím đang bận
        for aid in self._ids.values():
            try:
                self._call("setShortcut", D.strings(aid), D.ints([]), D.uint(SET_FLAGS))
            except D.DBusError:
                pass
        for item in backup:
            try:
                self._call("setForeignShortcut", D.strings(item["id"]), D.ints(item["keys"]))
            except D.DBusError:
                pass
