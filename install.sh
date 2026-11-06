#!/bin/bash
# Cài X-Capture cho người dùng hiện tại trên các bản Linux phổ biến
# (Debian/Ubuntu/Mint, Fedora/RHEL, Arch/Manjaro, openSUSE; X11 và Wayland).
#
#   ./install.sh              cài / cập nhật (tự chọn cách cài thư viện)
#   ./install.sh --system     cài thư viện bằng trình quản lý gói của hệ thống (cần sudo)
#   ./install.sh --venv       cài thư viện riêng bằng pip vào ~/.local/share/x-capture/venv (không cần sudo)
#   ./install.sh --yes        không hỏi (đồng ý dùng sudo nếu cần)
#   ./install.sh --uninstall  gỡ bỏ (giữ cấu hình ở ~/.config/x-capture)
#
# Thư viện cần: PyQt6 (kèm QtDBus) và python-xlib. Phần cài đặt chính không cần quyền root:
# nếu không có sudo thì PyQt6 được tải bằng pip vào một môi trường ảo riêng.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/x-capture"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"
AUTOSTART="$HOME/.config/autostart/x-capture.desktop"
VENV="$DEST/venv"

MODE=auto YES=0 ACTION=install
for a in "$@"; do
    case "$a" in
        --uninstall) ACTION=uninstall ;;
        --system) MODE=system ;;
        --venv) MODE=venv ;;
        -y|--yes) YES=1 ;;
        -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Tuỳ chọn không hợp lệ: $a" >&2; exit 2 ;;
    esac
done

say() { printf '→ %s\n' "$*"; }
warn() { printf '! %s\n' "$*" >&2; }

# ---------- nhận diện bản phân phối ----------
FAMILY=unknown
if [ -r /etc/os-release ]; then
    . /etc/os-release
    for id in ${ID:-} ${ID_LIKE:-}; do
        case "$id" in
            debian|ubuntu|linuxmint|pop|elementary|raspbian|kali|zorin|neon) FAMILY=debian; break ;;
            fedora|rhel|centos|rocky|almalinux|nobara|ultramarine) FAMILY=fedora; break ;;
            arch|manjaro|endeavouros|garuda|cachyos|artix) FAMILY=arch; break ;;
            opensuse*|suse|sles) FAMILY=suse; break ;;
        esac
    done
fi
case "$FAMILY" in
    debian) PKG_INSTALL="apt-get install -y"; PKG_HINT="apt install"; DEPS="python3-pyqt6 python3-xlib"
            OPT_FFMPEG="ffmpeg"; OPT_OCR="tesseract-ocr tesseract-ocr-vie" ;;
    fedora) PKG_INSTALL="dnf install -y"; PKG_HINT="dnf install"; DEPS="python3-pyqt6 python3-xlib"
            OPT_FFMPEG="ffmpeg-free"; OPT_OCR="tesseract tesseract-langpack-vie" ;;
    arch)   PKG_INSTALL="pacman -S --needed --noconfirm"; PKG_HINT="pacman -S"; DEPS="python-pyqt6 python-xlib"
            OPT_FFMPEG="ffmpeg"; OPT_OCR="tesseract tesseract-data-vie" ;;
    suse)   PKG_INSTALL="zypper --non-interactive install"; PKG_HINT="zypper install"
            DEPS="python3-PyQt6 python3-python-xlib"
            OPT_FFMPEG="ffmpeg"; OPT_OCR="tesseract-ocr tesseract-ocr-traineddata-vietnamese" ;;
    *)      PKG_INSTALL=""; PKG_HINT=""; DEPS=""; OPT_FFMPEG="ffmpeg"; OPT_OCR="tesseract" ;;
esac
SUDO_HINT() { if [ -n "$PKG_HINT" ]; then echo "sudo $PKG_HINT $*"; else echo "$*"; fi; }

refresh_menus() {
    update-desktop-database "$APPS" 2>/dev/null || true
    gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true
    # KDE: KWin đọc danh mục ứng dụng (sycoca) để cấp quyền chụp màn hình cho X-Capture
    for k in kbuildsycoca6 kbuildsycoca5; do
        command -v "$k" >/dev/null && { "$k" >/dev/null 2>&1 || true; break; }
    done
}

