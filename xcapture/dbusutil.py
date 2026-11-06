"""Gọi D-Bus phiên bằng QtDBus, kèm kiểu dữ liệu tường minh (PyQt6 không tự đoán đúng 'as' / 'ai' / 'u')."""
try:
    from PyQt6.QtCore import QMetaType
    from PyQt6.QtDBus import QDBus, QDBusArgument, QDBusConnection, QDBusMessage
    HAVE_QTDBUS = True
except ImportError:  # pragma: no cover
    HAVE_QTDBUS = False


class DBusError(Exception):
    def __init__(self, name, message):
        super().__init__(message)
        self.name = name


def bus():
    return QDBusConnection.sessionBus() if HAVE_QTDBUS else None


def has_service(name):
    b = bus()
    if b is None or not b.isConnected():
        return False
    reply = b.interface().isServiceRegistered(name)
    return bool(reply.value()) if reply.isValid() else False


def call(service, path, iface, method, *args, timeout=5000):
    """Gọi đồng bộ, trả về danh sách giá trị trả về; lỗi D-Bus thành DBusError."""
    m = QDBusMessage.createMethodCall(service, path, iface, method)
    m.setArguments(list(args))
    r = bus().call(m, QDBus.CallMode.Block, timeout)
    if r.type() == QDBusMessage.MessageType.ErrorMessage:
        raise DBusError(r.errorName(), r.errorMessage())
    return r.arguments()


def strings(values):
    a = QDBusArgument()
    a.add(list(values), QMetaType.Type.QStringList.value)
    return a


def ints(values):
    a = QDBusArgument()
    a.beginArray(QMetaType.Type.Int.value)
    for v in values:
        a.add(int(v), QMetaType.Type.Int.value)
    a.endArray()
    return a


def uint(value):
    a = QDBusArgument()
    a.add(int(value), QMetaType.Type.UInt.value)
    return a
