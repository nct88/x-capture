"""Nhận diện phiên đồ hoạ (X11 / Wayland) và môi trường desktop để chọn cách chụp, phím tắt."""
import os
import shutil


def is_wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE") == "wayland"


def desktops():
    return [d.strip().lower() for d in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if d.strip()]


def is_kde():
    return "kde" in desktops() or os.environ.get("KDE_FULL_SESSION") == "true"


def is_gnome():
    return any(d in ("gnome", "ubuntu", "unity", "pop", "zorin", "pantheon") for d in desktops())


def is_niri():
    return bool(os.environ.get("NIRI_SOCKET")) or "niri" in desktops()


def is_cosmic():
    return "cosmic" in desktops()


def is_wlroots():
    """Sway / Hyprland / river / wayfire / niri / labwc (grim screencopy)."""
    return bool(os.environ.get("SWAYSOCK") or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
                or os.environ.get("NIRI_SOCKET")) or \
        any(d in ("sway", "hyprland", "river", "wayfire", "labwc", "niri") for d in desktops())


def have(cmd):
    return shutil.which(cmd) is not None


def prepare_qt_platform():
    """Trên Wayland, chạy Qt qua XWayland: lớp phủ toàn màn hình, thanh nổi, ghim ảnh cần tự đặt vị trí
    cửa sổ mà Wayland không cho phép. Ảnh màn hình vẫn lấy qua KWin / grim / portal (xem grabber.py).
    Đặt XCAPTURE_QPA=wayland để buộc dùng Wayland gốc.

    Không có DISPLAY (Wayland thuần, không XWayland): để Qt dùng wayland, overlay fullscreen từng output.

    Trả về hàm khôi phục biến môi trường: gọi ngay sau khi tạo QApplication để các chương trình con
    (spectacle, trình sửa ảnh ngoài, xdg-open) không bị ép chạy qua XWayland."""
    old = os.environ.get("QT_QPA_PLATFORM")
    if not is_wayland():
        return lambda: None
    if not os.environ.get("DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", os.environ.get("XCAPTURE_QPA") or "wayland")

        def restore_pure():
            if old is None:
                os.environ.pop("QT_QPA_PLATFORM", None)
            else:
                os.environ["QT_QPA_PLATFORM"] = old
        return restore_pure
    os.environ["QT_QPA_PLATFORM"] = os.environ.get("XCAPTURE_QPA") or "xcb"

    def restore():
        if old is None:
            os.environ.pop("QT_QPA_PLATFORM", None)
        else:
            os.environ["QT_QPA_PLATFORM"] = old
    return restore


def describe():
    kind = "Wayland" if is_wayland() else "X11"
    de = os.environ.get("XDG_CURRENT_DESKTOP") or "?"
    return f"{kind} / {de}"


PACKAGES = {
    "ffmpeg": {"apt": "ffmpeg", "dnf": "ffmpeg-free", "pacman": "ffmpeg", "zypper": "ffmpeg",
               "xbps": "ffmpeg", "apk": "ffmpeg"},
    "tesseract": {"apt": "tesseract-ocr tesseract-ocr-vie", "dnf": "tesseract tesseract-langpack-vie",
                  "pacman": "tesseract tesseract-data-vie",
                  "zypper": "tesseract-ocr tesseract-ocr-traineddata-vietnamese",
                  "xbps": "tesseract tesseract-data-vie", "apk": "tesseract-ocr tesseract-ocr-data-vie"},
    "xlib": {"apt": "python3-xlib", "dnf": "python3-xlib", "pacman": "python-xlib",
             "zypper": "python3-python-xlib", "xbps": "python3-xlib", "apk": "py3-xlib"},
    "grim": {"apt": "grim", "dnf": "grim", "pacman": "grim", "zypper": "grim",
             "xbps": "grim", "apk": "grim"},
    "wf-recorder": {"apt": "wf-recorder", "dnf": "wf-recorder", "pacman": "wf-recorder",
                    "zypper": "wf-recorder", "xbps": "wf-recorder", "apk": "wf-recorder"},
}
INSTALL = {"apt": "sudo apt install", "dnf": "sudo dnf install", "pacman": "sudo pacman -S",
           "zypper": "sudo zypper install", "xbps": "sudo xbps-install -S", "apk": "sudo apk add"}


def package_manager():
    for pm, exe in (("apt", "apt-get"), ("dnf", "dnf"), ("pacman", "pacman"),
                    ("zypper", "zypper"), ("xbps", "xbps-install"), ("apk", "apk")):
        if have(exe):
            return pm
    return None


def install_hint(name):
    """Lệnh cài gói phù hợp với máy, vd. 'sudo dnf install ffmpeg-free'."""
    pm = package_manager()
    pkgs = PACKAGES.get(name, {}).get(pm, name)
    return f"{INSTALL[pm]} {pkgs}" if pm else pkgs
