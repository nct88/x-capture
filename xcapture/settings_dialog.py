"""Hộp thoại Cài đặt."""
import json
import os
import shutil
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                             QGridLayout, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QSpinBox, QSystemTrayIcon, QTabWidget, QToolButton,
                             QVBoxLayout, QWidget)

from . import icons, imageops, session
from .config import ACTION_LABELS, APP_NAME, DEFAULTS, HOTKEY_ACTIONS, config, pictures_dir
from .i18n import tr

XFCE_CHANNEL = "xfce4-keyboard-shortcuts"


def xfce_print_bindings():
    """Các phím tắt XFCE đang chiếm phím Print (thường là xfce4-screenshooter)."""
    if not shutil.which("xfconf-query"):
        return {}
    try:
        out = subprocess.run(["xfconf-query", "-c", XFCE_CHANNEL, "-l", "-v"], capture_output=True,
                             text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    res = {}
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].startswith("/commands/custom/") and parts[0].endswith("Print") \
                and APP_NAME not in parts[1]:
            res[parts[0]] = parts[1].strip()
    return res


def autostart_path():
    return os.path.expanduser("~/.config/autostart/x-capture.desktop")


def set_autostart(on, exe):
    path = autostart_path()
    if on:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=X-Capture\n"
                    f"Exec={exe} --tray\nIcon=x-capture\nX-GNOME-Autostart-enabled=true\n"
                    "Comment=Screen capture tool\n")
    elif os.path.exists(path):
        os.remove(path)


class SettingsDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(tr("X-Capture Settings"))
        self.setWindowIcon(icons.icon("settings"))
        self.resize(620, 520)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        tabs.addTab(self._general(), icons.icon("settings"), tr("General"))
        tabs.addTab(self._capture(), icons.icon("rect"), tr("Capture"))
        tabs.addTab(self._output(), icons.icon("save"), tr("Output"))
        tabs.addTab(self._hotkeys(), icons.icon("delay"), tr("Hotkeys"))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    # ---------- các thẻ ----------
    def _general(self):
        w = QWidget()
        f = QFormLayout(w)
        self.lang = QComboBox()
        self.lang.addItem("Tiếng Việt", "vi")
        self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(0 if config.get("general/language") == "vi" else 1)
        f.addRow(tr("Language:"), self.lang)
        self.show_panel = QCheckBox(tr("Show the Capture Panel at startup"))
        self.show_panel.setChecked(config.get("general/show_panel"))
        f.addRow(self.show_panel)
        self.close_action = QComboBox()
        for key, label in (("tray", "Keep running in the system tray"), ("exit", "Exit X-Capture"),
                           ("ask", "Ask every time")):
            self.close_action.addItem(tr(label), key)
        self.close_action.setCurrentIndex(max(0, self.close_action.findData(config.get("general/close_action"))))
        f.addRow(tr("When closing the Capture Panel:"), self.close_action)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            n = QLabel(tr("No system tray was found, so X-Capture cannot keep running hidden."))
            n.setStyleSheet("color:#b26a00")
            n.setWordWrap(True)
            f.addRow(n)
        self.autostart = QCheckBox(tr("Run X-Capture when I log in"))
        self.autostart.setChecked(os.path.exists(autostart_path()))
        f.addRow(self.autostart)
        self.ext = QLineEdit(config.get("editor/external"))
        self.ext.setPlaceholderText("gimp %f")
        f.addRow(tr("External editor (%f = file):"), self.ext)
        note = QLabel(tr("Changing the language takes full effect after restarting X-Capture."))
        note.setStyleSheet("color:#777")
        note.setWordWrap(True)
        f.addRow(note)
        return w

    def _capture(self):
        w = QWidget()
        f = QFormLayout(w)
        self.delay = QSpinBox()
        self.delay.setRange(0, 60)
        self.delay.setSuffix(" s")
        self.delay.setValue(config.get("capture/delay"))
        f.addRow(tr("Delay before capture:"), self.delay)
        self.hide_editor = QCheckBox(tr("Hide the Editor while capturing"))
        self.hide_editor.setChecked(config.get("capture/hide_editor"))
        f.addRow(self.hide_editor)
        self.magnifier = QCheckBox(tr("Show magnifier while selecting a region"))
        self.magnifier.setChecked(config.get("capture/magnifier"))
        f.addRow(self.magnifier)
        row = QHBoxLayout()
        self.fw, self.fh = QSpinBox(), QSpinBox()
        for s in (self.fw, self.fh):
            s.setRange(16, 10000)
        self.fw.setValue(config.get("capture/fixed_w"))
        self.fh.setValue(config.get("capture/fixed_h"))
        row.addWidget(self.fw)
        row.addWidget(QLabel("×"))
        row.addWidget(self.fh)
        row.addStretch()
        f.addRow(tr("Fixed region size:"), row)
        self.scroll_clicks = QSpinBox()
        self.scroll_clicks.setRange(1, 20)
        self.scroll_clicks.setValue(config.get("capture/scroll_clicks"))
        f.addRow(tr("Scrolling capture — wheel steps per scroll:"), self.scroll_clicks)
        self.scroll_max = QSpinBox()
        self.scroll_max.setRange(1000, 100000)
        self.scroll_max.setSingleStep(1000)
        self.scroll_max.setSuffix(" px")
        self.scroll_max.setValue(config.get("capture/scroll_max"))
        f.addRow(tr("Scrolling capture — maximum height:"), self.scroll_max)
        self.fps = QSpinBox()
        self.fps.setRange(5, 60)
        self.fps.setValue(config.get("record/fps"))
        f.addRow(tr("Screen recorder frame rate:"), self.fps)
        self.audio = QCheckBox(tr("Record audio (PulseAudio / PipeWire default source)"))
        self.audio.setChecked(config.get("record/audio"))
        f.addRow(self.audio)
        self.auto_int = QSpinBox()
        self.auto_int.setRange(1, 3600)
        self.auto_int.setSuffix(" s")
        self.auto_int.setValue(config.get("auto/interval"))
        f.addRow(tr("Auto capture interval:"), self.auto_int)
        if not shutil.which("ffmpeg"):
            n = QLabel(tr("Screen recorder needs ffmpeg:") + "  " + session.install_hint("ffmpeg"))
            n.setStyleSheet("color:#b26a00")
            f.addRow(n)
        return w

    def _output(self):
        w = QWidget()
        f = QFormLayout(w)
        self.dest = QComboBox()
        for key, label in (("editor", "To Editor"), ("clipboard", "To Clipboard"), ("file", "To File"),
                           ("pin", "Pin to Screen")):
            self.dest.addItem(tr(label), key)
        self.dest.setCurrentIndex(max(0, self.dest.findData(config.get("output/destination"))))
        f.addRow(tr("After capture:"), self.dest)
        self.copy_clip = QCheckBox(tr("Also copy to clipboard"))
        self.copy_clip.setChecked(config.get("output/copy_clipboard"))
        f.addRow(self.copy_clip)
        self.auto_save = QCheckBox(tr("Also auto-save to file"))
        self.auto_save.setChecked(config.get("output/auto_save"))
        f.addRow(self.auto_save)
        row = QHBoxLayout()
        self.folder = QLineEdit(config.get("output/folder") or pictures_dir())
        b = QToolButton()
        b.setIcon(icons.icon("open"))
        b.clicked.connect(self._pick_folder)
        row.addWidget(self.folder)
        row.addWidget(b)
        f.addRow(tr("Save folder:"), row)
        self.pattern = QLineEdit(config.get("output/pattern"))
        self.pattern.textChanged.connect(self._preview)
        f.addRow(tr("File name:"), self.pattern)
        self.preview = QLabel()
        self.preview.setStyleSheet("color:#777")
        f.addRow("", self.preview)
        f.addRow("", QLabel(tr("Tokens: {date} {time} {mode}")))
        self.fmt = QComboBox()
        for x in imageops.writable_formats():
            self.fmt.addItem(x.upper(), x)
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(config.get("output/format"))))
        self.fmt.currentIndexChanged.connect(self._preview)
        f.addRow(tr("Default format:"), self.fmt)
        self.quality = QSpinBox()
        self.quality.setRange(10, 100)
        self.quality.setValue(config.get("output/jpeg_quality"))
        f.addRow(tr("JPEG / WebP quality:"), self.quality)
        self._preview()
        return w

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("Save folder:"), self.folder.text())
        if d:
            self.folder.setText(d)

    def _preview(self):
        import datetime
        now = datetime.datetime.now()
        name = (self.pattern.text() or "Screenshot").replace("{date}", now.strftime("%Y-%m-%d")) \
            .replace("{time}", now.strftime("%H%M%S")).replace("{mode}", "rect")
        self.preview.setText(f"{name}.{self.fmt.currentData() or 'png'}")

    def _hotkeys(self):
        w = QWidget()
        v = QVBoxLayout(w)
        grid = QGridLayout()
        self.key_edits = {}
        self.key_status = {}
        status = self.app.hotkeys.results
        for row, (action, _) in enumerate(HOTKEY_ACTIONS):
            grid.addWidget(QLabel(tr(ACTION_LABELS[action])), row, 0)
            ed = QKeySequenceEdit(QKeySequence(config.get("hotkeys/" + action)))
            ed.setMaximumSequenceLength(1)
            ed.setClearButtonEnabled(True)
            grid.addWidget(ed, row, 1)
            st = QLabel()
            grid.addWidget(st, row, 2)
            self.key_status[action] = st
            self.key_edits[action] = ed
        v.addLayout(grid)
        row = QHBoxLayout()
        b = QPushButton(tr("Restore defaults"))
        b.clicked.connect(self._default_keys)
        row.addWidget(b)
        row.addStretch()
        v.addLayout(row)
        hk = self.app.hotkeys
        if hk.kind == "none":
            n = QLabel(tr("This Wayland desktop does not let applications register global hotkeys. "
                          "Add shortcuts in your desktop keyboard settings that run the commands below."))
            n.setStyleSheet("color:#b26a00")
            n.setWordWrap(True)
            v.addWidget(n)
        elif not hk.available:
            n = QLabel(tr("Global hotkeys need python3-xlib:") + "  " + session.install_hint("xlib"))
            n.setStyleSheet("color:#d32f2f")
            v.addWidget(n)
        elif hk.kind == "kde":
            n = QLabel(tr("Hotkeys are registered with KDE and also appear in System Settings → Shortcuts → X-Capture."))
            n.setStyleSheet("color:#666")
            n.setWordWrap(True)
            v.addWidget(n)
        # xung đột với Spectacle / phím tắt KDE
        self.kde_box = QWidget()
        kl = QVBoxLayout(self.kde_box)
        kl.setContentsMargins(0, 8, 0, 0)
        self.kde_lbl = QLabel()
        self.kde_lbl.setWordWrap(True)
        kl.addWidget(self.kde_lbl)
        kr = QHBoxLayout()
        self.kde_free = QPushButton(tr("Free these keys for X-Capture"))
        self.kde_free.clicked.connect(self._kde_free)
        self.kde_restore = QPushButton(tr("Restore KDE shortcuts"))
        self.kde_restore.clicked.connect(self._kde_restore)
        kr.addWidget(self.kde_free)
        kr.addWidget(self.kde_restore)
        kr.addStretch()
        kl.addLayout(kr)
        v.addWidget(self.kde_box)
        # xung đột với xfce4-screenshooter
        self.xfce_box = QWidget()
        xl = QVBoxLayout(self.xfce_box)
        xl.setContentsMargins(0, 8, 0, 0)
        self.xfce_lbl = QLabel()
        self.xfce_lbl.setWordWrap(True)
        xl.addWidget(self.xfce_lbl)
        xr = QHBoxLayout()
        self.xfce_free = QPushButton(tr("Free the Print keys for X-Capture"))
        self.xfce_free.clicked.connect(self._xfce_free)
        self.xfce_restore = QPushButton(tr("Restore XFCE shortcuts"))
        self.xfce_restore.clicked.connect(self._xfce_restore)
        xr.addWidget(self.xfce_free)
        xr.addWidget(self.xfce_restore)
        xr.addStretch()
        xl.addLayout(xr)
        v.addWidget(self.xfce_box)
        cli = QLabel(tr("You can also bind keys in your desktop settings to commands such as:") +
                     "\n  x-capture --rect   x-capture --window   x-capture --fullscreen   x-capture --active")
        cli.setStyleSheet("color:#666")
        cli.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(cli)
        v.addStretch()
        self._refresh_xfce()
        self._refresh_status(hk.results)
        hk.status.connect(self._refresh_status)
        return w

    def done(self, r):
        try:
            self.app.hotkeys.status.disconnect(self._refresh_status)
        except TypeError:
            pass
        super().done(r)

    def _refresh_status(self, status):
        hk = self.app.hotkeys
        conflicts = hk.conflicts() if hk.kind == "kde" else {}
        for action, st in self.key_status.items():
            seq = config.get("hotkeys/" + action)
            if seq and action in status:
                st.setText("✔" if status[action] else "✖ " + tr("in use"))
                st.setStyleSheet("color:#2e9b4f" if status[action] else "color:#d32f2f")
                st.setToolTip("" if status[action] else
                              conflicts.get(action) or tr("Another program already uses this key combination."))
            else:
                st.setText("")
                st.setToolTip("")
        self._refresh_kde(conflicts)

    def _refresh_kde(self, conflicts):
        has_backup = bool(config.get("kde/backup"))
        self.kde_box.setVisible(self.app.hotkeys.kind == "kde" and (bool(conflicts) or has_backup))
        if conflicts:
            lines = [f"{config.get('hotkeys/' + a)}  →  {who}" for a, who in conflicts.items()]
            self.kde_lbl.setText(tr("These keys are used by other KDE shortcuts:") + "\n" + "\n".join(lines))
        else:
            self.kde_lbl.setText(tr("The KDE shortcuts were released for X-Capture."))
        self.kde_free.setEnabled(bool(conflicts))
        self.kde_restore.setEnabled(has_backup)

    def _kde_free(self):
        hk = self.app.hotkeys
        conflicts = hk.conflicts()
        if not conflicts:
            return
        r = QMessageBox.question(self, tr("X-Capture Settings"),
                                 tr("Remove these keys from the other KDE shortcuts so X-Capture can use them?") +
                                 "\n\n" + "\n".join(f"{config.get('hotkeys/' + a)}  →  {w}" for a, w in conflicts.items())
                                 + "\n\n" + tr("They are backed up and can be restored later."))
        if r != QMessageBox.StandardButton.Yes:
            return
        backup = json.loads(config.get("kde/backup") or "[]")
        known = {tuple(b["id"]) for b in backup}
        for item in hk.release():
            if tuple(item["id"]) not in known:  # giữ bản gốc đầu tiên của mỗi phím tắt
                backup.append(item)
                known.add(tuple(item["id"]))
        config.set("kde/backup", json.dumps(backup))
        self.app.apply_hotkeys(delay=200)

    def _kde_restore(self):
        try:
            backup = json.loads(config.get("kde/backup") or "[]")
        except ValueError:
            backup = []
        self.app.hotkeys.restore(backup)
        config.set("kde/backup", "")
        self.app.apply_hotkeys(delay=200)
        self._refresh_kde({})
    def _default_keys(self):
        for action, key in HOTKEY_ACTIONS:
            self.key_edits[action].setKeySequence(QKeySequence(key))

    def _refresh_xfce(self):
        binds = xfce_print_bindings()
        has_backup = bool(config.get("xfce/backup"))
        self.xfce_box.setVisible(bool(binds) or has_backup)
        if binds:
            names = ", ".join(k.rsplit("/", 1)[1] for k in binds)
            self.xfce_lbl.setText(tr("XFCE keyboard shortcuts are using these keys:") + f" {names}\n" +
                                  tr("X-Capture cannot use them until they are released."))
        else:
            self.xfce_lbl.setText(tr("The XFCE Print-key shortcuts were released for X-Capture."))
        self.xfce_free.setEnabled(bool(binds))
        self.xfce_restore.setEnabled(has_backup)

    def _xfce_free(self):
        binds = xfce_print_bindings()
        if not binds:
            return
        r = QMessageBox.question(self, tr("X-Capture Settings"),
                                 tr("Remove these XFCE shortcuts so X-Capture can use the Print key?") +
                                 "\n\n" + "\n".join(f"{k.rsplit('/', 1)[1]}  →  {v}" for k, v in binds.items()) +
                                 "\n\n" + tr("They are backed up and can be restored later."))
        if r != QMessageBox.StandardButton.Yes:
            return
        old = config.get("xfce/backup")
        backup = dict(line.split("\t", 1) for line in old.splitlines() if "\t" in line) if old else {}
        backup.update(binds)
        config.set("xfce/backup", "\n".join(f"{k}\t{v}" for k, v in backup.items()))
        for prop in binds:
            subprocess.run(["xfconf-query", "-c", XFCE_CHANNEL, "-p", prop, "-r"], timeout=5)
        self.app.apply_hotkeys(delay=600)
        self._refresh_xfce()

    def _xfce_restore(self):
        old = config.get("xfce/backup")
        if not old:
            return
        for line in old.splitlines():
            if "\t" not in line:
                continue
            prop, val = line.split("\t", 1)
            subprocess.run(["xfconf-query", "-c", XFCE_CHANNEL, "-p", prop, "-n", "-t", "string", "-s", val],
                           timeout=5)
        config.set("xfce/backup", "")
        self.app.apply_hotkeys(delay=600)
        self._refresh_xfce()

    # ---------- lưu ----------
    def accept(self):
        config.set("general/language", self.lang.currentData())
        config.set("general/show_panel", self.show_panel.isChecked())
        config.set("general/close_action", self.close_action.currentData())
        set_autostart(self.autostart.isChecked(), self.app.exe_path())
        config.set("editor/external", self.ext.text().strip() or DEFAULTS["editor/external"])
        config.set("capture/delay", self.delay.value())
        config.set("capture/hide_editor", self.hide_editor.isChecked())
        config.set("capture/magnifier", self.magnifier.isChecked())
        config.set("capture/fixed_w", self.fw.value())
        config.set("capture/fixed_h", self.fh.value())
        config.set("capture/scroll_clicks", self.scroll_clicks.value())
        config.set("capture/scroll_max", self.scroll_max.value())
        config.set("record/fps", self.fps.value())
        config.set("record/audio", self.audio.isChecked())
        config.set("auto/interval", self.auto_int.value())
        config.set("output/destination", self.dest.currentData())
        config.set("output/copy_clipboard", self.copy_clip.isChecked())
        config.set("output/auto_save", self.auto_save.isChecked())
        folder = self.folder.text().strip()
        config.set("output/folder", "" if folder == pictures_dir() else folder)
        config.set("output/pattern", self.pattern.text().strip() or DEFAULTS["output/pattern"])
        config.set("output/format", self.fmt.currentData())
        config.set("output/jpeg_quality", self.quality.value())
        for action, ed in self.key_edits.items():
            config.set("hotkeys/" + action, ed.keySequence().toString(QKeySequence.SequenceFormat.PortableText))
        config.sync()
        self.app.settings_changed()
        super().accept()
