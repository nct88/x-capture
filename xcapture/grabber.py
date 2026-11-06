"""Chụp ảnh màn hình (mọi màn hình): X11 trực tiếp, Wayland qua KWin / grim / portal; danh sách cửa sổ."""
import json
import os
import shutil
import subprocess
import tempfile

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap

try:
    from Xlib import X, display as xdisplay
    HAVE_XLIB = True
except ImportError:  # pragma: no cover
    HAVE_XLIB = False


def virtual_geometry():
    rect = QRect()
    for s in QGuiApplication.screens():
        rect = rect.united(s.geometry())
    return rect


def device_ratio():
    return max((s.devicePixelRatio() for s in QGuiApplication.screens()), default=1.0)


def _composite_docks(pm, vg, dpr):
    """XGetImage của cửa sổ root không chứa cửa sổ ARGB (Plank) khi bộ tổng hợp
    đang bật, nên ảnh chụp mất thanh dock. Vẽ lại các cửa sổ kiểu DOCK, giữ alpha."""
    if not HAVE_XLIB or pm.isNull():
        return
    try:
        d = xdisplay.Display()
        root = d.screen().root
        dock_type = d.intern_atom("_NET_WM_WINDOW_TYPE_DOCK")
        prop = root.get_full_property(d.intern_atom("_NET_CLIENT_LIST_STACKING"), X.AnyPropertyType)
        wids = list(prop.value) if prop else []
    except Exception:
        return
    screen = QGuiApplication.primaryScreen()
    if screen is None or not wids:
        return
    p = QPainter(pm)
    for wid in wids:
        try:
            w = d.create_resource_object("window", wid)
            if w.get_attributes().map_state != X.IsViewable:
                continue
            types = w.get_full_property(d.intern_atom("_NET_WM_WINDOW_TYPE"), X.AnyPropertyType)
            if not types or dock_type not in list(types.value):
                continue
            pos = root.translate_coords(w, 0, 0)
            shot = screen.grabWindow(int(wid))
            if shot.isNull():
                continue
            shot.setDevicePixelRatio(1.0)
            p.drawPixmap(round((pos.x - vg.x()) * dpr), round((pos.y - vg.y()) * dpr), shot)
        except Exception:
            continue
    p.end()


def grab_screen():
    """Trả về (QPixmap toàn bộ desktop ảo theo pixel thiết bị, hình học ảo logic, dpr)."""
    vg = virtual_geometry()
    dpr = device_ratio()
    pm = QPixmap(round(vg.width() * dpr), round(vg.height() * dpr))
    pm.fill(QColor(0, 0, 0))
    p = QPainter(pm)
    for s in QGuiApplication.screens():
        g = s.geometry()
        shot = s.grabWindow(0)
        target = QRect(round((g.x() - vg.x()) * dpr), round((g.y() - vg.y()) * dpr),
                       round(g.width() * dpr), round(g.height() * dpr))
        shot.setDevicePixelRatio(1.0)
        p.drawPixmap(target, shot)
    p.end()
    _composite_docks(pm, vg, dpr)
    return pm, vg, dpr


