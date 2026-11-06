"""Cấu hình người dùng lưu tại ~/.config/x-capture/x-capture.ini."""
import os

from PyQt6.QtCore import QSettings, QStandardPaths

from .version import VERSION  # noqa: F401  (config.VERSION vẫn dùng được)

APP_NAME = "x-capture"
APP_TITLE = "X-Capture"

# (hành động, phím tắt mặc định) — theo bố cục phím tắt mặc định của FastStone Capture.
HOTKEY_ACTIONS = [
    ("active", "Alt+Print"),
    ("window", "Shift+Print"),
    ("rect", "Ctrl+Print"),
    ("freehand", "Ctrl+Shift+Print"),
    ("fullscreen", "Print"),
    ("scroll", "Ctrl+Alt+Print"),
    ("fixed", "Ctrl+Shift+Alt+Print"),
    ("repeat", "Meta+Print"),
    ("record", ""),
    ("color", ""),
    ("ocr", ""),
]

ACTION_LABELS = {
    "active": "Capture Active Window",
    "window": "Capture Window / Object",
    "rect": "Capture Rectangular Region",
    "freehand": "Capture Freehand Region",
    "fullscreen": "Capture Full Screen",
    "scroll": "Capture Scrolling Window",
    "fixed": "Capture Fixed-Size Region",
    "repeat": "Repeat Last Capture",
    "record": "Screen Recorder",
    "color": "Screen Color Picker",
    "ocr": "Capture Text (OCR)",
}


def pictures_dir():
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return os.path.join(base or os.path.expanduser("~"), "x-capture")


DEFAULTS = {
    "general/language": "vi",
    "general/show_panel": True,
    # khi bấm × trên thanh công cụ chụp: "tray" (chạy ẩn ở khay), "exit" (thoát) hoặc "ask" (hỏi)
    "general/close_action": "tray",
    "general/autostart": False,
    "general/first_run": True,
    "panel/x": -1,
    "panel/y": -1,
    "capture/delay": 0,
    "capture/hide_editor": True,
    "capture/fixed_w": 800,
    "capture/fixed_h": 600,
    "capture/scroll_clicks": 3,
    "capture/scroll_max": 20000,
    "capture/magnifier": True,
    "output/destination": "editor",
    "output/copy_clipboard": False,
    "output/auto_save": False,
    "output/folder": "",
    "output/pattern": "Screenshot_{date}_{time}",
    "output/format": "png",
    "output/jpeg_quality": 90,
    "editor/external": "gimp %f",
    "editor/color": "#e53935",
    "editor/width": 3,
    "editor/font": "Sans,14",
    "editor/shadow": True,
    "editor/fill": False,
    "editor/geometry": None,
    "record/fps": 25,
    "record/audio": False,
    "auto/interval": 10,
    "xfce/backup": "",
    "kde/backup": "",
    "gnome/backup": "",
}
for _a, _k in HOTKEY_ACTIONS:
    DEFAULTS["hotkeys/" + _a] = _k


class Config:
    def __init__(self):
        self.s = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, APP_NAME, APP_NAME)

    def get(self, key):
        default = DEFAULTS.get(key)
        if default is None:
            return self.s.value(key)
        val = self.s.value(key, default)
        t = type(default)
        if t is bool:
            return val if isinstance(val, bool) else str(val).lower() in ("1", "true", "yes")
        try:
            return t(val)
        except (TypeError, ValueError):
            return default

    def set(self, key, value):
        self.s.setValue(key, value)

    def sync(self):
        self.s.sync()

    def output_folder(self):
        folder = self.get("output/folder") or pictures_dir()
        os.makedirs(folder, exist_ok=True)
        return folder

    def hotkeys(self):
        return {a: self.get("hotkeys/" + a) for a, _ in HOTKEY_ACTIONS}


config = Config()