# ---------- gỡ cài đặt ----------
if [ "$ACTION" = uninstall ]; then
    if [ -x "$BIN/x-capture" ]; then
        "$BIN/x-capture" --quit 2>/dev/null || true
        sleep 1
        # trả lại phím tắt đã nhường (KDE / XFCE) và gỡ phím tắt của X-Capture khỏi KDE
        "$BIN/x-capture" --cleanup 2>/dev/null || true
    fi
    rm -rf "$DEST" "$BIN/x-capture" "$APPS/x-capture.desktop" \
        "$ICONS/scalable/apps/x-capture.svg" "$AUTOSTART"
    find "$ICONS" -name 'x-capture.png' -delete 2>/dev/null || true
    refresh_menus
    echo "Đã gỡ X-Capture (cấu hình vẫn giữ ở ~/.config/x-capture)."
    exit 0
fi

# ---------- thư viện Python ----------
need_mods="import PyQt6.QtWidgets, PyQt6.QtNetwork"
have_sys_qt() { python3 -c "$need_mods" 2>/dev/null; }
have_sys_xlib() { python3 -c "import Xlib" 2>/dev/null; }
venv_ok() { [ -x "$VENV/bin/python3" ] && "$VENV/bin/python3" -c "$need_mods" 2>/dev/null; }

command -v python3 >/dev/null || { warn "Cần python3. Cài: $(SUDO_HINT python3)"; exit 1; }
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { warn "Cần Python ≥ 3.9 (đang có $PYV)."; exit 1; }

# phiên đang chạy dùng mã cũ: tắt trước khi chép đè
if [ -x "$BIN/x-capture" ]; then "$BIN/x-capture" --quit 2>/dev/null || true; fi

mkdir -p "$DEST" "$BIN" "$APPS" "$ICONS/scalable/apps"
rm -rf "$DEST/xcapture"
cp -r "$SRC/xcapture" "$DEST/"
cp "$SRC/x-capture" "$DEST/x-capture"
chmod +x "$DEST/x-capture"
find "$DEST/xcapture" -name __pycache__ -prune -exec rm -rf {} +

install_system_deps() {
    [ -n "$PKG_INSTALL" ] || { warn "Không nhận ra trình quản lý gói của bản phân phối này."; return 1; }
    command -v sudo >/dev/null || return 1
    if [ "$YES" = 0 ] && [ "$MODE" != system ]; then
        [ -t 0 ] || return 1
        read -r -p "Cài $DEPS bằng sudo ${PKG_INSTALL%% *}? [Y/n] " ans
        case "${ans:-y}" in [Yy]*) ;; *) return 1 ;; esac
    fi
    say "sudo $PKG_INSTALL $DEPS"
    # shellcheck disable=SC2086
    sudo $PKG_INSTALL $DEPS
}

