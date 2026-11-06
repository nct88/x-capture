"""Trình chỉnh sửa ảnh chụp: nhiều thẻ, công cụ chú thích, hiệu ứng, lưu / sao chép / ghim."""
import os
import shlex
import subprocess
import tempfile

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QAction, QActionGroup, QBrush, QColor, QFont, QIcon, QImage, QKeySequence,
                         QPainter, QPixmap, QUndoStack)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
                             QDialogButtonBox, QFileDialog, QFontDialog, QFormLayout, QGraphicsPixmapItem,
                             QGraphicsScene, QGraphicsView, QHBoxLayout, QInputDialog, QLabel,
                             QMainWindow, QMenu, QMessageBox, QSpinBox, QTabWidget, QToolBar,
                             QToolButton, QWidget)

from . import icons, imageops
from .config import config, APP_TITLE
from .i18n import tr
from .items import (AddCmd, AnnoItem, ImageCmd, MoveCmd, RemoveCmd, StateCmd, TextItem)

TOOLS = [
    ("select", "Select / Move (V)", "V"),
    ("arrow", "Arrow (A)", "A"),
    ("line", "Line (L)", "L"),
    ("rectangle", "Rectangle (R)", "R"),
    ("ellipse", "Ellipse (E)", "E"),
    ("pen", "Pen (P)", "P"),
    ("marker", "Highlighter pen (M)", "M"),
    ("highlight", "Highlight area (H)", "H"),
    ("text", "Text (T)", "T"),
    ("callout", "Callout (C)", "C"),
    ("step", "Step number (N)", "N"),
    ("blur", "Blur (B)", "B"),
    ("pixelate", "Pixelate (X)", "X"),
    ("spotlight", "Spotlight (S)", "S"),
    ("crop", "Crop (K)", "K"),
    ("color", "Pick color from image (I)", "I"),
]
TOOL_KIND = {"arrow": "arrow", "line": "line", "rectangle": "rect", "ellipse": "ellipse", "pen": "pen",
             "marker": "marker", "highlight": "highlight", "spotlight": "spotlight",
             "blur": "rubber", "pixelate": "rubber", "crop": "rubber"}
SWATCHES = ["#e53935", "#fb8c00", "#fdd835", "#43a047", "#1e88e5", "#8e24aa", "#000000", "#ffffff"]
ZOOMS = [0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]


def checker_brush():
    pm = QPixmap(16, 16)
    pm.fill(QColor("#6b6f75"))
    p = QPainter(pm)
    p.fillRect(0, 0, 8, 8, QColor("#5f6369"))
    p.fillRect(8, 8, 8, 8, QColor("#5f6369"))
    p.end()
    return QBrush(pm)


