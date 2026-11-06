"""Thanh công cụ chụp nổi (Capture Panel) giống FastStone Capture."""
from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QMenu, QToolButton, QWidget

from . import icons
from .config import ACTION_LABELS, config
from .i18n import tr

PANEL_ACTIONS = ["active", "window", "rect", "freehand", "fullscreen", "scroll", "fixed", "record"]
DESTINATIONS = [("editor", "To Editor", "editor"), ("clipboard", "To Clipboard", "clipboard"),
                ("file", "To File", "file"), ("pin", "Pin to Screen", "pin")]


class Grip(QWidget):
    """Tay cầm bên trái để kéo thanh công cụ."""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setFixedWidth(12)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._off = None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setPen(QPen(QColor("#9aa3ad"), 2))
        for y in range(8, self.height() - 6, 5):
            p.drawPoint(4, y)
            p.drawPoint(8, y)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            win = self.panel.windowHandle()
            # để trình quản lý cửa sổ kéo (mượt hơn trên X11), nếu không thì tự kéo
            if not (win and win.startSystemMove()):
                self._off = e.globalPosition().toPoint() - self.panel.pos()

    def mouseMoveEvent(self, e):
        if self._off is not None:
            self.panel.move(e.globalPosition().toPoint() - self._off)

    def mouseReleaseEvent(self, e):
        self._off = None
        self.panel.save_pos()


class CapturePanel(QWidget):
    def __init__(self, app):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.app = app
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("X-Capture")
        self.setObjectName("panel")
        self.setStyleSheet("""
            #panel { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fbfcfe, stop:1 #e3e8ef);
                     border: 1px solid #8f99a6; border-radius: 6px; }
            QToolButton { border: 1px solid transparent; border-radius: 4px; padding: 2px; background: transparent; }
            QToolButton:hover { border-color: #7aa7e0; background: #dbe9fb; }
            QToolButton:pressed { background: #bcd6f7; }
            QToolButton::menu-indicator { image: none; }
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(1)
        lay.addWidget(Grip(self))
        self.buttons = {}
        for a in PANEL_ACTIONS:
            b = self._button(a, lambda _=False, act=a: self.app.capture(act))
            self.buttons[a] = b
            lay.addWidget(b)
        lay.addSpacing(6)
        self.dest_btn = self._button("editor", None)
        self.dest_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.dest_menu = QMenu(self)
        self.dest_btn.setMenu(self.dest_menu)
        lay.addWidget(self.dest_btn)
        self.menu_btn = self._button("menu", None)
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.main_menu = QMenu(self)
        self.main_menu.aboutToShow.connect(self._fill_main_menu)
        self.menu_btn.setMenu(self.main_menu)
        lay.addWidget(self.menu_btn)
        lay.addSpacing(4)
        self.close_btn = self._button("close", self.app.close_panel, 18)
        lay.addWidget(self.close_btn)
        self.refresh()
        self.adjustSize()
        self._place()

    def _button(self, name, slot, size=30):
        b = QToolButton(self)
        b.setIcon(icons.icon(name))
        b.setIconSize(QSize(size, size))
        b.setAutoRaise(True)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if slot:
            b.clicked.connect(slot)
        return b

    def refresh(self):
        """Cập nhật chú giải (kèm phím tắt) và biểu tượng nơi xuất."""
        self.menu_btn.setToolTip(tr("Menu"))
        self.close_btn.setToolTip(tr({"tray": "Hide panel (still running in the system tray)",
                                      "exit": "Close panel and exit X-Capture"}.get(
            config.get("general/close_action"), "Close panel")))
        keys = config.hotkeys()
        for a, b in self.buttons.items():
            k = keys.get(a)
            b.setToolTip(tr(ACTION_LABELS[a]) + (f"  [{k}]" if k else ""))
        dest = config.get("output/destination")
        self.dest_menu.clear()
        for key, label, icon in DESTINATIONS:
            act = self.dest_menu.addAction(icons.icon(icon), tr(label))
            act.setCheckable(True)
            act.setChecked(key == dest)
            act.triggered.connect(lambda _=False, k=key: self.app.set_destination(k))
            if key == dest:
                self.dest_btn.setIcon(icons.icon(icon))
                self.dest_btn.setToolTip(tr("Output") + ": " + tr(label))
        self.dest_menu.addSeparator()
        for key, label in (("output/copy_clipboard", "Also copy to clipboard"),
                           ("output/auto_save", "Also auto-save to file")):
            act = self.dest_menu.addAction(tr(label))
            act.setCheckable(True)
            act.setChecked(config.get(key))
            act.toggled.connect(lambda v, k=key: config.set(k, v))

    def _fill_main_menu(self):
        m = self.main_menu
        m.clear()
        self.app.fill_main_menu(m)

    def _place(self):
        x, y = config.get("panel/x"), config.get("panel/y")
        scr = QApplication.primaryScreen().availableGeometry()
        if x < 0 or y < 0 or not any(s.geometry().contains(QPoint(x + 10, y + 10)) for s in QApplication.screens()):
            x = scr.center().x() - self.width() // 2
            y = scr.top() + 40
        self.move(x, y)

    def save_pos(self):
        config.set("panel/x", self.x())
        config.set("panel/y", self.y())

    def moveEvent(self, e):
        super().moveEvent(e)
        if self.isVisible():
            self.save_pos()

    def closeEvent(self, e):
        # Qt 6 gửi close (không spontaneous) tới mọi cửa sổ khi thoát; từ chối là huỷ thoát
        if self.app.quitting or not e.spontaneous():
            e.accept()
            return
        # Alt+F4 / trình quản lý cửa sổ đóng thanh: xử lý như nút ×
        e.ignore()
        self.app.close_panel()

    def contextMenuEvent(self, e):
        self.main_menu.exec(e.globalPos())

    def show_panel(self):
        self.show()
        self.raise_()
