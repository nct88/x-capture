"""Lớp phủ toàn màn hình (ảnh đã đóng băng) để chọn vùng / cửa sổ / màu."""
from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QPainter, QPainterPath,
                         QPen, QRegion)
from PyQt6.QtWidgets import QWidget

from .i18n import tr

RECT_MODES = ("rect", "ocr", "scroll", "record")
HINTS = {
    "rect": "Drag to select a region, or click a window. Esc / right-click to cancel.",
    "ocr": "Select the region that contains text. Esc to cancel.",
    "scroll": "Select the scrolling area (or click a window). Esc to cancel.",
    "record": "Select the region to record (or click a window). Esc to cancel.",
    "window": "Click a window to capture it. Esc to cancel.",
    "freehand": "Hold the left mouse button and draw around the area. Esc to cancel.",
    "fixed": "Move the frame and click to capture. Esc to cancel.",
    "color": "Click to pick a color. Esc to cancel.",
    "magnify": "Screen magnifier: move the mouse. Click or Esc to close.",
}


class SelectionOverlay(QWidget):
    finished = pyqtSignal(dict)
    canceled = pyqtSignal()

    def __init__(self, pm, vg, dpr, mode, windows=(), fixed_size=QSize(800, 600), magnifier=True):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.X11BypassWindowManagerHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.pm, self.vg, self.dpr, self.mode = pm, vg, dpr, mode
        self.img = pm.toImage()
        self.bounds = QRect(0, 0, pm.width(), pm.height())
        self.windows = [r.intersected(self.bounds) for r in windows if r.intersects(self.bounds)]
        self.fixed_size = fixed_size
        self.magnifier = magnifier
        self.start = None
        self.sel = QRect()
        self.path = None
        self.dragging = False
        self.done = False
        g = QCursor.pos() - vg.topLeft()
        self.cur = QPoint(round(g.x() * dpr), round(g.y() * dpr))
        self.hover = self._window_at(self.cur)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(vg)

    def start_overlay(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.grabKeyboard()

    # ---------- tiện ích ----------
    def _dev(self, pos):
        return QPoint(min(max(round(pos.x() * self.dpr), 0), self.bounds.width() - 1),
                      min(max(round(pos.y() * self.dpr), 0), self.bounds.height() - 1))

    def _window_at(self, pt):
        if self.mode not in RECT_MODES + ("window",):
            return None
        for r in self.windows:
            if r.contains(pt):
                return r
        return None

    def _fixed_rect(self):
        w, h = self.fixed_size.width(), self.fixed_size.height()
        r = QRect(self.cur.x() - w // 2, self.cur.y() - h // 2, w, h)
        # giữ khung nằm trong màn hình
        r.moveLeft(max(0, min(r.left(), self.bounds.width() - w)))
        r.moveTop(max(0, min(r.top(), self.bounds.height() - h)))
        return r.intersected(self.bounds)

    def _highlight(self):
        if self.mode == "freehand":
            return self.path
        if self.mode == "fixed":
            return self._fixed_rect()
        if self.mode == "color":
            return None
        if self.dragging and self.sel.width() > 1:
            return self.sel
        return self.hover

    # ---------- vẽ ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.scale(1 / self.dpr, 1 / self.dpr)
        p.drawPixmap(0, 0, self.pm)
        hl = self._highlight()
        dim = QColor(0, 0, 0, 110)
        full = QPainterPath()
        full.addRect(QRectF(self.bounds))
        if isinstance(hl, QPainterPath):
            p.fillPath(full.subtracted(hl), dim)
        elif isinstance(hl, QRect) and not hl.isNull():
            p.setClipRegion(QRegion(self.bounds).subtracted(QRegion(hl)))
            p.fillRect(self.bounds, dim)
            p.setClipping(False)
        elif self.mode != "magnify":
            p.fillRect(self.bounds, QColor(0, 0, 0, 60))

        lw = max(1, round(self.dpr))
        if isinstance(hl, QPainterPath):
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor("#1e90ff"), 2 * lw))
            p.drawPath(hl)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        elif isinstance(hl, QRect) and not hl.isNull():
            p.setPen(QPen(QColor("#1e90ff"), 2 * lw))
            p.drawRect(hl.adjusted(0, 0, -1, -1))
            self._size_label(p, hl)

        if self.mode in RECT_MODES + ("freehand", "color") and not (self.dragging and self.mode == "freehand"):
            # nét đứt trắng trên nền đen để thấy được trên mọi màu
            for pen in (QPen(QColor(0, 0, 0, 150), lw), QPen(QColor(255, 255, 255, 220), lw, Qt.PenStyle.DashLine)):
                p.setPen(pen)
                p.drawLine(0, self.cur.y(), self.bounds.width(), self.cur.y())
                p.drawLine(self.cur.x(), 0, self.cur.x(), self.bounds.height())

        if self.magnifier or self.mode in ("color", "magnify"):
            self._loupe(p)
        self._hint(p)

    def _size_label(self, p, r):
        f = QFont("Sans", 9)
        f.setPixelSize(round(12 * self.dpr))
        p.setFont(f)
        text = f"{r.width()} × {r.height()}"
        fm = QFontMetrics(f)
        w, h = fm.horizontalAdvance(text) + 12 * self.dpr, fm.height() + 6 * self.dpr
        y = r.top() - h - 4 if r.top() - h - 4 > 0 else r.top() + 4
        box = QRectF(r.left(), y, w, h)
        p.fillRect(box, QColor(30, 144, 255, 220))
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _loupe(self, p):
        d = self.dpr
        n, z = (21, 12) if self.mode == "magnify" else (15, 8)
        size = n * z
        info_h = round(48 * d)
        x, y = self.cur.x() + round(24 * d), self.cur.y() + round(24 * d)
        if x + size > self.bounds.width():
            x = self.cur.x() - size - round(24 * d)
        if y + size + info_h > self.bounds.height():
            y = self.cur.y() - size - info_h - round(24 * d)
        src = QRect(self.cur.x() - n // 2, self.cur.y() - n // 2, n, n)
        tgt = QRect(x, y, size, size)
        p.fillRect(tgt.adjusted(-2, -2, 2, 2 + info_h), QColor(20, 20, 20, 230))
        p.drawPixmap(tgt, self.pm, src)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        for i in range(1, n):
            p.drawLine(x + i * z, y, x + i * z, y + size)
            p.drawLine(x, y + i * z, x + size, y + i * z)
        p.setPen(QPen(QColor("#ff3b30"), 2))
        p.drawRect(x + (n // 2) * z, y + (n // 2) * z, z, z)
        c = QColor(self.img.pixel(self.cur))
        f = QFont("Monospace")
        f.setPixelSize(round(11 * d))
        p.setFont(f)
        p.setPen(QColor("white"))
        lines = [f"X: {self.cur.x()}  Y: {self.cur.y()}",
                 f"RGB({c.red()},{c.green()},{c.blue()})  {c.name().upper()}"]
        if self.dragging and self.mode in RECT_MODES:
            lines[0] += f"   {self.sel.width()}×{self.sel.height()}"
        p.fillRect(QRect(x, y + size + round(6 * d), round(12 * d), round(12 * d)), c)
        p.drawText(QRect(x + round(16 * d), y + size + round(2 * d), size + 200, info_h),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "\n".join(lines))

    def _hint(self, p):
        text = tr(HINTS.get(self.mode, ""))
        if not text or self.dragging:
            return
        f = QFont("Sans")
        f.setPixelSize(round(14 * self.dpr))
        p.setFont(f)
        fm = QFontMetrics(f)
        w, h = fm.horizontalAdvance(text) + 32 * self.dpr, fm.height() + 16 * self.dpr
        # đặt ở giữa màn hình chứa con trỏ
        scr = QRect(0, 0, self.bounds.width(), self.bounds.height())
        for s in self.screen().virtualSiblings():
            g = s.geometry().translated(-self.vg.topLeft())
            gd = QRect(round(g.x() * self.dpr), round(g.y() * self.dpr),
                       round(g.width() * self.dpr), round(g.height() * self.dpr))
            if gd.contains(self.cur):
                scr = gd
        box = QRectF(scr.center().x() - w / 2, scr.top() + 24 * self.dpr, w, h)
        if box.adjusted(-40, -40, 40, 40).contains(QPointF(self.cur)):
            box.moveTop(scr.bottom() - h - 24 * self.dpr)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 190))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    # ---------- chuột / phím ----------
    def mousePressEvent(self, e):
        self.cur = self._dev(e.position())
        if self.mode == "magnify":
            self._cancel()
            return
        if e.button() == Qt.MouseButton.RightButton:
            if self.dragging:
                self.dragging = False
                self.sel = QRect()
                self.update()
            else:
                self._cancel()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.mode in RECT_MODES:
            self.start = QPoint(self.cur)
            self.sel = QRect(self.start, self.start)
            self.dragging = True
        elif self.mode == "freehand":
            self.path = QPainterPath(QPointF(self.cur))
            self.dragging = True
        elif self.mode == "window":
            if self.hover:
                self._finish(rect=self.hover)
        elif self.mode == "fixed":
            self._finish(rect=self._fixed_rect())
        elif self.mode == "color":
            self._finish(color=QColor(self.img.pixel(self.cur)), point=self.cur)
        self.update()

    def mouseMoveEvent(self, e):
        self.cur = self._dev(e.position())
        if self.dragging and self.mode in RECT_MODES:
            self.sel = QRect(self.start, self.cur).normalized()
        elif self.dragging and self.mode == "freehand":
            self.path.lineTo(QPointF(self.cur))
        else:
            self.hover = self._window_at(self.cur)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.dragging:
            return
        self.cur = self._dev(e.position())
        self.dragging = False
        if self.mode in RECT_MODES:
            if self.sel.width() < 4 and self.sel.height() < 4:
                if self.hover:
                    self._finish(rect=self.hover)
                self.sel = QRect()
            else:
                self._finish(rect=QRect(self.start, self.cur).normalized().intersected(self.bounds))
        elif self.mode == "freehand":
            self.path.closeSubpath()
            br = self.path.boundingRect().toAlignedRect().intersected(self.bounds)
            if br.width() > 4 and br.height() > 4:
                self._finish(rect=br, path=self.path)
            else:
                self.path = None
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self._cancel()
            return
        step = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                 Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if k in moves:
            dx, dy = moves[k]
            QCursor.setPos(QCursor.pos() + QPoint(dx, dy))
            return
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.mode == "fixed":
                self._finish(rect=self._fixed_rect())
            elif self.mode == "color":
                self._finish(color=QColor(self.img.pixel(self.cur)), point=self.cur)
            elif self.hover:
                self._finish(rect=self.hover)

    def _finish(self, **result):
        if self.done:
            return
        self.done = True
        self.releaseKeyboard()
        self.hide()
        self.finished.emit(result)
        self.close()

    def _cancel(self):
        if self.done:
            return
        self.done = True
        self.releaseKeyboard()
        self.hide()
        self.canceled.emit()
        self.close()