class Canvas(QGraphicsView):
    zoomChanged = pyqtSignal(float)
    cursorMoved = pyqtSignal(int, int)

    def __init__(self, editor, image, path=None, title=None):
        super().__init__()
        self.editor = editor
        self.path = path
        self.title = title or (os.path.basename(path) if path else tr("Untitled"))
        self.scene = QGraphicsScene(self)
        self.scene.canvas = self
        self.setScene(self.scene)
        self.base = QGraphicsPixmapItem()
        self.base.setZValue(-1000)
        self.scene.addItem(self.base)
        self.undo = QUndoStack(self)
        self.image = None
        self.set_base(imageops.argb(image))
        self.zoom = 1.0
        self.step = 1
        self._creating = None
        self._moves = None
        self.setBackgroundBrush(checker_brush())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

    # ---------- ảnh nền ----------
    def set_base(self, img):
        self.image = imageops.argb(img)
        self.base.setPixmap(QPixmap.fromImage(self.image))
        self.scene.setSceneRect(QRectF(self.image.rect()))
        self.editor.canvas_changed(self)

    def items_on_top(self):
        return [it for it in self.scene.items() if it is not self.base and it.parentItem() is None]

    def flatten(self):
        sel = self.scene.selectedItems()
        self.scene.clearSelection()
        focus = self.scene.focusItem()
        if focus:
            focus.clearFocus()
        out = imageops.blank(self.image.width(), self.image.height())
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.scene.render(p, QRectF(out.rect()), QRectF(self.image.rect()))
        p.end()
        for it in sel:
            it.setSelected(True)
        return out

    def apply(self, func, flatten=True, text="Image"):
        old = self.image
        src = self.flatten() if flatten else old
        new = func(src)
        if new is None or new.isNull():
            return
        items = self.items_on_top() if flatten else []
        self.undo.push(ImageCmd(self, old, new, items, text))

    def modified(self):
        return not self.undo.isClean()

    # ---------- thu phóng ----------
    def set_zoom(self, z):
        z = max(0.05, min(16.0, z))
        self.zoom = z
        self.resetTransform()
        self.scale(z, z)
        self.base.setTransformationMode(Qt.TransformationMode.SmoothTransformation if z < 1
                                        else Qt.TransformationMode.FastTransformation)
        self.zoomChanged.emit(z)

    def zoom_step(self, up):
        cur = self.zoom
        if up:
            nxt = next((z for z in ZOOMS if z > cur + 1e-3), cur * 1.25)
        else:
            nxt = next((z for z in reversed(ZOOMS) if z < cur - 1e-3), cur / 1.25)
        self.set_zoom(nxt)

    def fit(self):
        vp = self.viewport().size()
        w, h = self.image.width(), self.image.height()
        if w <= 0 or h <= 0:
            return
        if h > 2.5 * w:  # ảnh rất cao (chụp cuộn): vừa chiều ngang để đọc được
            z = min((vp.width() - 30) / w, 1.0)
        else:
            z = min((vp.width() - 20) / w, (vp.height() - 20) / h, 1.0)
        self.set_zoom(max(z, 0.05))

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self.zoom_step(e.angleDelta().y() > 0)
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
            return
        super().wheelEvent(e)

    # ---------- chuột ----------
    def _scene_pos(self, e):
        return self.mapToScene(e.position().toPoint())

    def _clamp(self, pt):
        """Giữ điểm vẽ nằm trong ảnh."""
        return QPointF(min(max(pt.x(), 0.0), float(self.image.width())),
                       min(max(pt.y(), 0.0), float(self.image.height())))

    def mousePressEvent(self, e):
        tool = self.editor.tool
        sp = self._scene_pos(e)
        if e.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            fake = type(e)(e.type(), e.position(), e.globalPosition(), Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton, e.modifiers())
            super().mousePressEvent(fake)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(e)
        under = self.itemAt(e.position().toPoint())
        if tool == "select" or (tool in ("text", "callout") and isinstance(under, TextItem)):
            super().mousePressEvent(e)
            self._moves = {it: QPointF(it.pos()) for it in self.scene.selectedItems()}
            return
        sp = self._clamp(sp)
        st = self.editor.draw_style()
        if tool in ("text", "callout"):
            item = TextItem(sp, st["color"], st["font"], box=(tool == "callout"), shadow=st["shadow"])
            self.undo.push(AddCmd(self.scene, item, tr("Text")))
            self.scene.clearSelection()
            item.setSelected(True)
            item.start_edit()
            item._before = None
            return
        if tool == "step":
            item = AnnoItem("step", sp, st["color"], st["width"], st["fill"], st["shadow"], number=self.step)
            self.step += 1
            self.undo.push(AddCmd(self.scene, item, tr("Step number")))
            self.editor.update_step_label()
            return
        if tool == "color":
            pt = sp.toPoint()
            if self.image.rect().contains(pt):
                self.editor.set_color(QColor(self.flatten().pixel(pt)))
            return
        kind = TOOL_KIND.get(tool)
        if kind:
            self.scene.clearSelection()
            item = AnnoItem(kind, sp, st["color"], st["width"], st["fill"], st["shadow"])
            self.scene.addItem(item)
            self._creating = item

    def mouseMoveEvent(self, e):
        sp = self._scene_pos(e)
        self.cursorMoved.emit(int(sp.x()), int(sp.y()))
        if self._creating:
            self._creating.drag_to(self._clamp(sp), bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            fake = type(e)(e.type(), e.position(), e.globalPosition(), Qt.MouseButton.LeftButton,
                           Qt.MouseButton.NoButton, e.modifiers())
            super().mouseReleaseEvent(fake)
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            return
        item, self._creating = self._creating, None
        if item:
            tool = self.editor.tool
            if item.kind == "rubber":
                rect = item.rect().toAlignedRect()
                self.scene.removeItem(item)
                if rect.width() > 2 and rect.height() > 2:
                    if tool == "crop":
                        self.apply(lambda im: imageops.crop(im, rect), True, tr("Crop"))
                        QTimer.singleShot(0, self.fit_if_needed)
                    elif tool == "blur":
                        self.apply(lambda im: imageops.blur_region(im, rect, 10), False, tr("Blur"))
                    elif tool == "pixelate":
                        self.apply(lambda im: imageops.pixelate_region(im, rect, 10), False, tr("Pixelate"))
                return
            if item.is_trivial():
                self.scene.removeItem(item)
                return
            self.undo.push(AddCmd(self.scene, item, tr("Draw")))
            return
        super().mouseReleaseEvent(e)
        if self._moves:
            moves = [(it, old, QPointF(it.pos())) for it, old in self._moves.items()
                     if it.scene() is not None and it.pos() != old]
            if moves:
                self.undo.push(MoveCmd(moves, tr("Move")))
        self._moves = None

    def fit_if_needed(self):
        vp = self.viewport().size()
        tall = self.image.height() > 2.5 * self.image.width()
        if self.image.width() * self.zoom > vp.width() or \
                (not tall and self.image.height() * self.zoom > vp.height()):
            self.fit()
            if tall:
                self.verticalScrollBar().setValue(0)

    def keyPressEvent(self, e):
        focus = self.scene.focusItem()
        if isinstance(focus, TextItem) and focus.editing():
            return super().keyPressEvent(e)
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            return
        if e.key() == Qt.Key.Key_Escape:
            self.scene.clearSelection()
            return
        arrows = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if e.key() in arrows and self.scene.selectedItems():
            dx, dy = arrows[e.key()]
            n = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            moves = [(it, QPointF(it.pos()), it.pos() + QPointF(dx * n, dy * n)) for it in self.scene.selectedItems()]
            self.undo.push(MoveCmd(moves, tr("Move")))
            return
        super().keyPressEvent(e)

    def delete_selected(self):
        items = self.scene.selectedItems()
        if items:
            self.undo.push(RemoveCmd(self.scene, items, tr("Delete")))

    def text_edit_finished(self, item, before):
        if not item.toPlainText().strip():
            # chữ rỗng: gỡ khỏi cảnh và bỏ lệnh "thêm"
            if self.undo.count() and self.undo.command(self.undo.index() - 1) and \
                    getattr(self.undo.command(self.undo.index() - 1), "item", None) is item:
                self.undo.undo()
            elif item.scene():
                self.undo.push(RemoveCmd(self.scene, [item]))
            return
        if before and before["html"] != item.toHtml():
            self.undo.push(StateCmd(item, before, item.get_state(), tr("Edit text")))

    def apply_style(self, **kw):
        items = self.scene.selectedItems()
        if not items:
            return
        self.undo.beginMacro(tr("Change style"))
        for it in items:
            old = it.get_state()
            it.set_style(**kw) if isinstance(it, TextItem) else it.set_style(
                **{k: v for k, v in kw.items() if k != "font"})
            self.undo.push(StateCmd(it, old, it.get_state()))
        self.undo.endMacro()


class ResizeDialog(QDialog):
    def __init__(self, parent, w, h):
        super().__init__(parent)
        self.setWindowTitle(tr("Resize"))
        self.ratio = w / h if h else 1
        lay = QFormLayout(self)
        self.sw, self.sh, self.pct = QSpinBox(), QSpinBox(), QSpinBox()
        for s in (self.sw, self.sh):
            s.setRange(1, 30000)
        self.pct.setRange(1, 1000)
        self.pct.setSuffix(" %")
        self.sw.setValue(w)
        self.sh.setValue(h)
        self.pct.setValue(100)
        self.keep = QCheckBox(tr("Keep aspect ratio"))
        self.keep.setChecked(True)
        lay.addRow(tr("Percent"), self.pct)
        lay.addRow(tr("Width (px)"), self.sw)
        lay.addRow(tr("Height (px)"), self.sh)
        lay.addRow(self.keep)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)
        self._w0, self._h0 = w, h
        self._lock = False
        self.pct.valueChanged.connect(self._from_pct)
        self.sw.valueChanged.connect(lambda v: self._link(self.sw, v))
        self.sh.valueChanged.connect(lambda v: self._link(self.sh, v))

    def _from_pct(self, v):
        if self._lock:
            return
        self._lock = True
        self.sw.setValue(max(1, round(self._w0 * v / 100)))
        self.sh.setValue(max(1, round(self._h0 * v / 100)))
        self._lock = False

    def _link(self, src, v):
        if self._lock or not self.keep.isChecked():
            return
        self._lock = True
        if src is self.sw:
            self.sh.setValue(max(1, round(v / self.ratio)))
        else:
            self.sw.setValue(max(1, round(v * self.ratio)))
        self._lock = False


class EditorWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.tool = "select"
        self.color = QColor(config.get("editor/color"))
        self.font_ = QFont()
        self.font_.fromString(config.get("editor/font"))
        self.setWindowTitle(tr("Editor"))
        self.setWindowIcon(icons.icon("app"))
        self.setAcceptDrops(True)
        scr = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1280, int(scr.width() * 0.8)), min(860, int(scr.height() * 0.85)))
        geo = config.get("editor/geometry")
        if geo:
            self.restoreGeometry(geo)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setIconSize(QSize(32, 24))
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)
        empty = QLabel(tr("Capture something or drop an image here"))
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet("color:#888; font-size:16px;")
        self.empty = empty
        self.setCentralWidget(self.tabs)
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_status()
        self._update_actions()

    # ---------- dựng giao diện ----------
    def _act(self, text, icon=None, shortcut=None, slot=None, checkable=False):
        a = QAction(tr(text), self)
        if icon:
            a.setIcon(icons.icon(icon))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if slot:
            a.triggered.connect(slot)
        a.setCheckable(checkable)
        a.setToolTip(tr(text) + (f" ({QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)})"
                                 if shortcut else ""))
        self.addAction(a)
        return a

    def _build_actions(self):
        A = self._act
        self.a_open = A("Open...", "open", QKeySequence.StandardKey.Open, self.open_files)
        self.a_save = A("Save", "save", QKeySequence.StandardKey.Save, lambda: self.save())
        self.a_saveas = A("Save As...", "saveas", "Ctrl+Shift+S", lambda: self.save(ask=True))
        self.a_quicksave = A("Quick Save (auto name)", "file", "Ctrl+Alt+S", self.quick_save)
        self.a_copy = A("Copy Image", "copy", "Ctrl+Shift+C", self.copy_image)
        self.a_paste = A("Paste as New Image", "paste", "Ctrl+Shift+V", self.paste_new)
        self.a_pin = A("Pin to Screen", "pin", "Ctrl+P", self.pin_current)
        self.a_external = A("Open with External Editor", "external", "Ctrl+E", self.open_external)
        self.a_folder = A("Open Containing Folder", "folder", None, self.open_folder)
        self.a_close = A("Close Tab", None, QKeySequence.StandardKey.Close, lambda: self.close_tab(self.tabs.currentIndex()))
        self.a_undo = A("Undo", "undo", QKeySequence.StandardKey.Undo, lambda: self.cv and self.cv.undo.undo())
        self.a_redo = A("Redo", "redo", "Ctrl+Y", lambda: self.cv and self.cv.undo.redo())
        self.a_redo2 = A("Redo", None, "Ctrl+Shift+Z", lambda: self.cv and self.cv.undo.redo())
        self.a_delete = A("Delete Object", "delete", None, lambda: self.cv and self.cv.delete_selected())
        self.a_selall = A("Select All Objects", None, QKeySequence.StandardKey.SelectAll, self.select_all)
        self.a_zin = A("Zoom In", "zoomin", "Ctrl+=", lambda: self.cv and self.cv.zoom_step(True))
        self.a_zin2 = A("Zoom In", None, "Ctrl++", lambda: self.cv and self.cv.zoom_step(True))
        self.a_zout = A("Zoom Out", "zoomout", "Ctrl+-", lambda: self.cv and self.cv.zoom_step(False))
        self.a_z100 = A("Actual Size", "zoom100", "Ctrl+0", lambda: self.cv and self.cv.set_zoom(1.0))
        self.a_zfit = A("Fit to Window", "zoomfit", "Ctrl+9", lambda: self.cv and self.cv.fit())
        self.a_resize = A("Resize...", "resize", "Ctrl+R", self.resize_image)
        self.a_rotl = A("Rotate Left", "rotl", "Ctrl+L", lambda: self._op(lambda im: imageops.rotate(im, -90)))
        self.a_rotr = A("Rotate Right", "rotr", None, lambda: self._op(lambda im: imageops.rotate(im, 90)))
        self.a_fliph = A("Flip Horizontal", "fliph", None, lambda: self._op(lambda im: imageops.flip(im, True)))
        self.a_flipv = A("Flip Vertical", "flipv", None, lambda: self._op(lambda im: imageops.flip(im, False)))
        self.a_border = A("Add Border...", "border", None, self.add_border)
        self.a_shadow = A("Drop Shadow", "shadow", None, lambda: self._op(lambda im: imageops.drop_shadow(im)))
        self.a_torn = A("Torn Edge", "torn", None, self.torn_edge)
        self.a_caption = A("Add Caption...", "caption", None, self.add_caption)
        self.a_gray = A("Grayscale", "gray", None, lambda: self._op(imageops.grayscale))
        self.a_invert = A("Invert Colors", "invert", None, lambda: self._op(imageops.invert))
        self.a_ocr = A("Extract Text (OCR)", "ocr", None, self.ocr_current)
        self.doc_actions = [self.a_save, self.a_saveas, self.a_quicksave, self.a_copy, self.a_pin, self.a_external,
                            self.a_folder, self.a_close, self.a_undo, self.a_redo, self.a_delete, self.a_zin,
                            self.a_zout, self.a_z100, self.a_zfit, self.a_resize, self.a_rotl, self.a_rotr,
                            self.a_fliph, self.a_flipv, self.a_border, self.a_shadow, self.a_torn,
                            self.a_caption, self.a_gray, self.a_invert, self.a_ocr]
        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        for name, label, key in TOOLS:
            a = self._act(label, name, key, checkable=True)
            a.triggered.connect(lambda _=False, n=name: self.set_tool(n))
            self.tool_group.addAction(a)
            self.tool_actions[name] = a
        self.tool_actions["select"].setChecked(True)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu(tr("&File"))
        for a in (self.a_open, self.a_paste, None, self.a_save, self.a_saveas, self.a_quicksave, None,
                  self.a_copy, self.a_pin, self.a_external, self.a_folder, None, self.a_close):
            m.addSeparator() if a is None else m.addAction(a)
        m.addSeparator()
        m.addAction(icons.icon("close"), tr("Close Editor"), self.close)
        m = mb.addMenu(tr("&Edit"))
        for a in (self.a_undo, self.a_redo, None, self.a_delete, self.a_selall):
            m.addSeparator() if a is None else m.addAction(a)
        self.capture_menu = mb.addMenu(tr("&Capture"))
        self.app.dynamic_capture_menu(self.capture_menu)
        m = mb.addMenu(tr("&View"))
        for a in (self.a_zin, self.a_zout, self.a_z100, self.a_zfit):
            m.addAction(a)
        m = mb.addMenu(tr("&Image"))
        for a in (self.a_resize, None, self.a_rotl, self.a_rotr, self.a_fliph, self.a_flipv, None,
                  self.a_border, self.a_shadow, self.a_torn, self.a_caption, None, self.a_gray, self.a_invert):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu(tr("&Draw"))
        for name, _, _ in TOOLS:
            m.addAction(self.tool_actions[name])
        m = mb.addMenu(tr("&Tools"))
        m.addAction(self.a_ocr)
        self.app.fill_tools_menu(m)
        m = mb.addMenu(tr("&Help"))
        m.addAction(icons.icon("app"), tr("About X-Capture"), self.app.about)

    def _build_toolbars(self):
        tb = QToolBar(tr("Main"))
        tb.setObjectName("main")
        tb.setIconSize(QSize(26, 26))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        cap = QToolButton()
        cap.setText(tr("Capture"))
        cap.setIcon(icons.icon("rect"))
        cap.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        cap.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        cap.setMenu(self.capture_menu)
        cap.clicked.connect(lambda: self.app.capture("rect"))
        tb.addWidget(cap)
        tb.addSeparator()
        for a in (self.a_open, self.a_save, self.a_saveas, self.a_copy, self.a_pin, None, self.a_undo,
                  self.a_redo, None, self.a_resize, self.a_rotl, self.a_rotr, self.a_border, self.a_shadow,
                  self.a_torn, self.a_caption, None, self.a_external, self.a_ocr):
            tb.addSeparator() if a is None else tb.addAction(a)
        self._short_text(tb)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self.addToolBarBreak()

        pb = QToolBar(tr("Properties"))
        pb.setObjectName("props")
        pb.setIconSize(QSize(20, 20))
        self.color_btn = QToolButton()
        self.color_btn.setToolTip(tr("Color"))
        self.color_btn.clicked.connect(self.choose_color)
        pb.addWidget(QLabel(" " + tr("Color") + ": "))
        pb.addWidget(self.color_btn)
        for c in SWATCHES:
            b = QToolButton()
            b.setFixedSize(20, 20)
            b.setStyleSheet(f"QToolButton{{background:{c};border:1px solid #777;border-radius:3px;}}")
            b.clicked.connect(lambda _=False, col=c: self.set_color(QColor(col)))
            pb.addWidget(b)
        pb.addSeparator()
        pb.addWidget(QLabel(" " + tr("Width") + ": "))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 40)
        self.width_spin.setValue(config.get("editor/width"))
        self.width_spin.valueChanged.connect(self._width_changed)
        pb.addWidget(self.width_spin)
        self.fill_chk = QCheckBox(tr("Fill"))
        self.fill_chk.setChecked(config.get("editor/fill"))
        self.fill_chk.toggled.connect(lambda v: (config.set("editor/fill", v), self.cv and self.cv.apply_style(fill=v)))
        self.shadow_chk = QCheckBox(tr("Shadow"))
        self.shadow_chk.setChecked(config.get("editor/shadow"))
        self.shadow_chk.toggled.connect(lambda v: (config.set("editor/shadow", v), self.cv and self.cv.apply_style(shadow=v)))
        pb.addWidget(self.fill_chk)
        pb.addWidget(self.shadow_chk)
        pb.addSeparator()
        self.font_btn = QToolButton()
        self.font_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.font_btn.clicked.connect(self.choose_font)
        pb.addWidget(QLabel(" " + tr("Font") + ": "))
        pb.addWidget(self.font_btn)
        pb.addSeparator()
        self.step_lbl = QToolButton()
        self.step_lbl.setToolTip(tr("Click to reset the step counter"))
        self.step_lbl.clicked.connect(self.reset_step)
        pb.addWidget(self.step_lbl)
        pb.addSeparator()
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        for z in ZOOMS:
            self.zoom_combo.addItem(f"{round(z * 100)}%")
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.lineEdit().returnPressed.connect(self._zoom_typed)
        self.zoom_combo.activated.connect(lambda i: self.cv and self.cv.set_zoom(ZOOMS[i]))
        pb.addAction(self.a_zout)
        pb.addWidget(self.zoom_combo)
        pb.addAction(self.a_zin)
        pb.addAction(self.a_z100)
        pb.addAction(self.a_zfit)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, pb)
        self._refresh_style_widgets()

        db = QToolBar(tr("Draw"))
        db.setObjectName("draw")
        db.setIconSize(QSize(24, 24))
        for name, _, _ in TOOLS:
            db.addAction(self.tool_actions[name])
            if name in ("select", "marker", "step", "spotlight"):
                db.addSeparator()
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, db)

    def _short_text(self, tb):
        short = {self.a_saveas: "Save As", self.a_copy: "Copy", self.a_pin: "Pin", self.a_open: "Open",
                 self.a_resize: "Resize", self.a_border: "Border", self.a_shadow: "Shadow",
                 self.a_torn: "Torn Edge", self.a_caption: "Caption", self.a_external: "Edit With",
                 self.a_ocr: "OCR", self.a_rotl: "Rotate L", self.a_rotr: "Rotate R"}
        for a, t in short.items():
            a.setIconText(tr(t))

    def _build_status(self):
        sb = self.statusBar()
        self.st_size = QLabel()
        self.st_zoom = QLabel()
        self.st_pos = QLabel()
        self.st_path = QLabel()
        for w in (self.st_size, self.st_zoom, self.st_pos):
            w.setMinimumWidth(90)
            sb.addPermanentWidget(w)
        sb.addWidget(self.st_path, 1)

    # ---------- trạng thái ----------
    @property
    def cv(self):
        w = self.tabs.currentWidget()
        return w if isinstance(w, Canvas) else None

    def canvases(self):
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def canvas_changed(self, cv):
        i = self.tabs.indexOf(cv)
        if i >= 0:
            thumb = QPixmap.fromImage(cv.image.scaled(64, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                                      Qt.TransformationMode.SmoothTransformation))
            self.tabs.setTabIcon(i, QIcon(thumb))
        if cv is self.cv:
            self._update_status()

    def _tab_title(self, cv):
        i = self.tabs.indexOf(cv)
        if i >= 0:
            self.tabs.setTabText(i, ("● " if cv.modified() else "") + cv.title)
            self.tabs.setTabToolTip(i, cv.path or cv.title)

    def _tab_changed(self, _):
        self._update_actions()
        self._update_status()
        self.update_step_label()

    def _update_actions(self):
        has = self.cv is not None
        for a in self.doc_actions:
            a.setEnabled(has)
        if has:
            self.a_undo.setEnabled(self.cv.undo.canUndo())
            self.a_redo.setEnabled(self.cv.undo.canRedo())
        self.a_folder.setEnabled(has and bool(self.cv.path))

    def _update_status(self):
        cv = self.cv
        if not cv:
            for w in (self.st_size, self.st_zoom, self.st_pos, self.st_path):
                w.setText("")
            return
        self.st_size.setText(f"{cv.image.width()} × {cv.image.height()}")
        self.st_zoom.setText(f"{round(cv.zoom * 100)}%")
        self.zoom_combo.setCurrentText(f"{round(cv.zoom * 100)}%")
        self.st_path.setText(cv.path or tr("Not saved"))

    def update_step_label(self):
        n = self.cv.step if self.cv else 1
        self.step_lbl.setText(tr("Next step") + f": {n}")

    def reset_step(self):
        if self.cv:
            self.cv.step = 1
            self.update_step_label()

    def _zoom_typed(self):
        txt = self.zoom_combo.currentText().strip().rstrip("%")
        try:
            if self.cv:
                self.cv.set_zoom(float(txt) / 100)
        except ValueError:
            pass

    def draw_style(self):
        return dict(color=QColor(self.color), width=self.width_spin.value(), fill=self.fill_chk.isChecked(),
                    shadow=self.shadow_chk.isChecked(), font=QFont(self.font_))

    def _refresh_style_widgets(self):
        pm = QPixmap(22, 22)
        pm.fill(self.color)
        self.color_btn.setIcon(QIcon(pm))
        self.font_btn.setText(f"{self.font_.family()} {self.font_.pointSize()}")

    def set_color(self, c):
        if not c.isValid():
            return
        self.color = QColor(c)
        config.set("editor/color", self.color.name())
        self._refresh_style_widgets()
        if self.cv:
            self.cv.apply_style(color=self.color)

    def choose_color(self):
        c = QColorDialog.getColor(self.color, self, tr("Color"), QColorDialog.ColorDialogOption.ShowAlphaChannel)
        self.set_color(c)

    def choose_font(self):
        f, ok = QFontDialog.getFont(self.font_, self, tr("Font"))
        if ok:
            self.font_ = f
            config.set("editor/font", f.toString())
            self._refresh_style_widgets()
            if self.cv:
                self.cv.apply_style(font=f)

    def _width_changed(self, v):
        config.set("editor/width", v)
        if self.cv:
            self.cv.apply_style(width=v)

    def set_tool(self, name):
        self.tool = name
        self.tool_actions[name].setChecked(True)
        for cv in self.canvases():
            cv.setDragMode(QGraphicsView.DragMode.RubberBandDrag if name == "select"
                           else QGraphicsView.DragMode.NoDrag)
            cv.viewport().setCursor(Qt.CursorShape.ArrowCursor if name == "select" else Qt.CursorShape.CrossCursor)

    def select_all(self):
        if self.cv:
            for it in self.cv.items_on_top():
                it.setSelected(True)

    # ---------- thẻ / ảnh ----------
    def add_image(self, img, title=None, path=None):
        cv = Canvas(self, img, path, title)
        cv.undo.cleanChanged.connect(lambda _=None, c=cv: (self._tab_title(c), self._update_actions()))
        cv.undo.indexChanged.connect(lambda _=None, c=cv: (self._tab_title(c), self._update_actions()))
        cv.zoomChanged.connect(lambda _=None: self._update_status())
        cv.cursorMoved.connect(lambda x, y: self.st_pos.setText(f"{x}, {y}"))
        i = self.tabs.addTab(cv, cv.title)
        self._tab_title(cv)
        self.canvas_changed(cv)
        self.tabs.setCurrentIndex(i)
        self.set_tool(self.tool)
        QTimer.singleShot(0, cv.fit_if_needed)
        self._update_actions()
        return cv

    def open_files(self):
        exts = " ".join(f"*.{e}" for e in ("png", "jpg", "jpeg", "bmp", "gif", "webp", "tif", "tiff", "ico", "ppm"))
        files, _ = QFileDialog.getOpenFileNames(self, tr("Open Images"), config.output_folder(),
                                                f"{tr('Images')} ({exts});;{tr('All files')} (*)")
        for f in files:
            self.open_path(f)

    def open_path(self, f):
        img = QImage(f)
        if img.isNull():
            QMessageBox.warning(self, APP_TITLE, tr("Cannot open file:") + f"\n{f}")
            return
        self.add_image(img, path=f)
        self.show_editor()

    def paste_new(self):
        img = QApplication.clipboard().image()
        if img.isNull():
            QMessageBox.information(self, APP_TITLE, tr("The clipboard does not contain an image."))
            return
        self.add_image(img, tr("Clipboard"))

    def close_tab(self, i):
        cv = self.tabs.widget(i)
        if not isinstance(cv, Canvas):
            return True
        if cv.modified():
            self.tabs.setCurrentIndex(i)
            SB = QMessageBox.StandardButton
            box = QMessageBox(QMessageBox.Icon.Question, APP_TITLE, tr("Save changes to") + f" \"{cv.title}\"?",
                              SB.Save | SB.Discard | SB.Cancel, self)
            for b, t in ((SB.Save, "Save"), (SB.Discard, "Don't Save"), (SB.Cancel, "Cancel")):
                box.button(b).setText(tr(t))
            r = SB(box.exec())
            if r == QMessageBox.StandardButton.Cancel:
                return False
            if r == QMessageBox.StandardButton.Save and not self.save(cv):
                return False
        self.tabs.removeTab(i)
        # ~QUndoStack phát indexChanged lúc Canvas đang bị huỷ → slot gọi vào đối tượng đã xoá
        # và PyQt6 abort cả ứng dụng. Ngắt tín hiệu trước khi xoá.
        cv.undo.blockSignals(True)
        cv.deleteLater()
        self._update_actions()
        return True

    def closeEvent(self, e):
        config.set("editor/geometry", self.saveGeometry())
        while self.tabs.count():
            if not self.close_tab(self.tabs.count() - 1):
                e.ignore()
                return
        e.accept()

    def shutdown(self):
        """Ứng dụng thoát khi còn thẻ mở (đăng xuất...): ngắt tín hiệu của ngăn hoàn tác, nếu không
        chúng phát ra lúc cửa sổ đang bị huỷ và gọi vào thẻ đã xoá (Python bị abort)."""
        for cv in self.canvases():
            cv.undo.blockSignals(True)

    def show_editor(self):
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()

    # ---------- lưu / xuất ----------
    def save(self, cv=None, ask=False):
        cv = cv or self.cv
        if not cv:
            return False
        path = cv.path
        if ask or not path or os.path.splitext(path)[1].lower().lstrip(".") not in imageops.writable_formats() + ["jpeg", "tif"]:
            suggested = path or imageops.auto_filename(config)
            filters = imageops.file_filters()
            ext = os.path.splitext(suggested)[1].lower().lstrip(".")
            sel = next((f for f in filters if f"*.{ext}" in f), filters[0])
            path, _ = QFileDialog.getSaveFileName(self, tr("Save As"), suggested, ";;".join(filters), sel)
            if not path:
                return False
            if not os.path.splitext(path)[1]:
                path += "." + (config.get("output/format") or "png")
        if not imageops.save_image(cv.flatten(), path, config.get("output/jpeg_quality")):
            QMessageBox.warning(self, APP_TITLE, tr("Could not save the file:") + f"\n{path}")
            return False
        cv.path = path
        cv.title = os.path.basename(path)
        cv.undo.setClean()
        self._tab_title(cv)
        self._update_status()
        self._update_actions()
        self.statusBar().showMessage(tr("Saved") + f": {path}", 4000)
        return True

    def quick_save(self):
        cv = self.cv
        if not cv:
            return
        path = imageops.auto_filename(config)
        if imageops.save_image(cv.flatten(), path, config.get("output/jpeg_quality")):
            cv.path, cv.title = path, os.path.basename(path)
            cv.undo.setClean()
            self._tab_title(cv)
            self._update_status()
            self._update_actions()
            self.statusBar().showMessage(tr("Saved") + f": {path}", 4000)

    def current_image(self):
        return self.cv.flatten() if self.cv else None

    def copy_image(self):
        img = self.current_image()
        if img is not None:
            QApplication.clipboard().setImage(img)
            self.statusBar().showMessage(tr("Image copied to clipboard"), 3000)

    def pin_current(self):
        img = self.current_image()
        if img is not None:
            self.app.pin(img)

    def open_external(self):
        cv = self.cv
        if not cv:
            return
        cmd = config.get("editor/external") or "xdg-open %f"
        if cv.path and not cv.modified():
            path = cv.path
        else:
            fd, path = tempfile.mkstemp(prefix="x-capture-", suffix=".png")
            os.close(fd)
            imageops.save_image(cv.flatten(), path)
        args = [a.replace("%f", path) for a in shlex.split(cmd)]
        if "%f" not in cmd:
            args.append(path)
        try:
            subprocess.Popen(args, start_new_session=True)
        except OSError as ex:
            QMessageBox.warning(self, APP_TITLE, tr("Cannot start external editor:") + f"\n{ex}")

    def open_folder(self):
        if self.cv and self.cv.path:
            subprocess.Popen(["xdg-open", os.path.dirname(self.cv.path)], start_new_session=True)

    def ocr_current(self):
        img = self.current_image()
        if img is not None:
            self.app.run_ocr(img)

    # ---------- thao tác ảnh ----------
    def _op(self, func, text="Image"):
        if self.cv:
            self.cv.apply(func, True, tr(text))
            QTimer.singleShot(0, self.cv.fit_if_needed)

    def resize_image(self):
        cv = self.cv
        if not cv:
            return
        d = ResizeDialog(self, cv.image.width(), cv.image.height())
        if d.exec():
            w, h = d.sw.value(), d.sh.value()
            self._op(lambda im: imageops.resize(im, w, h), "Resize")

    def add_border(self):
        if not self.cv:
            return
        w, ok = QInputDialog.getInt(self, tr("Add Border"), tr("Border width (px):"), 4, 1, 200)
        if ok:
            c = QColorDialog.getColor(self.color, self, tr("Border color"))
            if c.isValid():
                self._op(lambda im: imageops.border(im, w, c), "Border")

    def torn_edge(self):
        if not self.cv:
            return
        items = [tr("Bottom"), tr("Right"), tr("Bottom + Right"), tr("All sides")]
        it, ok = QInputDialog.getItem(self, tr("Torn Edge"), tr("Edges:"), items, 0, False)
        if ok:
            sides = {0: "b", 1: "r", 2: "br", 3: "trbl"}[items.index(it)]
            self._op(lambda im: imageops.drop_shadow(imageops.torn_edge(im, sides), 6, 8), "Torn Edge")

    def add_caption(self):
        if not self.cv:
            return
        text, ok = QInputDialog.getMultiLineText(self, tr("Add Caption"), tr("Caption text:"))
        if ok and text.strip():
            self._op(lambda im: imageops.caption(im, text.strip()), "Caption")

    # ---------- kéo thả ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        if md.hasUrls():
            for u in md.urls():
                if u.isLocalFile():
                    self.open_path(u.toLocalFile())
        elif md.hasImage():
            self.add_image(QImage(md.imageData()), tr("Dropped image"))
