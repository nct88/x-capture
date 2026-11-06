"""`x-capture --cleanup` (bộ gỡ cài gọi): trả lại phím tắt KDE / XFCE đã nhường cho X-Capture
và gỡ các phím tắt của X-Capture khỏi KDE."""
import json
import shutil
import subprocess
import sys

from PyQt6.QtCore import QCoreApplication

from .config import ACTION_LABELS, HOTKEY_ACTIONS, config


def main():
    app = QCoreApplication(sys.argv[:1])  # noqa: F841 — QtDBus cần có ứng dụng Qt
    from . import dbusutil
    if dbusutil.HAVE_QTDBUS and dbusutil.has_service("org.kde.kglobalaccel"):
        from . import kde
        hk = kde.KGlobalAccelHotkeys(ACTION_LABELS)
        hk._ids = {a: hk._aid(a) for a, _ in HOTKEY_ACTIONS}
        try:
            hk.restore(json.loads(config.get("kde/backup") or "[]"))
        except ValueError:
            pass
        config.set("kde/backup", "")
        for action, _ in HOTKEY_ACTIONS:
            try:
                dbusutil.call(kde.KGA, "/kglobalaccel", "org.kde.KGlobalAccel", "unregister", kde.COMPONENT, action)
            except dbusutil.DBusError:
                pass
    backup = config.get("xfce/backup")
    if backup and shutil.which("xfconf-query"):
        for line in backup.splitlines():
            if "\t" in line:
                prop, val = line.split("\t", 1)
                subprocess.run(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", prop, "-n", "-t", "string",
                                "-s", val], timeout=5)
        config.set("xfce/backup", "")
    try:
        from . import desktop_keys
        desktop_keys.unbind_all()
        desktop_keys.restore_gnome_print(
            json.loads(config.get("gnome/backup") or "{}"))
    except Exception:
        pass
    config.set("gnome/backup", "")
    config.sync()
    return 0
