"""Bộ điều khiển chính: khay hệ thống, phím tắt, quy trình chụp và nơi xuất ảnh."""
import os
import shutil
import subprocess
import sys

from PyQt6.QtCore import QObject, QRect, QSize, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import QApplication, QCheckBox, QMenu, QMessageBox, QSystemTrayIcon

from . import i18n, icons, imageops, session, tools, xapp_report
from .config import ACTION_LABELS, APP_TITLE, VERSION, config
from .grabber import X11Info, create_backend
from .hotkeys import create_hotkeys
from .i18n import tr
from .overlay import SelectionOverlay
from .panel import CapturePanel

CAPTURE_MENU = ["active", "window", "rect", "freehand", "fullscreen", "scroll", "fixed", None, "repeat", None,
                "record", "ocr"]
ICON_FOR = {"repeat": "rect", "fullscreen": "fullscreen", "ocr": "ocr", "color": "color"}
COMMANDS = {"--active": "active", "--window": "window", "--rect": "rect", "--region": "rect",
            "--freehand": "freehand", "--fullscreen": "fullscreen", "--full": "fullscreen", "--scroll": "scroll",
            "--fixed": "fixed", "--repeat": "repeat", "--record": "record", "--color": "color", "--ocr": "ocr"}


class XCaptureApp(QObject):
    def __init__(self, qapp, exe):
        super().__init__()
        self.qapp = qapp
        self.exe = exe
        self.x11 = X11Info()
        self.screen = create_backend(self.x11)
        self.hotkeys = create_hotkeys({a: tr(l) for a, l in ACTION_LABELS.items()})
        self.hotkeys.triggered.connect(self.on_hotkey)
        self.hotkeys.status.connect(self._hotkey_status)
        self._warned_keys = False
        self.editor = None
        self.busy = False
        self._hidden = []
        self.last_mode = None
        self.last_rect = None
        self.counter = 0
        self.keep = []  # giữ tham chiếu tới cửa sổ phụ
        self.recorder = None
        self.overlay = None
        self._tray_hint = False  # đã báo "vẫn chạy ở khay" trong phiên này chưa
        self.quitting = False
        self.auto_timer = QTimer(self, timeout=self._auto_capture)
        self.panel = CapturePanel(self)
        self._build_tray()
        self.apply_hotkeys()

    # ---------- khung ----------
    def exe_path(self):
        return self.exe

    def get_editor(self):
        if self.editor is None:
            from .editor import EditorWindow
            self.editor = EditorWindow(self)
        return self.editor

    def _build_tray(self):
        self.tray = QSystemTrayIcon(icons.icon("app"), self)
        self._tray_tooltip()
        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(self._fill_tray)
        self._fill_tray()
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_tooltip(self):
        self.tray.setToolTip(f"{APP_TITLE} — {tr('Screen capture')}")

    @staticmethod
    def tray_available():
        return QSystemTrayIcon.isSystemTrayAvailable()

    def _fill_tray(self):
        m = self.tray_menu
        m.clear()
        self.fill_capture_menu(m)
        m.addSeparator()
        self.fill_main_menu(m, tray=True)

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.panel.isVisible():
                self.panel.hide()
            else:
                self.panel.show_panel()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.capture("rect")

    def _label(self, action):
        key = config.get("hotkeys/" + action)
        return tr(ACTION_LABELS[action]) + (f"\t{key}" if key else "")

    def dynamic_capture_menu(self, menu):
        """Menu chụp tự làm mới (phím tắt / trạng thái quay phim) mỗi lần mở."""
        self.fill_capture_menu(menu)
        menu.aboutToShow.connect(lambda: (menu.clear(), self.fill_capture_menu(menu)))

    def fill_capture_menu(self, menu):
        for a in CAPTURE_MENU:
            if a is None:
                menu.addSeparator()
                continue
            label = self._label(a)
            if a == "record" and self.recorder:
                label = tr("Stop Recording")
            menu.addAction(icons.icon(ICON_FOR.get(a, a)), label, lambda act=a: self.capture(act))
        menu.addSeparator()
        d = menu.addMenu(icons.icon("delay"), tr("Delay Before Capture"))
        cur = config.get("capture/delay")
        for s in (0, 1, 2, 3, 5, 10):
            act = d.addAction(tr("No delay") if s == 0 else f"{s} s")
            act.setCheckable(True)
            act.setChecked(s == cur)
            act.triggered.connect(lambda _=False, v=s: config.set("capture/delay", v))

    def fill_tools_menu(self, menu):
        menu.addAction(icons.icon("color"), self._label("color"), lambda: self.capture("color"))
        menu.addAction(icons.icon("magnifier"), tr("Screen Magnifier"), self.magnifier)
        menu.addAction(icons.icon("ruler"), tr("Screen Ruler"), self.ruler)
        menu.addAction(icons.icon("ocr"), self._label("ocr"), lambda: self.capture("ocr"))
        act = menu.addAction(icons.icon("auto"), tr("Auto Capture (every %d s)") % config.get("auto/interval"))
        act.setCheckable(True)
        act.setChecked(self.auto_timer.isActive())
        act.toggled.connect(self.toggle_auto)
        menu.addAction(icons.icon("pin"), tr("Close All Pinned Images"), tools.PinWindow.close_all)
        menu.addSeparator()
        menu.addAction(icons.icon("settings"), tr("Settings..."), self.settings)

    def fill_main_menu(self, m, tray=False):
        m.addAction(icons.icon("editor"), tr("Open Editor"), self.show_editor)
        m.addAction(icons.icon("open"), tr("Open Image..."), lambda: (self.show_editor(), self.editor.open_files()))
        m.addAction(icons.icon("paste"), tr("Paste Image from Clipboard"), self.paste_to_editor)
        m.addAction(icons.icon("folder"), tr("Open Save Folder"),
                    lambda: subprocess.Popen(["xdg-open", config.output_folder()], start_new_session=True))
        m.addSeparator()
        t = m.addMenu(icons.icon("magnifier"), tr("Screen Tools"))
        self.fill_tools_menu(t)
        if tray:
            if self.panel.isVisible():
                m.addAction(icons.icon("app"), tr("Hide Capture Panel"), self.panel.hide)
            else:
                m.addAction(icons.icon("app"), tr("Show Capture Panel"), self.panel.show_panel)
            m.addAction(icons.icon("settings"), tr("Settings..."), self.settings)
        else:
            m.addAction(icons.icon("settings"), tr("Settings..."), self.settings)
        m.addSeparator()
        m.addAction(icons.icon("report"), tr("Report a Problem / Feedback..."), self.report_problem)
        m.addAction(icons.icon("app"), tr("About X-Capture"), self.about)
        m.addAction(icons.icon("close"), tr("Exit"), self.quit)

    def notify(self, msg, secs=3):
        if self.tray.isVisible() and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(APP_TITLE, msg, icons.icon("app"), secs * 1000)

    # ---------- đóng thanh công cụ ----------
    def close_panel(self):
        """Nút × / Alt+F4 trên thanh công cụ chụp: chạy ẩn ở khay hoặc thoát, theo cài đặt."""
        action = config.get("general/close_action")
        if action == "ask":
            action = self._ask_close_action()
            if action is None:
                return
        if action == "exit":
            self.quit()
            return
        if not self.tray_available():
            # không có khay thì ẩn đi là mất luôn đường quay lại ứng dụng
            r = QMessageBox.question(self.panel, APP_TITLE,
                                     tr("No system tray was found, so X-Capture cannot keep running hidden.")
                                     + "\n\n" + tr("Exit X-Capture now?"))
            if r == QMessageBox.StandardButton.Yes:
                self.quit()
            return
        self.panel.hide()
        if not self._tray_hint:
            self._tray_hint = True
            self.notify(tr("X-Capture is still running in the system tray.") + "\n" +
                        tr("Click the tray icon to show the panel again."))

    def _ask_close_action(self):
        box = QMessageBox(QMessageBox.Icon.Question, tr("Close the Capture Panel"),
                          tr("What do you want to do?"), QMessageBox.StandardButton.NoButton, self.panel)
        tray = box.addButton(tr("Run in Tray"), QMessageBox.ButtonRole.AcceptRole)
        ex = box.addButton(tr("Exit"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(tray)
        remember = QCheckBox(tr("Remember my choice"))
        box.setCheckBox(remember)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (tray, ex):
            return None
        action = "tray" if clicked is tray else "exit"
        if remember.isChecked():
            config.set("general/close_action", action)
            self.panel.refresh()
        return action

    # ---------- phím tắt ----------
    def apply_hotkeys(self, delay=0):
        QTimer.singleShot(delay, lambda: self.hotkeys.set_bindings(config.hotkeys()))

    def _hotkey_status(self, results):
        failed = [a for a, ok in results.items() if not ok]
        if failed and not self._warned_keys:
            self._warned_keys = True
            keys = ", ".join(config.get("hotkeys/" + a) for a in failed)
            self.notify(tr("Some hotkeys are used by another program:") + f" {keys}\n" +
                        tr("Open Settings → Hotkeys to fix this."), 6)

    def on_hotkey(self, action):
        self.capture(action)

    # ---------- quy trình chụp ----------
    def capture(self, mode):
        if mode == "record" and self.recorder:
            self.recorder.stop()
            return
        if self.busy:
            return
        if mode == "record" and not self._record_supported():
            return
        if mode == "repeat":
            if not self.last_mode:
                mode = "rect"
            elif self.last_mode not in ("rect", "fixed") or not self.last_rect:
                mode = self.last_mode
        self.busy = True
        self._hidden = []
        for w in (self.panel, self.editor if config.get("capture/hide_editor") else None):
            if w is not None and w.isVisible():
                w.hide()
                self._hidden.append(w)
        menus = False
        for m in QApplication.topLevelWidgets():
            if isinstance(m, QMenu) and m.isVisible():
                m.hide()
                menus = True
        delay = config.get("capture/delay")
        if delay > 0 and mode != "color":
            cd = tools.Countdown(delay)
            cd.done.connect(lambda: self._grab(mode))
            self._track(cd)
            cd.start()
        else:
            # chờ trình tổng hợp vẽ lại sau khi ẩn cửa sổ / menu
            QTimer.singleShot(280 if self._hidden else 180 if menus else 60, lambda: self._grab(mode))

    def grab_now(self, windows=True):
        return self.screen.grab(windows=windows)

    def _record_supported(self):
        """Quay phim: X11 dùng ffmpeg x11grab, wlroots dùng wf-recorder; KDE Wayland nhờ Spectacle."""
        if self.screen.name == "x11":
            if self._have("ffmpeg"):
                return True
            QMessageBox.information(None, APP_TITLE, tr("Screen recorder needs ffmpeg:") + "\n\n" +
                                    session.install_hint("ffmpeg"))
            return False
        if self.screen.name == "wlroots" and self._have("wf-recorder"):
            return True
        if self.screen.name == "kwin" and self._have("spectacle"):
            subprocess.Popen(["spectacle", "-R", "r"], start_new_session=True)
            return False
        QMessageBox.information(None, APP_TITLE, tr("Screen recording on Wayland needs wf-recorder (Sway, Hyprland) "
                                                    "or the recorder of your desktop (KDE: Spectacle)."))
        return False

    @staticmethod
    def _have(cmd):
        from shutil import which
        return which(cmd) is not None

    def _grab(self, mode):
        try:
            pm, vg, dpr = self.screen.grab()
        except Exception as ex:  # pragma: no cover
            self._restore()
            QMessageBox.warning(None, APP_TITLE, tr(str(ex)))
            return
        if mode == "fullscreen":
            self._restore()
            self.deliver(pm.toImage(), mode)
            return
        if mode == "repeat":
            rect, last = self.last_rect
            self._restore()
            self.deliver(pm.copy(rect).toImage(), last)
            return
        if mode == "active":
            r = self.screen.active_rect(pm, vg, dpr)
            self._restore()
            if r:
                r = r.intersected(pm.rect())
            self.deliver(pm.copy(r).toImage() if r and not r.isEmpty() else pm.toImage(), mode)
            return
        windows = []
        if mode in ("window", "rect", "scroll", "record", "ocr"):
            windows = self.screen.window_rects(pm, vg, dpr)
            for s in QApplication.screens():  # cả màn hình làm phương án cuối
                g = s.geometry()
                windows.append(QRect(round((g.x() - vg.x()) * dpr), round((g.y() - vg.y()) * dpr),
                                     round(g.width() * dpr), round(g.height() * dpr)))
        size = QSize(round(config.get("capture/fixed_w")), round(config.get("capture/fixed_h")))
        ov = SelectionOverlay(pm, vg, dpr, mode, windows, size, config.get("capture/magnifier"))
        ov.finished.connect(lambda res: self._selected(mode, pm, vg, dpr, res))
        ov.canceled.connect(self._restore)
        self.overlay = ov
        ov.start_overlay()

    def _selected(self, mode, pm, vg, dpr, res):
        self.overlay = None
        if mode == "color":
            self._restore()
            d = tools.ColorResult(res["color"])
            self._track(d)
            d.show()
            d.raise_()
            d.activateWindow()
            return
        rect = res["rect"]
        img = pm.copy(rect).toImage()
        if res.get("path") is not None:
            img = imageops.apply_mask(img, res["path"].translated(-rect.x(), -rect.y()))
        if mode in ("rect", "fixed"):
            self.last_rect = (rect, mode)
        if mode == "scroll":
            sc = tools.ScrollCapture(self, rect, dpr, vg)
            self.keep.append(sc)
            sc.start()
            return
        if mode == "record":
            rec = tools.Recorder(self, rect, dpr, vg)
            if rec.start():
                self.recorder = rec
            else:
                self._restore()
            return
        self._restore()
        if mode == "ocr":
            tools.run_ocr(img)
            return
        self.deliver(img, mode)

    def _restore(self):
        self.busy = False
        for w in self._hidden:
            w.show()
        self._hidden = []

    def scroll_done(self, sc, img):
        if sc in self.keep:
            self.keep.remove(sc)
        self._restore()
        if img is not None:
            self.deliver(img, "scroll")

    def record_done(self, rec, path, err):
        self.recorder = None
        self._restore()
        if os.path.exists(path) and os.path.getsize(path) > 0:
            self.notify(tr("Video saved:") + f" {path}", 5)
            subprocess.Popen(["xdg-open", os.path.dirname(path)], start_new_session=True)
        else:
            QMessageBox.warning(None, APP_TITLE, tr("Recording failed.") + (f"\n\n{err}" if err else ""))

    def deliver(self, img, mode):
        self.last_mode = mode
        dest = config.get("output/destination")
        saved = None
        if config.get("output/copy_clipboard") or dest == "clipboard":
            QApplication.clipboard().setImage(img)
        if config.get("output/auto_save") or dest == "file":
            saved = imageops.auto_filename(config, mode)
            if not imageops.save_image(img, saved, config.get("output/jpeg_quality")):
                saved = None
        if dest == "editor":
            self.counter += 1
            ed = self.get_editor()
            ed.add_image(img, title=None if saved else f"{tr('Capture')} {self.counter}", path=saved)
            if saved:
                ed.cv.undo.setClean()
            ed.show_editor()
        elif dest == "pin":
            self.pin(img)
        elif dest == "clipboard":
            self.notify(tr("Screenshot copied to clipboard") + f" ({img.width()}×{img.height()})")
        elif dest == "file":
            self.notify(tr("Saved") + f": {saved}" if saved else tr("Could not save the file:"))

    def set_destination(self, key):
        config.set("output/destination", key)
        self.panel.refresh()

    # ---------- công cụ ----------
    def show_editor(self):
        self.get_editor().show_editor()

    def open_in_editor(self, img, title=None):
        ed = self.get_editor()
        ed.add_image(img, title or tr("Pinned image"))
        ed.show_editor()

    def paste_to_editor(self):
        ed = self.get_editor()
        ed.show_editor()
        ed.paste_new()

    def pin(self, img):
        w = tools.PinWindow(self, img)
        w.show()
        w.raise_()

    def run_ocr(self, img):
        tools.run_ocr(img, self.editor)

    def _track(self, w):
        """Giữ tham chiếu Python tới cửa sổ phụ (tự xoá khi cửa sổ bị huỷ)."""
        self.keep.append(w)
        w.destroyed.connect(lambda: self.keep.remove(w) if w in self.keep else None)
        return w

    def magnifier(self):
        if not self.screen.live:
            # Wayland không cho đọc màn hình liên tục: phóng to trên ảnh tĩnh vừa chụp
            self.capture("magnify")
            return
        self._track(tools.Magnifier(self.x11)).start()

    def ruler(self):
        self._track(tools.Ruler()).show()

    def toggle_auto(self, on):
        if on:
            self.auto_timer.start(config.get("auto/interval") * 1000)
            self.notify(tr("Auto capture started. Images are saved to:") + f" {config.output_folder()}")
        else:
            self.auto_timer.stop()
            self.notify(tr("Auto capture stopped."))

    def _auto_capture(self):
        try:
            pm, _, _ = self.screen.grab(windows=False)
        except Exception:
            return
        imageops.save_image(pm.toImage(), imageops.auto_filename(config, "auto"), config.get("output/jpeg_quality"))

    def settings(self):
        from .settings_dialog import SettingsDialog
        d = SettingsDialog(self, self.editor if self.editor and self.editor.isVisible() else None)
        d.setWindowIcon(icons.icon("settings"))
        d.exec()

    def settings_changed(self):
        i18n.set_language(config.get("general/language"))
        self._tray_tooltip()
        self.apply_hotkeys()
        self.panel.refresh()
        if self.auto_timer.isActive():
            self.auto_timer.setInterval(config.get("auto/interval") * 1000)

    def report_problem(self):
        # Mở form Báo lỗi trên nct88.dev, điền sẵn phiên bản, distro, desktop, X11/Wayland;
        # không gửi gì tự động.
        url = xapp_report.report_url("x-capture", VERSION)
        if not QDesktopServices.openUrl(QUrl(url)) and not xapp_report.open_url(url):
            QMessageBox.information(None, tr("Report a Problem / Feedback"),
                                    f"{tr('Could not open a web browser. Open this address:')}<br>"
                                    f"<a href='{url}'>{url}</a>")

    def about(self):
        QMessageBox.about(None, tr("About X-Capture"),
                          f"<h3>{APP_TITLE} {VERSION}</h3>"
                          f"<p>{tr('Lightweight screen capture and annotation tool for Linux (X11), inspired by FastStone Capture.')}</p>"
                          f"<p>{tr('Config file:')} <code>{config.s.fileName()}</code><br>"
                          f"{tr('Save folder:')} <code>{config.output_folder()}</code></p>")

    def quit(self):
        if self.recorder:
            self.recorder.stop()
        if self.editor and self.editor.isVisible() and not self.editor.close():
            return
        if self.editor:
            while self.editor.tabs.count():
                if not self.editor.close_tab(self.editor.tabs.count() - 1):
                    return
        config.sync()
        self.hotkeys.shutdown()
        self.quitting = True
        self.tray.hide()
        self.qapp.quit()

    # ---------- dòng lệnh / phiên bản đang chạy ----------
    def handle_args(self, args, startup=False):
        files = [a for a in args if not a.startswith("-")]
        flags = [a for a in args if a.startswith("-")]
        for f in flags:
            if f in COMMANDS:
                QTimer.singleShot(300 if startup else 0, lambda m=COMMANDS[f]: self.capture(m))
            elif f == "--editor":
                self.show_editor()
            elif f == "--settings":
                QTimer.singleShot(0, self.settings)
            elif f == "--panel":
                self.panel.show_panel()
            elif f == "--tray" and not startup:
                self.panel.hide()
            elif f == "--quit":
                QTimer.singleShot(0, self.quit)
        for f in files:
            self.get_editor().open_path(f)
        if not args and not startup:
            self.panel.show_panel()


def run(args, sock_path, exe):
    restore_env = session.prepare_qt_platform()
    qapp = QApplication(sys.argv[:1])
    restore_env()
    qapp.setApplicationName("x-capture")
    qapp.setApplicationDisplayName(APP_TITLE)
    qapp.setDesktopFileName("x-capture")
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(icons.icon("app"))
    i18n.set_language(config.get("general/language"))
    app = XCaptureApp(qapp, exe)

    server = QLocalServer()
    QLocalServer.removeServer(sock_path)
    if not server.listen(sock_path):
        print(f"x-capture: cannot listen on {sock_path}: {server.errorString()}", file=sys.stderr)

    def on_conn():
        conn = server.nextPendingConnection()
        buf = bytearray()

        def read():
            buf.extend(bytes(conn.readAll()))

        def done():
            read()
            app.handle_args([a for a in buf.decode("utf-8", "replace").split("\n") if a])
            conn.deleteLater()

        conn.readyRead.connect(read)
        conn.disconnected.connect(done)

    server.newConnection.connect(on_conn)
    app.server = server

    quiet = "--tray" in args or any(a in COMMANDS for a in args)
    if config.get("general/show_panel") and not quiet:
        app.panel.show()
    app.handle_args(args, startup=True)

    def no_tray_fallback():
        # chạy ẩn nhưng không có khay hệ thống (sau khi chờ khay của phiên đăng nhập khởi động)
        # → hiện thanh công cụ để người dùng vẫn điều khiển được
        if not app.tray_available() and not any(w.isVisible() for w in QApplication.topLevelWidgets()):
            app.panel.show_panel()

    QTimer.singleShot(8000, no_tray_fallback)
    qapp.aboutToQuit.connect(lambda: app.editor and app.editor.shutdown())
    if config.get("general/first_run"):
        config.set("general/first_run", False)
        QTimer.singleShot(1500, lambda: app.notify(
            tr("X-Capture is running. Use Print-key hotkeys or the Capture Panel."), 6))
    code = qapp.exec()
    server.close()
    return code