class X11Info:
    """Liệt kê cửa sổ (để bắt dính khi chọn vùng) và cửa sổ đang hoạt động."""

    def __init__(self):
        self.d = None
        if HAVE_XLIB:
            try:
                self.d = xdisplay.Display()
                self.root = self.d.screen().root
                self._atoms = {}
            except Exception:
                self.d = None

    def atom(self, name):
        if name not in self._atoms:
            self._atoms[name] = self.d.intern_atom(name)
        return self._atoms[name]

    def _prop(self, win, name, ptype=X.AnyPropertyType if HAVE_XLIB else 0):
        try:
            p = win.get_full_property(self.atom(name), ptype)
            return p.value if p else None
        except Exception:
            return None

    def _frame(self, win):
        """Cửa sổ khung (gồm viền trang trí) là tổ tiên trực tiếp của root."""
        try:
            cur = win
            while True:
                tree = cur.query_tree()
                if tree.parent == 0 or tree.parent.id == self.root.id:
                    return cur
                cur = tree.parent
        except Exception:
            return win

    def _rect(self, win):
        """Hình chữ nhật của cửa sổ (toạ độ root, pixel thiết bị), trừ bóng CSD của GTK."""
        try:
            gtk = self._prop(win, "_GTK_FRAME_EXTENTS")
            target = win if gtk is not None and len(gtk) == 4 else self._frame(win)
            g = target.get_geometry()
            pos = self.root.translate_coords(target, 0, 0)
            r = QRect(pos.x, pos.y, g.width, g.height)
            if target is win and gtk is not None and len(gtk) == 4:
                l, rr, t, b = (int(v) for v in gtk)
                r.adjust(l, t, -rr, -b)
            return r
        except Exception:
            return None

    def _title(self, win):
        name = self._prop(win, "_NET_WM_NAME")
        if isinstance(name, bytes):
            return name.decode("utf-8", "replace")
        if name:
            return str(name)
        try:
            return win.get_wm_name() or ""
        except Exception:
            return ""

    def window_rects(self, exclude_ids=()):
        """Danh sách (QRect, tiêu đề) theo thứ tự từ trên xuống."""
        if not self.d:
            return []
        stack = self._prop(self.root, "_NET_CLIENT_LIST_STACKING") or []
        cur_desk = self._prop(self.root, "_NET_CURRENT_DESKTOP")
        cur_desk = cur_desk[0] if cur_desk is not None and len(cur_desk) else None
        hidden = self.atom("_NET_WM_STATE_HIDDEN")
        desktop_type = self.atom("_NET_WM_WINDOW_TYPE_DESKTOP")
        out = []
        for wid in reversed(list(stack)):
            if wid in exclude_ids:
                continue
            try:
                w = self.d.create_resource_object("window", wid)
                if w.get_attributes().map_state != X.IsViewable:
                    continue
                state = self._prop(w, "_NET_WM_STATE") or []
                if hidden in state:
                    continue
                types = self._prop(w, "_NET_WM_WINDOW_TYPE") or []
                if desktop_type in types:
                    continue
                desk = self._prop(w, "_NET_WM_DESKTOP")
                if desk is not None and len(desk) and cur_desk is not None \
                        and desk[0] not in (cur_desk, 0xFFFFFFFF):
                    continue
                r = self._rect(w)
                if r and r.width() > 1 and r.height() > 1:
                    out.append((r, self._title(w)))
            except Exception:
                continue
        return out

    def active_window_rect(self):
        if not self.d:
            return None
        act = self._prop(self.root, "_NET_ACTIVE_WINDOW")
        if not act or not act[0]:
            return None
        w = self.d.create_resource_object("window", act[0])
        types = self._prop(w, "_NET_WM_WINDOW_TYPE") or []
        if self.atom("_NET_WM_WINDOW_TYPE_DESKTOP") in types:
            return None
        return self._rect(w)

    def pointer_buttons(self):
        """Mặt nạ nút chuột hiện tại (để công cụ kính lúp biết khi người dùng bấm)."""
        if not self.d:
            return 0
        try:
            return self.root.query_pointer().mask
        except Exception:
            return 0

    def scroll(self, pos, clicks, down=True):
        """Giả lập lăn chuột qua XTest tại vị trí pos (pixel thiết bị)."""
        if not self.d:
            return False
        try:
            from Xlib.ext import xtest
            if pos is not None:
                self.root.warp_pointer(pos.x(), pos.y())
                self.d.sync()
            button = 5 if down else 4
            for _ in range(clicks):
                xtest.fake_input(self.d, X.ButtonPress, button)
                xtest.fake_input(self.d, X.ButtonRelease, button)
            self.d.sync()
            return True
        except Exception:
            return False


# ================= Cách chụp theo phiên làm việc =================
class X11Backend:
    """X11: chụp bằng Qt (XGetImage), cửa sổ và cuộn chuột qua Xlib."""
    name = "x11"
    live = True
    can_scroll = True

    def __init__(self, x11):
        self.x11 = x11

    def grab(self, windows=True):
        return grab_screen()

    def window_rects(self, pm, vg, dpr):
        off = QPoint(round(vg.x() * dpr), round(vg.y() * dpr))
        return [r.translated(-off) for r, _ in self.x11.window_rects()]

    def active_rect(self, pm, vg, dpr):
        r = self.x11.active_window_rect()
        return r.translated(-round(vg.x() * dpr), -round(vg.y() * dpr)) if r else None

    def scroll(self, pos, clicks, down=True):
        return self.x11.scroll(pos, clicks, down)


