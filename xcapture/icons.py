"""Bộ biểu tượng vẽ bằng QPainter (không cần tệp ảnh ngoài)."""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QPolygonF)

S = 64  # vẽ trên lưới 64x64 rồi để QIcon tự co giãn
BLUE = QColor("#1e74d8")
BLUE_L = QColor("#cfe3fb")
DARK = QColor("#3a3f47")
RED = QColor("#e53935")
GREEN = QColor("#2e9b4f")
ORANGE = QColor("#f39c12")
_cache = {}


def _pen(c=DARK, w=4.0, style=Qt.PenStyle.SolidLine):
    p = QPen(c, w, style)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def _window(p, r, title=BLUE, body=QColor("white")):
    p.setPen(_pen(DARK, 3))
    p.setBrush(body)
    p.drawRoundedRect(r, 4, 4)
    p.setBrush(title)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(QRectF(r.x() + 1.5, r.y() + 1.5, r.width() - 3, 9))


def _cursor(p, x, y, s=1.0):
    path = QPainterPath(QPointF(x, y))
    for dx, dy in ((0, 22), (5.5, 17), (10, 26), (14, 24), (9.5, 15.5), (16, 15.5)):
        path.lineTo(x + dx * s, y + dy * s)
    path.closeSubpath()
    p.setPen(_pen(QColor("white"), 2.2))
    p.setBrush(QColor("black"))
    p.drawPath(path)


def _arrow_head(p, a, b, size=12):
    ang = math.atan2(b.y() - a.y(), b.x() - a.x())
    pts = [b,
           QPointF(b.x() - size * math.cos(ang - 0.45), b.y() - size * math.sin(ang - 0.45)),
           QPointF(b.x() - size * math.cos(ang + 0.45), b.y() - size * math.sin(ang + 0.45))]
    p.drawPolygon(QPolygonF(pts))


