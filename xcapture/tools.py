"""Công cụ màn hình: ghim ảnh, kính lúp, thước, chọn màu, OCR, đếm ngược, chụp cuộn, quay phim."""
import operator
import os
import shutil
import signal
import subprocess
import tempfile

from PyQt6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QGuiApplication, QImage, QKeySequence, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                             QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                             QVBoxLayout, QWidget)

from . import icons, imageops, session
from .config import APP_TITLE, config
from .i18n import tr

FLOAT = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)


# ---------------- Ghim ảnh lên màn hình ----------------
class PinWindow(QWidget):
    instances = []

    def __init__(self, app, image, pos=None):
        super().__init__(None, FLOAT)
        self.app = app
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr("Pinned image"))
        self.image = image
        self.pm = QPixmap.fromImage(image)
        self.zoom = 1.0
        self._off = None
        self._fit_zoom()
        self.move(pos or QCursor.pos() - QPoint(self.width() // 2, self.height() // 2))
        PinWindow.instances.append(self)
        self.destroyed.connect(lambda: PinWindow.instances.remove(self) if self in PinWindow.instances else None)

    def _fit_zoom(self):
        scr = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        z = min(1.0, scr.width() * 0.8 / max(1, self.pm.width()), scr.height() * 0.8 / max(1, self.pm.height()))
        self.set_zoom(z)

    def set_zoom(self, z):
        self.zoom = max(0.05, min(8.0, z))
        self.setFixedSize(QSize(max(8, round(self.pm.width() * self.zoom)) + 2,
                                max(8, round(self.pm.height() * self.zoom)) + 2))
        self.setToolTip(f"{round(self.zoom * 100)}%  —  " + tr("Wheel: zoom · Ctrl+Wheel: opacity · Double-click / Esc: close"))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.zoom < 1)
        p.drawPixmap(QRect(1, 1, self.width() - 2, self.height() - 2), self.pm)
        p.setPen(QPen(QColor("#1e74d8"), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            win = self.windowHandle()
            if not (win and win.startSystemMove()):
                self._off = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self._off is not None:
            self.move(e.globalPosition().toPoint() - self._off)

    def mouseReleaseEvent(self, e):
        self._off = None

    def mouseDoubleClickEvent(self, e):
        self.close()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        elif e.matches(QKeySequence.StandardKey.Copy):
            QApplication.clipboard().setImage(self.image)

    def wheelEvent(self, e):
        up = e.angleDelta().y() > 0
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.setWindowOpacity(max(0.2, min(1.0, self.windowOpacity() + (0.1 if up else -0.1))))
        else:
            self.set_zoom(self.zoom * (1.15 if up else 1 / 1.15))

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction(icons.icon("copy"), tr("Copy"), lambda: QApplication.clipboard().setImage(self.image))
        m.addAction(icons.icon("saveas"), tr("Save As..."), self.save_as)
        m.addAction(icons.icon("editor"), tr("Open in Editor"), lambda: self.app.open_in_editor(self.image))
        m.addSeparator()
        m.addAction(icons.icon("zoom100"), tr("Actual Size"), lambda: self.set_zoom(1.0))
        op = m.addMenu(tr("Opacity"))
        for v in (100, 80, 60, 40):
            op.addAction(f"{v}%", lambda val=v: self.setWindowOpacity(val / 100))
        m.addSeparator()
        m.addAction(icons.icon("close"), tr("Close"), self.close)
        m.addAction(tr("Close All Pinned Images"), PinWindow.close_all)
        m.exec(e.globalPos())

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Save As"), imageops.auto_filename(config),
                                              ";;".join(imageops.file_filters()))
        if path:
            imageops.save_image(self.image, path, config.get("output/jpeg_quality"))

    @staticmethod
    def close_all():
        for w in list(PinWindow.instances):
            w.close()


# ---------------- Kính lúp màn hình ----------------
class Magnifier(QWidget):
    """Phóng to vùng quanh con trỏ theo thời gian thực. Bấm chuột (bất kỳ đâu) hoặc Esc để đóng."""

    def __init__(self, x11, zoom=4):
        super().__init__(None, FLOAT | Qt.WindowType.X11BypassWindowManagerHint
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.x11 = x11
        self.zoom = zoom
        self.setFixedSize(240, 240)
        self.shot = QPixmap()
        self.color = QColor()
        self.timer = QTimer(self, timeout=self.tick, interval=40)
        self._armed = False

    def start(self):
        self.tick()
        self.show()
        self.timer.start()
        QTimer.singleShot(400, lambda: setattr(self, "_armed", True))

    def tick(self):
        if self._armed and self.x11.pointer_buttons() & (0x100 | 0x200 | 0x400):
            self.close()
            return
        pos = QCursor.pos()
        scr = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        g = scr.geometry()
        n = self.width() // self.zoom
        self.shot = scr.grabWindow(0, pos.x() - g.x() - n // 2, pos.y() - g.y() - n // 2, n, n)
        img = self.shot.toImage()
        if not img.isNull():
            self.color = QColor(img.pixel(min(n // 2, img.width() - 1), min(n // 2, img.height() - 1)))
        x, y = pos.x() + 30, pos.y() + 30
        if x + self.width() > g.right():
            x = pos.x() - self.width() - 30
        if y + self.height() > g.bottom():
            y = pos.y() - self.height() - 30
        self.move(x, y)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.shot)
        c = self.width() // 2
        z = self.zoom
        p.setPen(QPen(QColor(255, 0, 0, 200), 1))
        p.drawRect(c - z // 2, c - z // 2, z, z)
        p.fillRect(0, self.height() - 22, self.width(), 22, QColor(0, 0, 0, 180))
        p.setPen(QColor("white"))
        pos = QCursor.pos()
        p.drawText(QRect(6, self.height() - 22, self.width() - 12, 22), Qt.AlignmentFlag.AlignVCenter,
                   f"{pos.x()},{pos.y()}   {self.color.name().upper()}   ×{z}")
        p.setPen(QPen(QColor("#1e74d8"), 2))
        p.drawRect(1, 1, self.width() - 2, self.height() - 2)

    def keyPressEvent(self, e):
        self.close()


# ---------------- Thước đo màn hình ----------------
class Ruler(QWidget):
    def __init__(self):
        super().__init__(None, FLOAT)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(tr("Screen Ruler"))
        self.vertical = False
        self.length = 800
        self._apply()
        self._drag = None
        self.setMouseTracking(True)
        self.track = QTimer(self, timeout=self.update, interval=50)
        self.track.start()
        self.move(QCursor.pos() - QPoint(100, 30))

    def _apply(self):
        self.setFixedSize(QSize(60, self.length) if self.vertical else QSize(self.length, 60))

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 236, 140, 225))
        p.setPen(QPen(QColor("#6b5b00"), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        f = QFont("Sans")
        f.setPixelSize(10)
        p.setFont(f)
        for i in range(0, self.length, 5):
            h = 18 if i % 50 == 0 else (11 if i % 10 == 0 else 5)
            if self.vertical:
                p.drawLine(0, i, h, i)
                if i % 50 == 0 and i:
                    p.drawText(20, i + 4, str(i))
            else:
                p.drawLine(i, 0, i, h)
                if i % 50 == 0 and i:
                    p.drawText(i + 2, 30, str(i))
        cur = self.mapFromGlobal(QCursor.pos())
        v = cur.y() if self.vertical else cur.x()
        if 0 <= v < self.length:
            p.setPen(QPen(QColor("red"), 1))
            if self.vertical:
                p.drawLine(0, v, self.width(), v)
            else:
                p.drawLine(v, 0, v, self.height())
            p.drawText(QRect(0, self.height() - 16, self.width() - 6, 14) if not self.vertical
                       else QRect(4, self.height() - 16, self.width(), 14),
                       Qt.AlignmentFlag.AlignRight if not self.vertical else Qt.AlignmentFlag.AlignLeft,
                       f"{v} px")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.position().toPoint()
            edge = (pos.y() if self.vertical else pos.x()) > self.length - 12
            self._drag = ("resize" if edge else "move", e.globalPosition().toPoint(), self.pos(), self.length)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        near_end = (pos.y() if self.vertical else pos.x()) > self.length - 12
        self.setCursor(Qt.CursorShape.SizeVerCursor if near_end and self.vertical else
                       Qt.CursorShape.SizeHorCursor if near_end else Qt.CursorShape.SizeAllCursor)
        if not self._drag:
            return
        kind, start, wpos, ln = self._drag
        d = e.globalPosition().toPoint() - start
        if kind == "move":
            self.move(wpos + d)
        else:
            self.length = max(100, ln + (d.y() if self.vertical else d.x()))
            self._apply()

    def mouseReleaseEvent(self, e):
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        self.vertical = not self.vertical
        self._apply()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction(tr("Rotate (double-click)"), self.mouseDoubleClickEvent.__get__(self))
        m.addAction(icons.icon("close"), tr("Close"), self.close)
        m.exec(e.globalPos())


# ---------------- Kết quả chọn màu ----------------
class ColorResult(QDialog):
    def __init__(self, color):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr("Screen Color Picker"))
        self.setWindowIcon(icons.icon("color"))
        lay = QVBoxLayout(self)
        sw = QLabel()
        sw.setFixedHeight(48)
        sw.setStyleSheet(f"background:{color.name()}; border:1px solid #666; border-radius:4px;")
        lay.addWidget(sw)
        h, s, v, _ = color.getHsv()
        values = [("HEX", color.name().upper()),
                  ("RGB", f"{color.red()}, {color.green()}, {color.blue()}"),
                  ("HSV", f"{h}, {s}, {v}"),
                  ("CSS", f"rgb({color.red()}, {color.green()}, {color.blue()})")]
        for label, val in values:
            row = QHBoxLayout()
            lab = QLabel(label)
            lab.setFixedWidth(40)
            ed = QLineEdit(val)
            ed.setReadOnly(True)
            btn = QPushButton(icons.icon("copy"), "")
            btn.setToolTip(tr("Copy"))
            btn.clicked.connect(lambda _=False, t=val: QApplication.clipboard().setText(t))
            row.addWidget(lab)
            row.addWidget(ed)
            row.addWidget(btn)
            lay.addLayout(row)
        info = QLabel(tr("HEX value copied to clipboard."))
        info.setStyleSheet("color:#666")
        lay.addWidget(info)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        QApplication.clipboard().setText(color.name().upper())


# ---------------- OCR ----------------
def tesseract_langs():
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10).stdout
        return [l.strip() for l in out.splitlines()[1:] if l.strip()]
    except (OSError, subprocess.SubprocessError):
        return []


def run_ocr(img, parent=None):
    if not shutil.which("tesseract"):
        QMessageBox.information(parent, APP_TITLE, tr("OCR needs Tesseract. Install it with:") +
                                "\n\n" + session.install_hint("tesseract"))
        return
    langs = tesseract_langs()
    lang = "+".join(l for l in ("vie", "eng") if l in langs) or "eng"
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    # phóng to ảnh nhỏ giúp Tesseract nhận dạng chữ màn hình tốt hơn
    big = img.scaled(img.width() * 2, img.height() * 2, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation) if img.width() < 2000 else img
    imageops.save_image(big, path)
    try:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        res = subprocess.run(["tesseract", path, "stdout", "-l", lang], capture_output=True, text=True, timeout=120)
        text = res.stdout.strip()
    except (OSError, subprocess.SubprocessError) as ex:
        text = f"Error: {ex}"
    finally:
        QApplication.restoreOverrideCursor()
        os.unlink(path)
    d = QDialog(parent)
    d.setWindowTitle(tr("Captured Text (OCR)"))
    d.setWindowIcon(icons.icon("ocr"))
    d.resize(560, 400)
    lay = QVBoxLayout(d)
    ed = QPlainTextEdit(text)
    lay.addWidget(ed)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    copy = bb.addButton(tr("Copy All"), QDialogButtonBox.ButtonRole.ActionRole)
    copy.clicked.connect(lambda: QApplication.clipboard().setText(ed.toPlainText()))
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    if text:
        QApplication.clipboard().setText(text)
    d.exec()


# ---------------- Đếm ngược trước khi chụp ----------------
class Countdown(QWidget):
    done = pyqtSignal()

    def __init__(self, seconds):
        super().__init__(None, FLOAT | Qt.WindowType.X11BypassWindowManagerHint
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.left = seconds
        self.setFixedSize(120, 120)
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.move(scr.geometry().center() - QPoint(60, 60))
        self.timer = QTimer(self, timeout=self._tick, interval=1000)

    def start(self):
        self.show()
        self.timer.start()

    def _tick(self):
        self.left -= 1
        if self.left <= 0:
            self.timer.stop()
            self.hide()
            QTimer.singleShot(150, lambda: (self.done.emit(), self.close()))
        else:
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawEllipse(self.rect().adjusted(4, 4, -4, -4))
        f = QFont("Sans")
        f.setPixelSize(56)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self.left))


# ---------------- Hộp điều khiển nổi (chụp cuộn / quay phim) ----------------
class ControlBox(QWidget):
    stop = pyqtSignal()

    def __init__(self, text, avoid: QRect):
        super().__init__(None, FLOAT | Qt.WindowType.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("QWidget#box{background:#202428;border:1px solid #4a90e2;border-radius:6px;}"
                           "QLabel{color:white;} QPushButton{padding:4px 10px;}")
        self.setObjectName("box")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        lay = QHBoxLayout(self)
        self.label = QLabel(text)
        lay.addWidget(self.label)
        btn = QPushButton(tr("Stop"))
        btn.clicked.connect(self.stop.emit)
        lay.addWidget(btn)
        self.adjustSize()
        # đặt ngoài vùng đang chụp để không lọt vào ảnh
        scr = QGuiApplication.screenAt(avoid.center()) or QGuiApplication.primaryScreen()
        g = scr.geometry()
        candidates = [QPoint(avoid.center().x() - self.width() // 2, avoid.bottom() + 8),
                      QPoint(avoid.center().x() - self.width() // 2, avoid.top() - self.height() - 8),
                      QPoint(avoid.right() + 8, avoid.top()), QPoint(avoid.left() - self.width() - 8, avoid.top()),
                      QPoint(g.right() - self.width() - 4, g.bottom() - self.height() - 4)]
        for c in candidates:
            r = QRect(c, self.size())
            if g.contains(r) and not r.intersects(avoid):
                self.move(c)
                break
        else:
            self.move(candidates[-1])

    def set_text(self, t):
        self.label.setText(t)
        self.adjustSize()


# ---------------- Chụp cửa sổ cuộn ----------------
FEAT_W = 48


def row_features(img):
    """Mỗi dòng ảnh -> 48 giá trị xám (ảnh thu hẹp chiều ngang) để so khớp có dung sai.

    Trình duyệt cuộn mượt có thể dừng ở vị trí lẻ pixel nên so khớp tuyệt đối không dùng được.
    """
    small = img.scaled(FEAT_W, img.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
    bpl = small.bytesPerLine()
    ptr = small.constBits()
    ptr.setsize(small.sizeInBytes())
    data = bytes(ptr)
    return [data[i * bpl:i * bpl + FEAT_W] for i in range(small.height())]


def _diff(a, b):
    return sum(map(abs, map(operator.sub, a, b)))


def find_shift(prev, new):
    """Số dòng nội dung đã cuộn lên giữa hai ảnh (0 = không đổi, None = không khớp)."""
    h = len(prev)
    if h < 16:
        return None
    # chọn các dòng "có nội dung" (độ tương phản cao) của ảnh mới làm mẫu
    rich = [j for j in range(h) if max(new[j]) - min(new[j]) > 40]
    if len(rich) < 8:
        return 0 if prev == new else None
    step = max(1, len(rich) // 80)
    samples = rich[::step]
    total0 = sum(_diff(new[j], prev[j]) for j in samples) / (len(samples) * FEAT_W)
    if total0 < 1.5:
        return 0
    best, best_score = None, 1e9
    for s in range(1, h - 8):
        used = 0
        d = 0
        for j in samples:
            if j + s >= h:
                break
            d += _diff(new[j], prev[j + s])
            used += 1
            if d / (used * FEAT_W) > best_score and used >= 8:
                break
        if used >= 8:
            score = d / (used * FEAT_W)
            if score < best_score:
                best, best_score = s, score
    return best if best_score < 6 else None


class ScrollCapture:
    def __init__(self, app, rect_dev, dpr, vg):
        self.app, self.rect, self.dpr, self.vg = app, rect_dev, dpr, vg
        self.parts = []
        self.prev = None
        self.prev_h = None
        self.total_h = 0
        self.same = 0
        self.stopped = False
        # Wayland: không giả lập được lăn chuột vào cửa sổ của ứng dụng khác → người dùng tự cuộn,
        # X-Capture chụp liên tục và ghép những đoạn mới xuất hiện
        self.manual = not app.screen.can_scroll
        logical = QRect(round(rect_dev.x() / dpr) + vg.x(), round(rect_dev.y() / dpr) + vg.y(),
                        round(rect_dev.width() / dpr), round(rect_dev.height() / dpr))
        self.box = ControlBox(tr("Scroll the content with the mouse wheel, then click Stop.") if self.manual
                              else tr("Scrolling capture... (click Stop to finish)"), logical)
        self.box.stop.connect(self.finish)
        self.center = QPoint(rect_dev.center().x() + round(vg.x() * dpr), rect_dev.center().y() + round(vg.y() * dpr))
        self.timer = QTimer(singleShot=True, timeout=self.step)

    def start(self):
        self.box.show()
        self.app.hotkeys.triggered.connect(self._hotkey)
        QTimer.singleShot(150, self.step)

    def _hotkey(self, _):
        self.finish()

    def grab(self):
        pm, _, _ = self.app.grab_now(windows=False)
        return pm.toImage().copy(self.rect)

    def step(self):
        if self.stopped:
            return
        img = self.grab()
        hs = row_features(img)
        if self.prev is None:
            self.parts.append(img)
            self.total_h = img.height()
        elif self.manual:
            s = find_shift(self.prev_h, hs)
            if not s:
                # không đổi (người dùng chưa cuộn) hoặc không khớp (cuộn quá nhanh / cuộn ngược): bỏ khung này
                self.timer.start(350)
                return
            self.parts.append(img.copy(0, img.height() - s, img.width(), s))
            self.total_h += s
        else:
            s = find_shift(self.prev_h, hs)
            if s == 0:
                self.same += 1
                if self.same >= 2:
                    return self.finish()
            elif s is None:
                # không khớp được: ghép nguyên ảnh mới để không mất nội dung
                self.parts.append(img)
                self.total_h += img.height()
                self.same = 0
            else:
                self.same = 0
                self.parts.append(img.copy(0, img.height() - s, img.width(), s))
                self.total_h += s
        self.prev, self.prev_h = img, hs
        label = tr("Scroll the content with the mouse wheel, then click Stop.") if self.manual \
            else tr("Scrolling capture...")
        self.box.set_text(label + f"  {self.rect.width()}×{self.total_h}")
        if self.total_h >= config.get("capture/scroll_max"):
            return self.finish()
        if self.manual:
            self.timer.start(350)
            return
        # chỉ đưa con trỏ vào vùng ở lần đầu; nếu người dùng kéo chuột ra (để bấm Dừng) thì tạm chờ
        cur = QCursor.pos()
        dev = QPoint(round(cur.x() * self.dpr), round(cur.y() * self.dpr))
        abs_rect = self.rect.translated(round(self.vg.x() * self.dpr), round(self.vg.y() * self.dpr))
        first = len(self.parts) == 1 and self.same == 0 and not getattr(self, "_warped", False)
        if first or abs_rect.contains(dev):
            self._warped = True
            scroller = getattr(self.app.screen, "scroll", None) or self.app.x11.scroll
            if not scroller(self.center if first else None, config.get("capture/scroll_clicks")):
                return self.finish()
        self.timer.start(500)

    def finish(self):
        if self.stopped:
            return
        self.stopped = True
        self.timer.stop()
        try:
            self.app.hotkeys.triggered.disconnect(self._hotkey)
        except TypeError:
            pass
        self.box.close()
        if not self.parts:
            # dừng trước lần chụp đầu tiên: vẫn phải trả trạng thái "đang chụp" cho ứng dụng
            self.app.scroll_done(self, None)
            return
        out = imageops.blank(self.rect.width(), self.total_h)
        p = QPainter(out)
        y = 0
        for part in self.parts:
            p.drawImage(0, y, part)
            y += part.height()
        p.end()
        self.app.scroll_done(self, out)


# ---------------- Quay phim màn hình (ffmpeg) ----------------
class Recorder:
    def __init__(self, app, rect_dev, dpr, vg):
        self.app = app
        self.proc = None
        self.stopped = False
        x = rect_dev.x() + round(vg.x() * dpr)
        y = rect_dev.y() + round(vg.y() * dpr)
        # libx264 cần kích thước chẵn, tối thiểu 2×2
        w, h = max(2, rect_dev.width() // 2 * 2), max(2, rect_dev.height() // 2 * 2)
        self.geom = (x, y, w, h)
        # wf-recorder nhận toạ độ logic của Wayland
        self.wf = app.screen.name == "wlroots" and shutil.which("wf-recorder") is not None
        self.logical = (round(rect_dev.x() / dpr) + vg.x(), round(rect_dev.y() / dpr) + vg.y(),
                        max(2, round(rect_dev.width() / dpr)), max(2, round(rect_dev.height() / dpr)))
        self.path = imageops.auto_filename(config, "video").rsplit(".", 1)[0] + ".mp4"
        self.box = ControlBox("● " + tr("Recording") + " 00:00", QRect(*self.logical))
        self.box.label.setStyleSheet("color:#ff5252; font-weight:bold;")
        self.box.stop.connect(self.stop)
        self.secs = 0
        self.clock = QTimer(timeout=self._tick, interval=1000)

    def start(self):
        from . import session
        lx, ly, lw, lh = self.logical
        if session.is_gnome() and self._gnome_screencast(lx, ly, lw, lh):
            return True
        if shutil.which("spectacle") and session.is_kde():
            cmd = ["spectacle", "-b", "-n", "--record", "-o", self.path]
            if self._spawn(cmd):
                return True
        if shutil.which("wf-recorder") and session.is_wayland():
            cmd = ["wf-recorder", "-g", f"{lx},{ly} {lw}x{lh}", "-f", self.path] + \
                (["-a"] if config.get("record/audio") else [])
            if self._spawn(cmd):
                self.wf = True
                return True
        if session.is_wayland() and not os.environ.get("DISPLAY"):
            QMessageBox.warning(None, APP_TITLE,
                                tr("Screen recording on this Wayland session needs wf-recorder, "
                                   "Spectacle, or GNOME Shell screencast."))
            return False
        x, y, w, h = self.geom
        disp = os.environ.get("DISPLAY", ":0")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "x11grab", "-draw_mouse", "1",
               "-framerate", str(config.get("record/fps")), "-video_size", f"{w}x{h}", "-i", f"{disp}+{x},{y}"]
        if config.get("record/audio"):
            cmd += ["-f", "pulse", "-i", "default", "-c:a", "aac"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", self.path]
        return self._spawn(cmd)

    def _gnome_screencast(self, x, y, w, h):
        from . import dbusutil as D
        if not D.HAVE_QTDBUS or not D.has_service("org.gnome.Shell.Screencast"):
            return False
        try:
            D.call("org.gnome.Shell.Screencast", "/org/gnome/Shell/Screencast",
                   "org.gnome.Shell.Screencast", "ScreencastArea",
                   int(x), int(y), int(w), int(h), self.path, {}, timeout=8000)
            self.wf = False
            self._gnome = True
            self.box.show()
            self.clock.start()
            return True
        except D.DBusError:
            return False

    def _spawn(self, cmd):
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as ex:
            QMessageBox.warning(None, APP_TITLE, str(ex))
            return False
        self.box.show()
        self.clock.start()
        return True

    def _tick(self):
        self.secs += 1
        self.box.set_text("● " + tr("Recording") + f" {self.secs // 60:02d}:{self.secs % 60:02d}")
        if self.proc and self.proc.poll() is not None:
            self.stop()

    def stop(self):
        # phím tắt, nút Dừng, menu khay và đồng hồ đều có thể gọi tới đây
        if self.stopped:
            return
        self.stopped = True
        self.clock.stop()
        self.box.close()
        err = ""
        if getattr(self, "_gnome", False):
            try:
                from . import dbusutil as D
                D.call("org.gnome.Shell.Screencast", "/org/gnome/Shell/Screencast",
                       "org.gnome.Shell.Screencast", "StopScreencast", timeout=8000)
            except Exception:
                pass
        if self.proc and self.proc.poll() is None:
            try:
                if self.wf:
                    self.proc.send_signal(signal.SIGINT)  # wf-recorder kết thúc tệp khi nhận SIGINT
                    self.proc.wait(timeout=10)
                else:
                    self.proc.communicate(b"q", timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        elif self.proc:
            err = (self.proc.stderr.read() or b"").decode(errors="replace")
        self.app.record_done(self, self.path, err)