# venv dùng bản SAO CHÉP trình thông dịch (--copies): KWin xác định ứng dụng theo đường dẫn tệp thực thi,
# nhờ đó tệp .desktop của X-Capture xin được quyền chụp màn hình mà không mở quyền cho mọi chương trình Python.
make_system_venv() {
    rm -rf "$VENV"
    python3 -m venv --copies --system-site-packages --without-pip "$VENV" 2>/dev/null && venv_ok
}
make_pip_venv() {
    if ! venv_ok || [ "$MODE" = venv ]; then
        if ! "$VENV/bin/python3" -c "import pip" 2>/dev/null; then
            rm -rf "$VENV"
            python3 -m venv --copies "$VENV" || return 1
        fi
        say "Tải PyQt6 và python-xlib bằng pip (khoảng 80 MB)..."
        "$VENV/bin/python3" -m pip install --disable-pip-version-check -q --upgrade PyQt6 python-xlib || return 1
    fi
    venv_ok
}
debian_vendor() {
    # Debian không có python3-venv và không có sudo: giải nén gói .deb riêng cho X-Capture (như bản cũ)
    command -v apt-get >/dev/null || return 1
    say "Giải nén thư viện vào $DEST/vendor ..."
    local tmp; tmp=$(mktemp -d)
    (cd "$tmp" && apt-get download python3-pyqt6 python3-pyqt6.sip python3-xlib python3-six) || { rm -rf "$tmp"; return 1; }
    mkdir -p "$tmp/root" "$DEST/vendor"
    for f in "$tmp"/*.deb; do dpkg-deb -x "$f" "$tmp/root"; done
    cp -r "$tmp/root/usr/lib/python3/dist-packages/." "$DEST/vendor/"
    rm -rf "$tmp"
}

# nếu venv cũ hỏng (Python được nâng cấp) thì làm lại
if [ -d "$VENV" ] && ! "$VENV/bin/python3" -c "" 2>/dev/null; then rm -rf "$VENV"; fi

pip_venv_ok() { venv_ok && ! grep -q "include-system-site-packages = true" "$VENV/pyvenv.cfg" 2>/dev/null; }

RUNTIME=""
if [ "$MODE" = venv ]; then
    make_pip_venv && RUNTIME=pip-venv
elif [ "$MODE" = auto ] && ! have_sys_qt && pip_venv_ok; then
    RUNTIME=pip-venv  # lần cài trước đã tải PyQt6 bằng pip: dùng lại, không hỏi sudo nữa
else
    if ! have_sys_qt; then
        install_system_deps || true
    fi
    if have_sys_qt; then
        if venv_ok && [ -f "$VENV/pyvenv.cfg" ] && grep -q "include-system-site-packages = true" "$VENV/pyvenv.cfg"; then
            RUNTIME=system-venv
        elif make_system_venv; then
            RUNTIME=system-venv
        else
            rm -rf "$VENV"; RUNTIME=system
        fi
        have_sys_xlib || warn "Thiếu python-xlib (cần cho phím tắt trên X11): $(SUDO_HINT "${DEPS#* }")"
    elif [ "$MODE" != system ]; then
        if make_pip_venv; then RUNTIME=pip-venv
        elif debian_vendor; then RUNTIME=vendor
        fi
    fi
fi
[ "$RUNTIME" != vendor ] && rm -rf "$DEST/vendor"
if [ -z "$RUNTIME" ]; then
    warn "Không cài được PyQt6. Cài thủ công rồi chạy lại ./install.sh:"
    warn "  $(SUDO_HINT "$DEPS")     hoặc     ./install.sh --venv"
    exit 1
fi
if [ -x "$VENV/bin/python3" ]; then
    # cho phép chạy thẳng "venv/bin/python3 -m xcapture" (lệnh trong tệp .desktop)
    SITE=$("$VENV/bin/python3" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
    echo "$DEST" > "$SITE/x-capture.pth"
    PY="$VENV/bin/python3"
else
    PY=python3
fi
say "Thư viện: $RUNTIME ($("$PY" -c 'from PyQt6.QtCore import QT_VERSION_STR as v; print("Qt", v)'))"

# ---------- lệnh, biểu tượng, menu ----------
ln -sf "$DEST/x-capture" "$BIN/x-capture"
cp "$SRC/data/x-capture.svg" "$ICONS/scalable/apps/x-capture.svg"
# XFCE (theme Tango) hiện icon hỏng nếu chỉ có SVG chưa nằm trong cache; index.theme là điều kiện để
# gtk-update-icon-cache ghi nhận icon mới.
if [ ! -f "$ICONS/index.theme" ] && [ -f /usr/share/icons/hicolor/index.theme ]; then
    cp /usr/share/icons/hicolor/index.theme "$ICONS/index.theme"
fi
PYTHONPATH="$DEST" QT_QPA_PLATFORM=offscreen "$PY" - "$SRC/data/x-capture.svg" "$ICONS" <<'PY' 2>/dev/null || warn "Không tạo được biểu tượng PNG (vẫn dùng SVG)."
import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
app = QGuiApplication(sys.argv[:1])
try:
    from PyQt6.QtSvg import QSvgRenderer
except ImportError:
    QSvgRenderer = None
svg, icons = sys.argv[1], Path(sys.argv[2])
for size in (16, 22, 24, 32, 48, 64, 96, 128, 256, 512):
    dest = icons / f"{size}x{size}" / "apps"
    dest.mkdir(parents=True, exist_ok=True)
    if QSvgRenderer is not None:
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        QSvgRenderer(svg).render(p)
        p.end()
    else:
        img = QImage(svg).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
    if img.isNull() or not img.save(str(dest / "x-capture.png")):
        sys.exit(1)
PY

# Exec trong tệp .desktop: trình thông dịch riêng của X-Capture (để KWin nhận ra) hoặc trình khởi chạy
quote() { case "$1" in *" "*) printf '"%s"' "$1" ;; *) printf '%s' "$1" ;; esac; }
if [ -x "$VENV/bin/python3" ]; then EXEC="$(quote "$VENV/bin/python3") -m xcapture"; else EXEC=$(quote "$BIN/x-capture"); fi
sed -e "s|^Exec=x-capture|Exec=$EXEC|" "$SRC/data/x-capture.desktop" > "$APPS/x-capture.desktop.tmp"
if [ -x "$VENV/bin/python3" ]; then
    # KDE Plasma: cho phép X-Capture dùng KWin ScreenShot2 (chụp màn hình trên Wayland).
    # Dòng này thuộc mục [Desktop Entry]: chèn trước mục [Desktop Action ...] đầu tiên.
    awk 'BEGIN { k = "X-KDE-DBUS-Restricted-Interfaces=org.kde.KWin.ScreenShot2" }
         /^\[Desktop Action/ && !done { print k; print ""; done = 1 }
         { print } END { if (!done) print k }' "$APPS/x-capture.desktop.tmp" > "$APPS/x-capture.desktop"
    rm -f "$APPS/x-capture.desktop.tmp"
else
    mv "$APPS/x-capture.desktop.tmp" "$APPS/x-capture.desktop"
fi
if [ -f "$AUTOSTART" ]; then
    sed -i "s|^Exec=.*|Exec=$BIN/x-capture --tray|" "$AUTOSTART"
fi
refresh_menus

# ---------- tóm tắt ----------
echo
echo "Đã cài X-Capture vào $DEST"
echo "Chạy: x-capture   (hoặc tìm \"X-Capture\" trong menu ứng dụng)"
SESSION="${XDG_SESSION_TYPE:-}"; [ -n "${WAYLAND_DISPLAY:-}" ] && SESSION=wayland
DESK="${XDG_CURRENT_DESKTOP:-}"
if [ "$SESSION" = wayland ]; then
    case ":${DESK,,}:" in
        *:kde:*) echo "  Wayland / KDE: chụp qua KWin, phím tắt đăng ký với KDE (Cài đặt hệ thống → Phím tắt)." ;;
        *:gnome:*|*:ubuntu:*) echo "  Wayland / GNOME: chụp qua xdg-desktop-portal (lần đầu GNOME hỏi quyền)."
            echo "  Phím tắt: Cài đặt → Bàn phím → Phím tắt tuỳ chỉnh → lệnh \"x-capture --rect\"..." ;;
        *) command -v grim >/dev/null || echo "  Wayland (Sway/Hyprland...): cài grim để chụp màn hình: $(SUDO_HINT grim)"
           echo "  Phím tắt: gán trong cấu hình của trình tổng hợp tới lệnh \"x-capture --rect\"..." ;;
    esac
fi
command -v ffmpeg >/dev/null || echo "  Tuỳ chọn – quay phim màn hình (X11): $(SUDO_HINT "$OPT_FFMPEG")"
command -v tesseract >/dev/null || echo "  Tuỳ chọn – nhận dạng chữ (OCR): $(SUDO_HINT "$OPT_OCR")"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "  Lưu ý: thêm $BIN vào PATH để gõ lệnh x-capture." ;; esac
