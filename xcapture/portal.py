"""Chụp màn hình qua xdg-desktop-portal (GNOME và các phiên Wayland khác không có cách nhanh hơn).
Lần đầu desktop có thể hỏi quyền; GNOME ghi nhớ lựa chọn."""
import os
import secrets
import time
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import QEventLoop, QObject, QTimer, pyqtSlot
from PyQt6.QtGui import QImage

from . import dbusutil as D

PORTAL = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"


def available():
    return D.HAVE_QTDBUS and D.has_service(PORTAL)


class _Response(QObject):
    def __init__(self, loop):
        super().__init__()
        self.loop = loop
        self.result = None

    @pyqtSlot(D.QDBusMessage)
    def on_response(self, msg):
        args = msg.arguments()
        self.result = (int(args[0]), dict(args[1]) if len(args) > 1 else {})
        self.loop.quit()


def screenshot(timeout=60000):
    """QImage của toàn màn hình, hoặc None nếu bị từ chối / hết giờ."""
    b = D.bus()
    token = "xcapture" + secrets.token_hex(6)
    sender = b.baseService().lstrip(":").replace(".", "_")
    req = f"{PATH}/request/{sender}/{token}"
    loop = QEventLoop()
    resp = _Response(loop)
    # nối tín hiệu trước khi gọi để không lỡ phản hồi đến sớm
    b.connect(PORTAL, req, "org.freedesktop.portal.Request", "Response", resp.on_response)
    started = time.time()
    try:
        D.call(PORTAL, PATH, "org.freedesktop.portal.Screenshot", "Screenshot", "",
               {"handle_token": token, "interactive": False}, timeout=10000)
    except D.DBusError:
        return None
    QTimer.singleShot(timeout, loop.quit)
    if resp.result is None:
        loop.exec()
    b.disconnect(PORTAL, req, "org.freedesktop.portal.Request", "Response", resp.on_response)
    if not resp.result or resp.result[0] != 0:
        return None
    uri = resp.result[1].get("uri", "")
    path = unquote(urlparse(uri).path)
    img = QImage(path)
    # portal tự lưu ảnh ra tệp (thường trong ~/Pictures): xoá tệp vừa tạo cho lần chụp này
    try:
        if path and os.path.getmtime(path) >= started - 2:
            os.unlink(path)
    except OSError:
        pass
    return None if img.isNull() else img