class WaylandBackend:
    """Wayland: ứng dụng không tự đọc được màn hình, phải xin trình tổng hợp một ảnh tĩnh.
    Cửa sổ X-Capture chạy qua XWayland nên toạ độ Qt khớp desktop; tỉ lệ ảnh/desktop tính từ kích thước ảnh."""
    name = "wayland"
    live = False

    @property
    def can_scroll(self):
        return shutil.which("ydotool") is not None

    def __init__(self, x11=None):
        self.x11 = x11
        self._wins = None  # (vùng desktop logic, [(QRect logic, tiêu đề, đang hoạt động)])

    def scroll(self, pos, clicks, down=True):
        return _ydotool_scroll(pos, clicks, down)

    def grab_image(self):
        raise NotImplementedError

    def list_windows(self):
        return None

    def grab(self, windows=True):
        img = self.grab_image()
        if img is None or img.isNull():
            raise RuntimeError("Could not capture the screen on Wayland.")
        if windows:
            try:
                self._wins = self.list_windows()
            except Exception:
                self._wins = None
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(1.0)
        vg = virtual_geometry()
        dpr = pm.width() / vg.width() if vg.width() > 0 else 1.0
        return pm, vg, dpr

    def _mapped(self, pm):
        if not self._wins:
            return []
        vs, wins = self._wins
        if vs.width() <= 0 or vs.height() <= 0:
            return []
        sx, sy = pm.width() / vs.width(), pm.height() / vs.height()
        out = []
        for r, _title, active in wins:
            out.append((QRect(round((r.x() - vs.x()) * sx), round((r.y() - vs.y()) * sy),
                              round(r.width() * sx), round(r.height() * sy)), active))
        return out

    def window_rects(self, pm, vg, dpr):
        return [r for r, _ in self._mapped(pm)]

    def active_rect(self, pm, vg, dpr):
        return next((r for r, active in self._mapped(pm) if active), None)


class KWinBackend(WaylandBackend):
    """KDE Plasma: KWin ScreenShot2 (≈0,1 s). Cần tệp .desktop có X-KDE-DBUS-Restricted-Interfaces
    trỏ đúng trình thông dịch của X-Capture (bộ cài tạo sẵn); nếu không, dùng spectacle (≈2 s) hoặc portal."""
    name = "kwin"

    def __init__(self, x11=None):
        super().__init__(x11)
        self.authorized = True

    def grab_image(self):
        from . import kde
        if self.authorized:
            try:
                return kde.screenshot()
            except kde.NotAuthorized:
                self.authorized = False
        if shutil.which("spectacle"):
            img = _run_tool_image(["spectacle", "-b", "-n", "-f", "-o"], suffix=".png")
            if img is not None:
                return img
        from . import portal
        return portal.screenshot() if portal.available() else None

    def list_windows(self):
        from . import kde
        return kde.windows()


