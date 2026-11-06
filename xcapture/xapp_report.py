"""Mở trang "Báo lỗi / góp ý" của nct88.dev với form điền sẵn thông tin máy.

Dùng chung cho X-Key, X-Capture và cửa sổ X-Office (bản gốc: nct88-dev/release/common/xapp_report.py,
chép vào từng dự án — sửa ở bản gốc rồi chép lại). Chỉ dùng thư viện chuẩn, không cần GUI:

    url = report_url("x-key", "1.0-11")   # → https://nct88.dev/issues/?app=x-key&ver=…#/new
    open_url(url)                         # xdg-open / gio; app GUI nên mở bằng toolkit của mình

Thông tin gửi đi chỉ là: tên app, phiên bản, distro + phiên bản distro, desktop, X11/Wayland. Không gửi
tự động — trình duyệt chỉ mở form, người dùng xem lại rồi tự bấm Gửi.
"""
import os
import shutil
import subprocess
from urllib.parse import urlencode

ISSUES_URL = "https://nct88.dev/issues/"

# ID trong /etc/os-release → mã distro của form web (issues-api/server.mjs: DISTROS).
_DISTRO_IDS = {
    "ubuntu": "ubuntu", "debian": "debian", "linuxmint": "mint", "fedora": "fedora",
    "rhel": "rhel", "almalinux": "rhel", "rocky": "rhel", "centos": "rhel", "ol": "rhel",
    "opensuse": "opensuse", "opensuse-leap": "opensuse", "opensuse-tumbleweed": "opensuse",
    "opensuse-slowroll": "opensuse", "sles": "opensuse", "arch": "arch", "manjaro": "manjaro",
    "manjaro-arm": "manjaro", "endeavouros": "endeavouros", "cachyos": "cachyos", "pop": "popos",
    "zorin": "zorin", "elementary": "elementary", "neon": "neon", "kali": "kali", "nixos": "nixos",
}
# Phần tử của XDG_CURRENT_DESKTOP → mã desktop; xét theo thứ tự này
# ("Budgie:GNOME" là Budgie, "ubuntu:GNOME" là GNOME, "X-Cinnamon" là Cinnamon).
_DESKTOPS = (
    ("kde", "kde"), ("budgie", "budgie"), ("x-cinnamon", "cinnamon"), ("cinnamon", "cinnamon"),
    ("xfce", "xfce"), ("mate", "mate"), ("lxqt", "lxqt"), ("cosmic", "cosmic"), ("sway", "sway"),
    ("hyprland", "hyprland"), ("gnome", "gnome"), ("ubuntu", "gnome"), ("pop", "gnome"),
    ("zorin", "gnome"), ("pantheon", "other"), ("unity", "other"),
)


def read_os_release(path=None):
    """Đọc /etc/os-release (hoặc /usr/lib/os-release) thành dict."""
    for p in ([path] if path else ["/etc/os-release", "/usr/lib/os-release"]):
        try:
            with open(p, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        info = {}
        for line in text.splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and not key.startswith("#"):
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                info[key.strip()] = value
        return info
    return {}


def distro_info(os_release=None):
    """→ (mã distro, phiên bản, tên khi là 'other')."""
    info = os_release if os_release is not None else read_os_release()
    did = info.get("ID", "").lower()
    key = _DISTRO_IDS.get(did) or ("opensuse" if did.startswith("opensuse") else None)
    version = info.get("VERSION_ID", "")[:40]
    if key:
        return key, version, ""
    name = info.get("NAME") or info.get("PRETTY_NAME") or did or "Linux"
    like = info.get("ID_LIKE", "").split()
    if like:
        name = f"{name} ({like[0]})"
    return "other", version, name[:40]


def desktop_key(env=None):
    env = os.environ if env is None else env
    parts = [p.strip().lower() for p in (env.get("XDG_CURRENT_DESKTOP") or env.get("DESKTOP_SESSION") or "").split(":")]
    for token, key in _DESKTOPS:
        if token in parts:
            return key
    return "other"


def session_key(env=None):
    env = os.environ if env is None else env
    kind = (env.get("XDG_SESSION_TYPE") or "").lower()
    if kind in ("wayland", "x11"):
        return kind
    if env.get("WAYLAND_DISPLAY"):
        return "wayland"
    if env.get("DISPLAY"):
        return "x11"
    return "unknown"


def report_url(app, version="", env=None, os_release=None):
    distro, dver, dother = distro_info(os_release)
    params = {"app": app, "ver": version[:40], "distro": distro, "dv": dver,
              "de": desktop_key(env), "session": session_key(env)}
    if dother:
        params["do"] = dother
    return ISSUES_URL + "?" + urlencode({k: v for k, v in params.items() if v}) + "#/new"


def open_url(url):
    """Mở trình duyệt mặc định, không chặn app. → True nếu đã gọi được trình mở."""
    for cmd in (["xdg-open", url], ["gio", "open", url]):
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                return True
            except OSError:
                continue
    try:
        import webbrowser
        return webbrowser.open(url)
    except Exception:
        return False
