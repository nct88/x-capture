#!/bin/bash
# Copy X-Capture into DESTDIR for .deb / .rpm / Arch packages:
#   /usr/bin/x-capture
#   /usr/share/x-capture/xcapture/
#   /usr/share/applications/x-capture.desktop
#   /usr/share/icons/hicolor/scalable/apps/x-capture.svg
set -euo pipefail
ROOT="${1:?Use: stage.sh DESTDIR}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../xcapture"
DATA="$HERE/../data"

install -d "$ROOT/usr/bin" "$ROOT/usr/share/x-capture" \
    "$ROOT/usr/share/applications" \
    "$ROOT/usr/share/icons/hicolor/scalable/apps"

cp -a "$SRC" "$ROOT/usr/share/x-capture/xcapture"
find "$ROOT/usr/share/x-capture/xcapture" \( -name __pycache__ -o -name '*.pyc' \) \
    -prune -exec rm -rf {} +
find "$ROOT/usr/share/x-capture/xcapture" -type d -exec chmod 755 {} +
find "$ROOT/usr/share/x-capture/xcapture" -type f -exec chmod 644 {} +

install -m 644 "$DATA/x-capture.svg" \
    "$ROOT/usr/share/icons/hicolor/scalable/apps/x-capture.svg"

cat > "$ROOT/usr/bin/x-capture" <<'EOF'
#!/bin/sh
export PYTHONPATH="/usr/share/x-capture${PYTHONPATH:+:$PYTHONPATH}"
export XCAPTURE_EXE=/usr/bin/x-capture
exec python3 -m xcapture "$@"
EOF
chmod 755 "$ROOT/usr/bin/x-capture"

install -m 644 "$DATA/x-capture.desktop" \
    "$ROOT/usr/share/applications/x-capture.desktop"
# System package: KWin ScreenShot2 is allowed for /usr/bin/x-capture.
if ! grep -q X-KDE-DBUS-Restricted-Interfaces "$ROOT/usr/share/applications/x-capture.desktop"; then
    printf '%s\n' "X-KDE-DBUS-Restricted-Interfaces=org.kde.KWin.ScreenShot2" \
        >> "$ROOT/usr/share/applications/x-capture.desktop"
fi