class WlrootsBackend(WaylandBackend):
    """Sway / Hyprland...: grim (giao thức screencopy); cửa sổ lấy từ swaymsg / hyprctl."""
    name = "wlroots"

    def grab_image(self):
        try:
            data = subprocess.run(["grim", "-t", "ppm", "-"], capture_output=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        img = QImage.fromData(data, "PPM")
        return None if img.isNull() else img

    def list_windows(self):
        if shutil.which("hyprctl") and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            return _hyprland_windows()
        if shutil.which("swaymsg") and os.environ.get("SWAYSOCK"):
            return _sway_windows()
        return None


class PortalBackend(WaylandBackend):
    name = "portal"

    def grab_image(self):
        from . import portal
        return portal.screenshot()


def create_backend(x11):
    from . import session
    if not session.is_wayland():
        return X11Backend(x11)
    from . import dbusutil
    if dbusutil.HAVE_QTDBUS:
        from . import kde
        if session.is_kde() and kde.kwin_available():
            return KWinBackend(x11)
    grim = shutil.which("grim")
    if session.is_niri() and grim:
        return NiriBackend(x11)
    if grim and session.is_wlroots():
        return WlrootsBackend(x11)
    if dbusutil.HAVE_QTDBUS:
        from . import portal
        if portal.available():
            return PortalBackend(x11)
    if grim:
        return WlrootsBackend(x11)
    if os.environ.get("DISPLAY"):
        return X11Backend(x11)
    return PortalBackend(x11)


def _run_tool_image(cmd, suffix=".png"):
    """Chạy công cụ chụp ngoài ghi ra tệp tạm (đường dẫn nối vào cuối lệnh), đọc thành QImage."""
    # tệp đích chưa được tồn tại: spectacle không ghi đè tệp có sẵn mà đổi sang tên khác
    with tempfile.TemporaryDirectory(prefix="x-capture-") as tmp:
        path = os.path.join(tmp, "shot" + suffix)
        try:
            subprocess.run(cmd + [path], capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return None
        img = QImage(path)
        return None if img.isNull() else img


def _json(cmd):
    try:
        return json.loads(subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout or "null")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _union(rects):
    out = QRect()
    for r in rects:
        out = out.united(r)
    return out


def _hyprland_windows():
    mons = _json(["hyprctl", "-j", "monitors"]) or []
    clients = _json(["hyprctl", "-j", "clients"]) or []
    act = (_json(["hyprctl", "-j", "activewindow"]) or {}).get("address")
    shown = {m.get("activeWorkspace", {}).get("id") for m in mons}
    vs = _union(QRect(m["x"], m["y"], round(m["width"] / (m.get("scale") or 1)),
                      round(m["height"] / (m.get("scale") or 1))) for m in mons)
    wins = []
    # Hyprland liệt kê theo thứ tự tạo: cửa sổ nổi / đang hoạt động đưa lên đầu
    for c in sorted(clients, key=lambda c: (c.get("address") != act, not c.get("floating"))):
        if not c.get("mapped", True) or c.get("hidden") or c.get("workspace", {}).get("id") not in shown:
            continue
        (x, y), (w, h) = c["at"], c["size"]
        wins.append((QRect(x, y, w, h), c.get("title", ""), c.get("address") == act))
    return vs, wins


def _sway_windows():
    tree = _json(["swaymsg", "-t", "get_tree", "-r"])
    outs = _json(["swaymsg", "-t", "get_outputs", "-r"]) or []
    if not tree:
        return None
    vs = _union(QRect(o["rect"]["x"], o["rect"]["y"], o["rect"]["width"], o["rect"]["height"])
                for o in outs if o.get("active"))
    wins = []

    def walk(n, floating=False):
        for c in n.get("floating_nodes", []):
            walk(c, True)
        for c in n.get("nodes", []):
            walk(c, floating)
        if n.get("type") in ("con", "floating_con") and n.get("visible") and (n.get("pid") or n.get("app_id")):
            r, d = n["rect"], n.get("deco_rect") or {}
            rect = QRect(r["x"], r["y"] - d.get("height", 0), r["width"], r["height"] + d.get("height", 0))
            wins.append((rect, n.get("name") or "", bool(n.get("focused")), floating))

    walk(tree)
    wins.sort(key=lambda w: (not w[2], not w[3]))  # đang hoạt động, rồi cửa sổ nổi lên trước
    return vs, [w[:3] for w in wins]

class NiriBackend(WlrootsBackend):
    """niri: grim chụp màn hình; cửa sổ từ `niri msg -j windows`."""
    name = "niri"

    def list_windows(self):
        return _niri_windows()


def _niri_windows():
    outs = _json(["niri", "msg", "-j", "outputs"]) or []
    clients = _json(["niri", "msg", "-j", "windows"]) or []
    if not isinstance(outs, list):
        outs = []
    if not isinstance(clients, list):
        clients = []
    rects = []
    for o in outs:
        log = o.get("logical") or o
        x, y = log.get("x", 0), log.get("y", 0)
        w, h = log.get("width") or o.get("width") or 0, log.get("height") or o.get("height") or 0
        if w and h:
            rects.append(QRect(int(x), int(y), int(w), int(h)))
    vs = _union(rects) if rects else QRect()
    wins = []
    for c in clients:
        if c.get("is_minimized"):
            continue
        lay = c.get("layout") or {}
        pos = lay.get("tile_pos_in_workspace_view") or lay.get("pos_in_scrolling_layout")
        size = lay.get("window_size") or lay.get("tile_size")
        if not size:
            continue
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            x, y = pos[0], pos[1]
        else:
            x = y = 0
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            w, h = size[0], size[1]
        elif isinstance(size, dict):
            w, h = size.get("width", 0), size.get("height", 0)
        else:
            continue
        wins.append((QRect(int(x), int(y), int(w), int(h)),
                     c.get("title") or "", bool(c.get("is_focused"))))
    wins.sort(key=lambda w: (not w[2],))
    return vs, wins


def _ydotool_scroll(pos, clicks, down=True):
    if not shutil.which("ydotool"):
        return False
    try:
        if pos is not None:
            subprocess.run(["ydotool", "mousemove", "--absolute", str(int(pos.x())), str(int(pos.y()))],
                           capture_output=True, timeout=3)
        # Linux REL_WHEEL: ydotool 1.0 accepts "click" on buttons 4/5 like X11
        btn = "4" if not down else "5"
        for _ in range(max(1, clicks)):
            subprocess.run(["ydotool", "click", btn], capture_output=True, timeout=3)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
