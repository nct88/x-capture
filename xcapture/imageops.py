"""Xử lý ảnh (QImage) và lưu tệp."""
import datetime
import os
import random

from PyQt6.QtCore import QMarginsF, QPointF, QRect, QRectF, QSizeF, Qt
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QImage, QImageWriter, QPageLayout,
                         QPageSize, QPainter, QPainterPath, QPdfWriter, QTransform)

ARGB = QImage.Format.Format_ARGB32_Premultiplied


def argb(img):
    return img if img.format() == ARGB else img.convertToFormat(ARGB)


def blank(w, h, color=Qt.GlobalColor.transparent):
    img = QImage(max(1, w), max(1, h), ARGB)
    img.fill(color)
    return img


def soft_blur(img, radius):
    """Làm mờ nhanh bằng thu nhỏ / phóng to nhiều lần (đủ đẹp cho ảnh chụp màn hình)."""
    if radius <= 0:
        return img
    w, h = img.width(), img.height()
    f = max(2, int(radius))
    small = img.scaled(max(1, w // f), max(1, h // f), Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    small = small.scaled(max(1, small.width() // 2 or 1), max(1, small.height() // 2 or 1),
                         Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation) \
        if radius > 6 and small.width() > 4 and small.height() > 4 else small
    return argb(small.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))


def blur_region(img, rect, strength=10):
    rect = rect.intersected(img.rect())
    if rect.isEmpty():
        return None
    out = argb(img.copy())
    part = soft_blur(out.copy(rect), strength)
    p = QPainter(out)
    p.drawImage(rect.topLeft(), part)
    p.end()
    return out