def _draw(name, p):
    dash = _pen(BLUE, 3.5, Qt.PenStyle.DashLine)
    if name == "app":
        g = QLinearGradient(0, 0, 0, S)
        g.setColorAt(0, QColor("#3d8ef0"))
        g.setColorAt(1, QColor("#1554a8"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(4, 4, 56, 56), 13, 13)
        p.setBrush(QColor("white"))
        p.drawRoundedRect(QRectF(22, 16, 14, 8), 2, 2)
        p.drawRoundedRect(QRectF(12, 22, 40, 26), 5, 5)
        p.setBrush(QColor("#1554a8"))
        p.drawEllipse(QRectF(24, 27, 16, 16))
        p.setBrush(QColor("#ffd54f"))
        p.drawEllipse(QRectF(28.5, 31.5, 7, 7))
    elif name == "active":
        _window(p, QRectF(6, 10, 52, 42))
        p.setPen(_pen(RED, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(3, 7, 58, 48), 6, 6)
    elif name == "window":
        _window(p, QRectF(4, 6, 48, 38), QColor("#8aa4c4"))
        p.setPen(dash)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(12, 20, 30, 18))
        _cursor(p, 34, 30, 1.1)
    elif name == "rect":
        p.setPen(dash)
        p.setBrush(QColor(30, 116, 216, 40))
        p.drawRect(QRectF(8, 12, 48, 38))
        p.setPen(_pen(DARK, 2.5))
        p.drawLine(QPointF(8, 2), QPointF(8, 22))
        p.drawLine(QPointF(-2, 12), QPointF(18, 12))
    elif name == "freehand":
        path = QPainterPath(QPointF(14, 18))
        path.cubicTo(QPointF(28, 0), QPointF(60, 10), QPointF(54, 30))
        path.cubicTo(QPointF(50, 52), QPointF(22, 60), QPointF(12, 46))
        path.cubicTo(QPointF(4, 36), QPointF(18, 34), QPointF(14, 18))
        p.setPen(dash)
        p.setBrush(QColor(30, 116, 216, 40))
        p.drawPath(path)
    elif name == "fullscreen":
        p.setPen(_pen(DARK, 3))
        p.setBrush(BLUE_L)
        p.drawRoundedRect(QRectF(4, 8, 56, 38), 3, 3)
        p.setBrush(DARK)
        p.drawRect(QRectF(26, 46, 12, 6))
        p.drawRoundedRect(QRectF(16, 52, 32, 5), 2, 2)
        p.setPen(_pen(BLUE, 3))
        for (x1, y1, x2, y2) in ((10, 20, 10, 14), (10, 14, 18, 14), (54, 34, 54, 40), (54, 40, 46, 40)):
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    elif name == "scroll":
        _window(p, QRectF(6, 4, 40, 56))
        p.setPen(_pen(DARK, 1.5))
        for y in range(20, 54, 7):
            p.drawLine(QPointF(12, y), QPointF(40, y))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(GREEN)
        p.drawRect(QRectF(50, 8, 8, 30))
        p.drawPolygon(QPolygonF([QPointF(44, 40), QPointF(62, 40), QPointF(54, 56)]))
    elif name == "fixed":
        p.setPen(dash)
        p.setBrush(QColor(30, 116, 216, 40))
        p.drawRect(QRectF(10, 14, 44, 32))
        p.setPen(_pen(DARK, 2))
        p.setBrush(DARK)
        p.drawLine(QPointF(10, 54), QPointF(54, 54))
        p.drawLine(QPointF(4, 14), QPointF(4, 46))
        p.setFont(QFont("Sans", 12, QFont.Weight.Bold))
        p.drawText(QRectF(10, 14, 44, 32), Qt.AlignmentFlag.AlignCenter, "W×H")
    elif name == "record":
        p.setPen(_pen(DARK, 3))
        p.setBrush(QColor("#555"))
        p.drawRoundedRect(QRectF(4, 16, 40, 32), 5, 5)
        p.drawPolygon(QPolygonF([QPointF(44, 28), QPointF(60, 18), QPointF(60, 46), QPointF(44, 36)]))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(RED)
        p.drawEllipse(QPointF(24, 32), 9, 9)
    elif name == "editor":
        p.setPen(_pen(DARK, 3))
        p.setBrush(QColor("#e8f4ff"))
        p.drawRoundedRect(QRectF(6, 10, 52, 44), 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ORANGE)
        p.drawEllipse(QPointF(20, 24), 6, 6)
        p.setBrush(GREEN)
        p.drawPolygon(QPolygonF([QPointF(9, 51), QPointF(26, 32), QPointF(36, 42), QPointF(44, 34), QPointF(56, 51)]))
    elif name == "clipboard":
        p.setPen(_pen(DARK, 3))
        p.setBrush(QColor("#c89b5c"))
        p.drawRoundedRect(QRectF(10, 8, 44, 52), 4, 4)
        p.setBrush(QColor("white"))
        p.drawRect(QRectF(16, 16, 32, 38))
        p.setBrush(QColor("#888"))
        p.drawRoundedRect(QRectF(22, 4, 20, 10), 3, 3)
    elif name in ("file", "save"):
        p.setPen(_pen(DARK, 3))
        p.setBrush(BLUE)
        p.drawRoundedRect(QRectF(8, 8, 48, 48), 4, 4)
        p.setBrush(QColor("white"))
        p.drawRect(QRectF(16, 8, 30, 18))
        p.setBrush(QColor("#ddd"))
        p.drawRect(QRectF(16, 36, 32, 20))
    elif name == "saveas":
        _draw("save", p)
        p.setPen(_pen(ORANGE, 5))
        p.drawLine(QPointF(36, 56), QPointF(58, 34))
    elif name == "pin":
        p.setPen(_pen(DARK, 3))
        p.drawLine(QPointF(28, 38), QPointF(10, 56))
        p.setBrush(RED)
        p.save()
        p.translate(38, 26)
        p.rotate(45)
        p.drawRoundedRect(QRectF(-10, -20, 20, 26), 4, 4)
        p.drawRect(QRectF(-16, 6, 32, 6))
        p.restore()
    elif name == "settings":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(DARK)
        c = QPointF(32, 32)
        for i in range(8):
            p.save()
            p.translate(c)
            p.rotate(i * 45)
            p.drawRect(QRectF(-5, -26, 10, 12))
            p.restore()
        p.drawEllipse(c, 18, 18)
        p.setBrush(QColor("white"))
        p.drawEllipse(c, 7, 7)
    elif name == "report":
        # bong bóng hội thoại có dấu "!" — Báo lỗi / góp ý
        bubble = QPainterPath()
        bubble.addRoundedRect(QRectF(8, 9, 48, 36), 10, 10)
        tail = QPainterPath()
        tail.addPolygon(QPolygonF([QPointF(17, 40), QPointF(14, 56), QPointF(31, 43)]))
        tail.closeSubpath()
        p.setPen(_pen(DARK, 3.5))
        p.setBrush(QColor("white"))
        p.drawPath(bubble.united(tail))
        p.setPen(_pen(RED, 5.5))
        p.drawLine(QPointF(32, 17), QPointF(32, 30))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(RED)
        p.drawEllipse(QPointF(32, 38), 3.4, 3.4)
    elif name == "menu":
        p.setPen(_pen(DARK, 5))
        for y in (18, 32, 46):
            p.drawLine(QPointF(14, y), QPointF(50, y))
    elif name == "close":
        p.setPen(_pen(DARK, 5))
        p.drawLine(QPointF(18, 18), QPointF(46, 46))
        p.drawLine(QPointF(46, 18), QPointF(18, 46))
    elif name == "minimize":
        p.setPen(_pen(DARK, 5))
        p.drawLine(QPointF(18, 44), QPointF(46, 44))
    elif name == "delay":
        p.setPen(_pen(DARK, 3.5))
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(32, 34), 24, 24)
        p.drawLine(QPointF(32, 34), QPointF(32, 18))
        p.drawLine(QPointF(32, 34), QPointF(44, 40))
        p.drawLine(QPointF(26, 6), QPointF(38, 6))
    elif name == "color":
        p.setPen(_pen(DARK, 3))
        p.setBrush(QColor("#9ad"))
        p.save()
        p.translate(32, 32)
        p.rotate(45)
        p.drawRoundedRect(QRectF(-6, -10, 12, 36), 3, 3)
        p.setBrush(DARK)
        p.drawRoundedRect(QRectF(-10, -26, 20, 16), 5, 5)
        p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(RED)
        p.drawEllipse(QPointF(12, 54), 6, 6)
    elif name == "magnifier":
        p.setPen(_pen(DARK, 4))
        p.setBrush(BLUE_L)
        p.drawEllipse(QPointF(26, 26), 18, 18)
        p.setPen(_pen(DARK, 8))
        p.drawLine(QPointF(40, 40), QPointF(56, 56))
    elif name == "ruler":
        p.save()
        p.translate(32, 32)
        p.rotate(-35)
        p.setPen(_pen(DARK, 2.5))
        p.setBrush(QColor("#f6d365"))
        p.drawRect(QRectF(-28, -9, 56, 18))
        for i, x in enumerate(range(-22, 26, 6)):
            p.drawLine(QPointF(x, -9), QPointF(x, -9 + (8 if i % 2 == 0 else 4)))
        p.restore()
    elif name == "ocr":
        p.setPen(_pen(BLUE, 3, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(6, 8, 52, 48))
        p.setPen(DARK)
        p.setFont(QFont("Serif", 30, QFont.Weight.Bold))
        p.drawText(QRectF(6, 6, 52, 50), Qt.AlignmentFlag.AlignCenter, "T")
    elif name == "auto":
        _draw("fullscreen", p)
        p.setPen(_pen(GREEN, 4))
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(46, 44), 13, 13)
        p.drawLine(QPointF(46, 44), QPointF(46, 36))
        p.drawLine(QPointF(46, 44), QPointF(52, 47))
    elif name == "open":
        p.setPen(_pen(DARK, 3))
        p.setBrush(QColor("#f3c35b"))
        path = QPainterPath(QPointF(6, 14))
        for x, y in ((24, 14), (30, 20), (56, 20), (56, 52), (6, 52)):
            path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "copy":
        p.setPen(_pen(DARK, 3))
        p.setBrush(QColor("#ddd"))
        p.drawRoundedRect(QRectF(8, 6, 32, 38), 3, 3)
        p.setBrush(QColor("white"))
        p.drawRoundedRect(QRectF(22, 20, 32, 38), 3, 3)
    elif name == "paste":
        _draw("clipboard", p)
    elif name in ("undo", "redo"):
        if name == "redo":
            p.translate(S, 0)
            p.scale(-1, 1)
        p.setPen(_pen(BLUE, 6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(18, 26))
        path.cubicTo(QPointF(36, 12), QPointF(60, 22), QPointF(52, 44))
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BLUE)
        p.drawPolygon(QPolygonF([QPointF(6, 30), QPointF(24, 12), QPointF(28, 36)]))
    elif name in ("zoomin", "zoomout", "zoom100", "zoomfit"):
        _draw("magnifier", p)
        p.setPen(_pen(DARK, 3.5))
        if name in ("zoomin", "zoomout"):
            p.drawLine(QPointF(18, 26), QPointF(34, 26))
        if name == "zoomin":
            p.drawLine(QPointF(26, 18), QPointF(26, 34))
        if name == "zoom100":
            p.setFont(QFont("Sans", 11, QFont.Weight.Bold))
            p.drawText(QRectF(8, 8, 36, 36), Qt.AlignmentFlag.AlignCenter, "1:1")
        if name == "zoomfit":
            p.drawRect(QRectF(18, 19, 16, 14))
    # ---- công cụ vẽ ----
    elif name == "select":
        _cursor(p, 20, 10, 1.6)
    elif name == "arrow":
        p.setPen(_pen(RED, 5))
        p.setBrush(RED)
        a, b = QPointF(10, 54), QPointF(52, 12)
        p.drawLine(a, QPointF(46, 18))
        _arrow_head(p, a, b, 18)
    elif name == "line":
        p.setPen(_pen(RED, 5))
        p.drawLine(QPointF(10, 54), QPointF(54, 10))
    elif name == "rectangle":
        p.setPen(_pen(RED, 5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(10, 16, 44, 32))
    elif name == "ellipse":
        p.setPen(_pen(RED, 5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(8, 14, 48, 36))
    elif name == "pen":
        p.setPen(_pen(RED, 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(6, 46))
        path.cubicTo(QPointF(16, 20), QPointF(26, 60), QPointF(36, 34))
        path.cubicTo(QPointF(42, 20), QPointF(52, 30), QPointF(58, 18))
        p.drawPath(path)
    elif name == "marker":
        p.setPen(_pen(QColor(255, 210, 0, 200), 12))
        path = QPainterPath(QPointF(8, 44))
        path.cubicTo(QPointF(20, 20), QPointF(40, 52), QPointF(56, 22))
        p.drawPath(path)
    elif name == "highlight":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 225, 0))
        p.drawRect(QRectF(6, 20, 52, 24))
        p.setPen(DARK)
        p.setFont(QFont("Sans", 16, QFont.Weight.Bold))
        p.drawText(QRectF(6, 20, 52, 24), Qt.AlignmentFlag.AlignCenter, "abc")
    elif name == "text":
        p.setPen(RED)
        p.setFont(QFont("Serif", 36, QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, S, S), Qt.AlignmentFlag.AlignCenter, "A")
    elif name == "callout":
        p.setPen(_pen(RED, 3.5))
        p.setBrush(QColor("#fff8d0"))
        path = QPainterPath()
        path.addRoundedRect(QRectF(6, 8, 52, 34), 8, 8)
        tail = QPainterPath(QPointF(16, 40))
        tail.lineTo(12, 58)
        tail.lineTo(30, 40)
        path = path.united(tail)
        p.drawPath(path)
    elif name == "step":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(RED)
        p.drawEllipse(QPointF(32, 32), 24, 24)
        p.setPen(QColor("white"))
        p.setFont(QFont("Sans", 26, QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, S, S), Qt.AlignmentFlag.AlignCenter, "1")
    elif name in ("blur", "pixelate"):
        cols = [QColor("#7fa7d9"), QColor("#c8d8ee"), QColor("#9db9e2"), QColor("#e5edf8")]
        n = 4
        for i in range(n):
            for j in range(n):
                p.fillRect(QRectF(8 + i * 12, 8 + j * 12, 12, 12), cols[(i + j * 3) % 4])
        if name == "blur":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 150))
            p.drawEllipse(QPointF(32, 32), 18, 18)
        p.setPen(_pen(DARK, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(8, 8, 48, 48))
    elif name == "spotlight":
        p.fillRect(QRectF(4, 4, 56, 56), QColor(40, 40, 40))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#fff7c0"))
        p.drawEllipse(QRectF(16, 16, 32, 32))
    elif name == "crop":
        p.setPen(_pen(DARK, 5))
        p.drawLine(QPointF(16, 4), QPointF(16, 48))
        p.drawLine(QPointF(16, 48), QPointF(60, 48))
        p.drawLine(QPointF(4, 16), QPointF(48, 16))
        p.drawLine(QPointF(48, 16), QPointF(48, 60))
    elif name == "resize":
        p.setPen(_pen(DARK, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(6, 26, 30, 30))
        p.setPen(_pen(BLUE, 4))
        p.setBrush(BLUE)
        p.drawLine(QPointF(28, 34), QPointF(52, 10))
        _arrow_head(p, QPointF(28, 34), QPointF(56, 6), 14)
    elif name in ("rotl", "rotr"):
        if name == "rotr":
            p.translate(S, 0)
            p.scale(-1, 1)
        p.setPen(_pen(BLUE, 5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(12, 12, 40, 40), 100 * 16, 270 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BLUE)
        p.drawPolygon(QPolygonF([QPointF(20, 4), QPointF(34, 14), QPointF(20, 24)]))
    elif name in ("fliph", "flipv"):
        if name == "flipv":
            p.translate(S / 2, S / 2)
            p.rotate(90)
            p.translate(-S / 2, -S / 2)
        p.setPen(_pen(DARK, 2, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(32, 4), QPointF(32, 60))
        p.setPen(_pen(DARK, 2.5))
        p.setBrush(BLUE)
        p.drawPolygon(QPolygonF([QPointF(26, 12), QPointF(26, 52), QPointF(4, 52)]))
        p.setBrush(QColor("white"))
        p.drawPolygon(QPolygonF([QPointF(38, 12), QPointF(38, 52), QPointF(60, 52)]))
    elif name == "border":
        p.setPen(_pen(BLUE, 7))
        p.setBrush(QColor("white"))
        p.drawRect(QRectF(10, 10, 44, 44))
    elif name == "shadow":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(QRectF(16, 16, 42, 42), 4, 4)
        p.setPen(_pen(DARK, 3))
        p.setBrush(QColor("white"))
        p.drawRect(QRectF(6, 6, 42, 42))
    elif name == "torn":
        path = QPainterPath(QPointF(8, 6))
        path.lineTo(56, 6)
        x = 56
        up = True
        while x > 8:
            x -= 6
            path.lineTo(max(x, 8), 46 if up else 54)
            up = not up
        path.closeSubpath()
        p.setPen(_pen(DARK, 3))
        p.setBrush(QColor("white"))
        p.drawPath(path)
    elif name == "caption":
        p.setPen(_pen(DARK, 3))
        p.setBrush(QColor("white"))
        p.drawRect(QRectF(6, 6, 52, 52))
        p.setBrush(DARK)
        p.drawRect(QRectF(6, 40, 52, 18))
        p.setPen(QColor("white"))
        p.setFont(QFont("Sans", 10, QFont.Weight.Bold))
        p.drawText(QRectF(6, 40, 52, 18), Qt.AlignmentFlag.AlignCenter, "Abc")
    elif name == "gray":
        g = QLinearGradient(0, 0, S, 0)
        g.setColorAt(0, QColor("black"))
        g.setColorAt(1, QColor("white"))
        p.setPen(_pen(DARK, 3))
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(6, 14, 52, 36))
    elif name == "invert":
        p.setPen(_pen(DARK, 3))
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(32, 32), 24, 24)
        p.setBrush(DARK)
        p.drawPie(QRectF(8, 8, 48, 48), 90 * 16, 180 * 16)
    elif name == "delete":
        p.setPen(_pen(RED, 6))
        p.drawLine(QPointF(16, 16), QPointF(48, 48))
        p.drawLine(QPointF(48, 16), QPointF(16, 48))
    elif name == "folder":
        _draw("open", p)
    elif name == "external":
        _draw("editor", p)
        p.setPen(_pen(BLUE, 4))
        p.drawLine(QPointF(40, 24), QPointF(60, 4))
        p.drawLine(QPointF(46, 4), QPointF(60, 4))
        p.drawLine(QPointF(60, 4), QPointF(60, 18))
    elif name == "tray":
        _draw("app", p)
    else:
        p.setPen(DARK)
        p.setFont(QFont("Sans", 28, QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, S, S), Qt.AlignmentFlag.AlignCenter, name[:1].upper())


def pixmap(name, size=S):
    pm = QPixmap(S, S)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    _draw(name, p)
    p.end()
    if size != S:
        pm = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return pm


def icon(name):
    if name not in _cache:
        ic = QIcon()
        for sz in (16, 22, 24, 32, 48, 64):
            ic.addPixmap(pixmap(name, sz))
        _cache[name] = ic
    return _cache[name]


def save_app_icon(path, size=256):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / S, size / S)
    _draw("app", p)
    p.end()
    return pm.save(path)
