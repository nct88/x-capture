"""Đối tượng chú thích có thể chỉnh sửa lại (di chuyển, kéo tay cầm) và lệnh hoàn tác."""
import math

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen,
                         QPolygonF, QTextCursor, QUndoCommand)
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QStyle

HIGHLIGHT = QColor(255, 228, 0)
HANDLE = 8.0
RECT_KINDS = ("rect", "ellipse", "highlight", "spotlight", "rubber")
LINE_KINDS = ("line", "arrow")
PATH_KINDS = ("pen", "marker")


def make_pen(color, width):
    p = QPen(color, width)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


class AnnoItem(QGraphicsItem):
    def __init__(self, kind, start, color=QColor("red"), width=3, fill=False, shadow=True, number=1):
        super().__init__()
        self.kind = kind
        self.p1 = QPointF(start)
        self.p2 = QPointF(start)
        self.points = [QPointF(start)]
        self.color = QColor(color)
        self.width = float(width)
        self.fill = fill
        self.shadow = shadow and kind not in ("highlight", "spotlight", "marker", "rubber")
        self.number = number
        self._h = None
        self._old = None
        flags = QGraphicsItem.GraphicsItemFlag
        if kind != "rubber":
            self.setFlags(flags.ItemIsSelectable | flags.ItemIsMovable)
        self.setZValue(10 if kind != "spotlight" else 5)
        self.setAcceptHoverEvents(True)

    # ---------- hình học ----------
    def rect(self):
        return QRectF(self.p1, self.p2).normalized()

    def step_radius(self):
        return 12 + self.width * 2

    def head(self):
        return max(12.0, self.width * 4)

    def outline(self):
        path = QPainterPath()
        k = self.kind
        if k in LINE_KINDS:
            path.moveTo(self.p1)
            path.lineTo(self.p2)
        elif k in ("rect", "highlight", "rubber", "spotlight"):
            path.addRect(self.rect())
        elif k == "ellipse":
            path.addEllipse(self.rect())
        elif k in PATH_KINDS:
            path.moveTo(self.points[0])
            for pt in self.points[1:]:
                path.lineTo(pt)
        elif k == "step":
            r = self.step_radius()
            path.addEllipse(self.p1, r, r)
        return path

    def handles(self):
        if not self.isSelected():
            return []
        if self.kind in LINE_KINDS:
            return [self.p1, self.p2]
        if self.kind in RECT_KINDS:
            r = self.rect()
            return [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
        return []

    def boundingRect(self):
        if self.kind == "spotlight" and self.scene():
            return self.mapRectFromScene(self.scene().sceneRect()).united(self.rect())
        m = self.width * (4 if self.kind == "marker" else 1) + HANDLE + 6
        if self.kind == "arrow":
            m += self.head()
        return self.outline().controlPointRect().adjusted(-m, -m, m, m)

    def shape(self):
        path = self.outline()
        if self.kind in ("rect", "ellipse", "highlight", "spotlight"):
            path = QPainterPath()
            path.addRect(self.rect().adjusted(-4, -4, 4, 4))
        elif self.kind != "step":
            st = QPainterPathStroker()
            st.setWidth(max(10.0, self.width * (4 if self.kind == "marker" else 1) + 8))
            path = st.createStroke(path)
        for h in self.handles():
            path.addRect(QRectF(h.x() - HANDLE, h.y() - HANDLE, HANDLE * 2, HANDLE * 2))
        return path

    # ---------- vẽ ----------
    def paint(self, p, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.shadow:
            p.save()
            p.translate(3, 3)
            self._draw(p, QColor(0, 0, 0, 70), shadow=True)
            p.restore()
        self._draw(p, self.color)
        for h in self.handles():
            p.setPen(QPen(QColor("#1e74d8"), 1))
            p.setBrush(QColor("white"))
            p.drawRect(QRectF(h.x() - HANDLE / 2, h.y() - HANDLE / 2, HANDLE, HANDLE))
        if self.isSelected() and self.kind in PATH_KINDS + ("step",):
            p.setPen(QPen(QColor("#1e74d8"), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(self.outline().controlPointRect().adjusted(-4, -4, 4, 4))

    def _draw(self, p, color, shadow=False):
        k = self.kind
        if k in LINE_KINDS:
            p.setPen(make_pen(color, self.width))
            line = QLineF(self.p1, self.p2)
            if k == "arrow" and line.length() > 1:
                h = min(self.head(), line.length())
                ang = math.atan2(line.dy(), line.dx())
                tip = self.p2
                base = QPointF(tip.x() - h * 0.8 * math.cos(ang), tip.y() - h * 0.8 * math.sin(ang))
                p.drawLine(self.p1, base)
                pts = [tip,
                       QPointF(tip.x() - h * math.cos(ang - 0.42), tip.y() - h * math.sin(ang - 0.42)),
                       QPointF(tip.x() - h * math.cos(ang + 0.42), tip.y() - h * math.sin(ang + 0.42))]
                p.setPen(make_pen(color, 1))
                p.setBrush(color)
                p.drawPolygon(QPolygonF(pts))
            else:
                p.drawLine(line)
        elif k in ("rect", "ellipse"):
            p.setPen(make_pen(color, self.width))
            if self.fill:
                fc = QColor(color)
                fc.setAlpha(min(color.alpha(), 90))
                p.setBrush(fc)
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
            if k == "rect":
                p.drawRect(self.rect())
            else:
                p.drawEllipse(self.rect())
        elif k == "highlight":
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            p.fillRect(self.rect(), HIGHLIGHT)
        elif k == "marker":
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            p.setPen(make_pen(HIGHLIGHT, max(12.0, self.width * 4)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(self.outline())
        elif k == "pen":
            p.setPen(make_pen(color, self.width))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(self.outline())
        elif k == "spotlight":
            outer = QPainterPath()
            outer.addRect(self.boundingRect())
            hole = QPainterPath()
            hole.addEllipse(self.rect())
            p.fillPath(outer.subtracted(hole), QColor(0, 0, 0, 140))
            if self.isSelected():
                p.setPen(QPen(QColor("#1e74d8"), 1, Qt.PenStyle.DashLine))
                p.drawRect(self.rect())
        elif k == "rubber":
            p.setPen(QPen(QColor("#1e74d8"), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(QColor(30, 116, 216, 40))
            p.drawRect(self.rect())
        elif k == "step":
            r = self.step_radius()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(self.p1, r, r)
            if not shadow:
                f = QFont("Sans")
                f.setBold(True)
                f.setPixelSize(int(r * (1.1 if self.number < 10 else 0.85)))
                p.setFont(f)
                p.setPen(QColor("white"))
                p.drawText(QRectF(self.p1.x() - r, self.p1.y() - r, 2 * r, 2 * r),
                           Qt.AlignmentFlag.AlignCenter, str(self.number))

    # ---------- cập nhật khi tạo ----------
    def drag_to(self, pt, constrain=False):
        self.prepareGeometryChange()
        if self.kind in PATH_KINDS:
            self.points.append(QPointF(pt))
        elif self.kind == "step":
            self.p1 = QPointF(pt)
        else:
            if constrain:
                pt = self._constrain(self.p1, pt)
            self.p2 = QPointF(pt)
        self.update()

    def _constrain(self, a, b):
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if self.kind in LINE_KINDS:
            ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            ln = math.hypot(dx, dy)
            return QPointF(a.x() + ln * math.cos(ang), a.y() + ln * math.sin(ang))
        s = max(abs(dx), abs(dy))
        return QPointF(a.x() + math.copysign(s, dx or 1), a.y() + math.copysign(s, dy or 1))

    def is_trivial(self):
        if self.kind in PATH_KINDS:
            return len(self.points) < 2
        if self.kind == "step":
            return False
        r = QRectF(self.p1, self.p2)
        return abs(r.width()) < 3 and abs(r.height()) < 3

    # ---------- trạng thái / hoàn tác ----------
    def get_state(self):
        return dict(p1=QPointF(self.p1), p2=QPointF(self.p2), points=[QPointF(x) for x in self.points],
                    color=QColor(self.color), width=self.width, fill=self.fill, shadow=self.shadow,
                    number=self.number, pos=QPointF(self.pos()))

    def set_state(self, st):
        self.prepareGeometryChange()
        self.p1, self.p2 = QPointF(st["p1"]), QPointF(st["p2"])
        self.points = [QPointF(x) for x in st["points"]]
        self.color, self.width, self.fill = QColor(st["color"]), st["width"], st["fill"]
        self.shadow, self.number = st["shadow"], st["number"]
        self.setPos(st["pos"])
        self.update()

    def set_style(self, color=None, width=None, fill=None, shadow=None):
        self.prepareGeometryChange()
        if color is not None:
            self.color = QColor(color)
        if width is not None:
            self.width = float(width)
        if fill is not None:
            self.fill = fill
        if shadow is not None and self.kind not in ("highlight", "spotlight", "marker"):
            self.shadow = shadow
        self.update()

    def _handle_at(self, pos):
        for i, h in enumerate(self.handles()):
            if QLineF(h, pos).length() <= HANDLE:
                return i
        return None

    def hoverMoveEvent(self, e):
        self.setCursor(Qt.CursorShape.CrossCursor if self._handle_at(e.pos()) is not None
                       else Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, e):
        idx = self._handle_at(e.pos()) if e.button() == Qt.MouseButton.LeftButton else None
        if idx is not None:
            self._h = idx
            self._old = self.get_state()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._h is None:
            return super().mouseMoveEvent(e)
        self.prepareGeometryChange()
        pt = e.pos()
        if self.kind in LINE_KINDS:
            if self._h == 0:
                self.p1 = pt
            else:
                self.p2 = pt
        else:
            r = self.rect()
            corners = [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
            opposite = corners[(self._h + 2) % 4]
            self.p1, self.p2 = opposite, pt
            nr = self.rect()
            new = [nr.topLeft(), nr.topRight(), nr.bottomRight(), nr.bottomLeft()]
            self._h = min(range(4), key=lambda i: QLineF(new[i], pt).length())
        self.update()

    def mouseReleaseEvent(self, e):
        if self._h is None:
            return super().mouseReleaseEvent(e)
        self._h = None
        canvas = getattr(self.scene(), "canvas", None)
        if canvas and self._old:
            canvas.undo.push(StateCmd(self, self._old, self.get_state(), "Resize"))
        self._old = None


class TextItem(QGraphicsTextItem):
    """Chữ / chú thích (callout khi box=True). Nháy đúp để sửa."""

    def __init__(self, pos, color=QColor("red"), font=None, box=False, shadow=False):
        super().__init__()
        self.kind = "callout" if box else "text"
        self.box = box
        self.color = QColor(color)
        self.shadow = shadow
        self.setFont(font or QFont("Sans", 14))
        self.setDefaultTextColor(self.color)
        self.setPos(pos)
        self.setZValue(20)
        flags = QGraphicsItem.GraphicsItemFlag
        self.setFlags(flags.ItemIsSelectable | flags.ItemIsMovable | flags.ItemIsFocusable)
        self._before = None

    def start_edit(self):
        self._before = self.get_state()
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        c = self.textCursor()
        c.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(c)

    def editing(self):
        return self.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction

    def mouseDoubleClickEvent(self, e):
        if not self.editing():
            self.start_edit()
        super().mouseDoubleClickEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        c = self.textCursor()
        c.clearSelection()
        self.setTextCursor(c)
        canvas = getattr(self.scene(), "canvas", None)
        if canvas:
            canvas.text_edit_finished(self, self._before)
        self._before = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            return
        super().keyPressEvent(e)

    def boundingRect(self):
        return super().boundingRect().adjusted(-6, -4, 10, 10)

    def paint(self, p, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = super().boundingRect()
        if self.box:
            box = r.adjusted(-4, -2, 4, 2)
            if self.shadow:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 60))
                p.drawRoundedRect(box.translated(3, 3), 6, 6)
            p.setPen(make_pen(self.color, 2))
            p.setBrush(QColor("#fffbe0"))
            p.drawRoundedRect(box, 6, 6)
        opt = type(option)(option)
        sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        opt.state &= ~QStyle.StateFlag.State_Selected
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(p, opt, widget)
        if sel or self.editing():
            p.setPen(QPen(QColor("#1e74d8"), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r.adjusted(-5, -3, 5, 3))

    def get_state(self):
        return dict(html=self.toHtml(), color=QColor(self.color), font=QFont(self.font()),
                    box=self.box, shadow=self.shadow, pos=QPointF(self.pos()))

    def set_state(self, st):
        self.prepareGeometryChange()
        self.setHtml(st["html"])
        self.color = QColor(st["color"])
        self.setDefaultTextColor(self.color)
        self.setFont(st["font"])
        self.box, self.shadow = st["box"], st["shadow"]
        self.setPos(st["pos"])
        self.update()

    def set_style(self, color=None, width=None, fill=None, shadow=None, font=None):
        self.prepareGeometryChange()
        if color is not None:
            self.color = QColor(color)
            self.setDefaultTextColor(self.color)
            # áp màu cho cả phần chữ đã định dạng
            c = QTextCursor(self.document())
            c.select(QTextCursor.SelectionType.Document)
            fmt = c.charFormat()
            fmt.setForeground(QBrush(self.color))
            c.mergeCharFormat(fmt)
        if shadow is not None:
            self.shadow = shadow
        if font is not None:
            self.setFont(font)
            c = QTextCursor(self.document())
            c.select(QTextCursor.SelectionType.Document)
            fmt = c.charFormat()
            fmt.setFont(font)
            c.mergeCharFormat(fmt)
        self.update()


# ---------- lệnh hoàn tác ----------
class AddCmd(QUndoCommand):
    def __init__(self, scene, item, text="Add"):
        super().__init__(text)
        self.scene, self.item = scene, item

    def redo(self):
        if self.item.scene() is None:
            self.scene.addItem(self.item)

    def undo(self):
        if self.item.scene() is not None:
            self.scene.removeItem(self.item)


class RemoveCmd(QUndoCommand):
    def __init__(self, scene, items, text="Delete"):
        super().__init__(text)
        self.scene, self.items = scene, list(items)

    def redo(self):
        for it in self.items:
            if it.scene() is not None:
                self.scene.removeItem(it)

    def undo(self):
        for it in self.items:
            if it.scene() is None:
                self.scene.addItem(it)


class MoveCmd(QUndoCommand):
    def __init__(self, moves, text="Move"):
        super().__init__(text)
        self.moves = moves  # [(item, old, new)]

    def redo(self):
        for it, _, new in self.moves:
            it.setPos(new)

    def undo(self):
        for it, old, _ in self.moves:
            it.setPos(old)


class StateCmd(QUndoCommand):
    def __init__(self, item, old, new, text="Change"):
        super().__init__(text)
        self.item, self.old, self.new = item, old, new

    def redo(self):
        self.item.set_state(self.new)

    def undo(self):
        self.item.set_state(self.old)


class ImageCmd(QUndoCommand):
    """Thay ảnh nền; nếu flatten thì các đối tượng đã được 'in' vào ảnh mới và bị gỡ khỏi cảnh."""

    def __init__(self, canvas, old, new, items=(), text="Image"):
        super().__init__(text)
        self.canvas, self.old, self.new, self.items = canvas, old, new, list(items)

    def redo(self):
        for it in self.items:
            if it.scene() is not None:
                self.canvas.scene.removeItem(it)
        self.canvas.set_base(self.new)

    def undo(self):
        self.canvas.set_base(self.old)
        for it in self.items:
            if it.scene() is None:
                self.canvas.scene.addItem(it)