def pixelate_region(img, rect, block=10):
    rect = rect.intersected(img.rect())
    if rect.isEmpty():
        return None
    out = argb(img.copy())
    part = out.copy(rect)
    small = part.scaled(max(1, rect.width() // block), max(1, rect.height() // block),
                        Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    part = small.scaled(rect.width(), rect.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.FastTransformation)
    p = QPainter(out)
    p.drawImage(rect.topLeft(), part)
    p.end()
    return out


def crop(img, rect):
    rect = rect.intersected(img.rect())
    return img.copy(rect) if rect.width() > 1 and rect.height() > 1 else None


def resize(img, w, h):
    return argb(img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))


def rotate(img, deg):
    return argb(img.transformed(QTransform().rotate(deg), Qt.TransformationMode.SmoothTransformation))


def flip(img, horizontal):
    try:
        return img.flipped(Qt.Orientation.Horizontal if horizontal else Qt.Orientation.Vertical)
    except AttributeError:
        return img.mirrored(horizontal, not horizontal)


def grayscale(img):
    return argb(img.convertToFormat(QImage.Format.Format_Grayscale8))


def invert(img):
    out = img.convertToFormat(QImage.Format.Format_ARGB32)
    out.invertPixels(QImage.InvertMode.InvertRgb)
    return argb(out)


def border(img, width, color):
    out = blank(img.width() + 2 * width, img.height() + 2 * width, QColor(color))
    p = QPainter(out)
    p.drawImage(width, width, img)
    p.end()
    return out


def drop_shadow(img, offset=10, blur=12, background=None):
    m = offset + blur * 2
    out = blank(img.width() + m + blur, img.height() + m + blur, QColor(background) if background else Qt.GlobalColor.transparent)
    sh = blank(out.width(), out.height())
    p = QPainter(sh)
    p.fillRect(QRect(blur + offset, blur + offset, img.width(), img.height()), QColor(0, 0, 0, 150))
    p.end()
    sh = soft_blur(sh, max(2, blur // 2))
    p = QPainter(out)
    p.drawImage(0, 0, sh)
    p.drawImage(blur, blur, img)
    p.end()
    return out


def torn_edge(img, sides="b", depth=10, step=14):
    """Cạnh xé giấy cho các cạnh trong sides (t, r, b, l)."""
    w, h = img.width(), img.height()
    rnd = random.Random(w * 31 + h)

    def zig(a, b, fixed, horizontal, inward):
        pts = []
        n = max(2, int(abs(b - a) / step))
        for i in range(n + 1):
            t = a + (b - a) * i / n
            off = rnd.uniform(0.2, 1.0) * depth if i % 2 else rnd.uniform(0, 0.3) * depth
            v = fixed + (off if inward > 0 else -off)
            pts.append(QPointF(t, v) if horizontal else QPointF(v, t))
        return pts

    path = QPainterPath(QPointF(0, 0))
    pts = zig(0, w, 0, True, 1) if "t" in sides else [QPointF(0, 0), QPointF(w, 0)]
    pts += zig(0, h, w, False, -1) if "r" in sides else [QPointF(w, 0), QPointF(w, h)]
    pts += zig(w, 0, h, True, -1) if "b" in sides else [QPointF(w, h), QPointF(0, h)]
    pts += zig(h, 0, 0, False, 1) if "l" in sides else [QPointF(0, h), QPointF(0, 0)]
    for pt in pts:
        path.lineTo(pt)
    path.closeSubpath()
    out = blank(w, h)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setClipPath(path)
    p.drawImage(0, 0, img)
    p.end()
    return out


def caption(img, text, position="bottom", bg="#222222", fg="#ffffff", size=16):
    f = QFont("Sans")
    f.setPixelSize(size)
    fm = QFontMetrics(f)
    lines = text.split("\n")
    bar = fm.height() * len(lines) + size
    out = blank(img.width(), img.height() + bar, QColor(bg))
    p = QPainter(out)
    top = position == "top"
    p.drawImage(0, bar if top else 0, img)
    p.setFont(f)
    p.setPen(QColor(fg))
    r = QRect(8, 0 if top else img.height(), img.width() - 16, bar)
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return out


def apply_mask(img, path):
    """Giữ phần ảnh bên trong path (toạ độ của img), phần ngoài trong suốt."""
    out = blank(img.width(), img.height())
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setClipPath(path)
    p.drawImage(0, 0, img)
    p.end()
    return out


# ---------- lưu tệp ----------
def writable_formats():
    have = {bytes(f).decode().lower() for f in QImageWriter.supportedImageFormats()}
    fmts = [f for f in ("png", "jpg", "bmp", "webp", "tiff", "gif") if f in have or (f == "jpg" and "jpeg" in have)]
    return fmts + ["pdf"]


FILTER_NAMES = {"png": "PNG", "jpg": "JPEG", "bmp": "BMP", "webp": "WebP", "tiff": "TIFF", "gif": "GIF", "pdf": "PDF"}


def file_filters():
    out = []
    for f in writable_formats():
        exts = "*.jpg *.jpeg" if f == "jpg" else ("*.tif *.tiff" if f == "tiff" else f"*.{f}")
        out.append(f"{FILTER_NAMES[f]} ({exts})")
    return out


def save_image(img, path, quality=90):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if ext == "pdf":
        w = QPdfWriter(path)
        w.setResolution(96)
        size_pt = QSizeF(img.width() * 72 / 96, img.height() * 72 / 96)
        w.setPageLayout(QPageLayout(QPageSize(size_pt, QPageSize.Unit.Point), QPageLayout.Orientation.Portrait,
                                    QMarginsF(0, 0, 0, 0)))
        p = QPainter(w)
        p.drawImage(QRectF(0, 0, img.width(), img.height()), img)
        p.end()
        return True
    if ext in ("jpg", "jpeg", "bmp"):
        flat = QImage(img.size(), QImage.Format.Format_RGB32)
        flat.fill(QColor("white"))
        p = QPainter(flat)
        p.drawImage(0, 0, img)
        p.end()
        img = flat
    return img.save(path, None, quality if ext in ("jpg", "jpeg", "webp") else -1)


def auto_filename(cfg, mode="capture"):
    now = datetime.datetime.now()
    name = cfg.get("output/pattern") or "Screenshot_{date}_{time}"
    name = (name.replace("{date}", now.strftime("%Y-%m-%d")).replace("{time}", now.strftime("%H%M%S"))
            .replace("{mode}", mode))
    folder = cfg.output_folder()
    ext = cfg.get("output/format") or "png"
    path = os.path.join(folder, f"{name}.{ext}")
    i = 1
    while os.path.exists(path):
        path = os.path.join(folder, f"{name}_{i}.{ext}")
        i += 1
    return path
