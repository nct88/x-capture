#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null \
    || dirname "$(cd "$HERE/.." && pwd)")"
PKG=x-capture
VERSION=1.2.0
OUT="$PROJECT/build/${PKG}_${VERSION}_all.deb"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
chmod 755 "$STAGE"

bash "$HERE/stage.sh" "$STAGE"
install -d "$STAGE/DEBIAN" "$STAGE/usr/share/doc/$PKG"
install -m 644 "$HERE/copyright" "$STAGE/usr/share/doc/$PKG/copyright"

cat <<EOF | gzip -9n > "$STAGE/usr/share/doc/$PKG/changelog.Debian.gz"
$PKG ($VERSION) unstable; urgency=medium

  * 1.2.0: desktop hotkeys, niri, Wayland recording. Screen capture for Linux (FastStone Capture style):
    floating toolbar, global hotkeys, annotating editor, pin-to-screen.
    Works on X11 (XFCE, MATE, Cinnamon, KDE) and Wayland (KDE, GNOME, Sway,
    Hyprland).

 -- truongit <lienhe@truong.me>  $(date -R)
EOF
chmod 644 "$STAGE/usr/share/doc/$PKG/"*

SIZE=$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Architecture: all
Maintainer: truongit <lienhe@truong.me>
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-pyqt6, python3-xlib
Recommends: xdotool, ffmpeg, tesseract-ocr, tesseract-ocr-vie, grim, slurp
Suggests: wf-recorder, gimp
Section: graphics
Priority: optional
Homepage: https://github.com/nct88/x-capture
Description: X-Capture — screenshot tool (FastStone Capture style)
 Floating capture toolbar, global hotkeys, annotating editor, pin-to-screen
 and color picker. X11 and Wayland (KWin ScreenShot2, grim, xdg-desktop-portal).
EOF
(cd "$STAGE" && find usr -type f -o -type l | LC_ALL=C sort | while read -r f; do
    [ -f "$f" ] && md5sum "$f"; done) > "$STAGE/DEBIAN/md5sums"
chmod 644 "$STAGE/DEBIAN/control" "$STAGE/DEBIAN/md5sums"

mkdir -p "$(dirname "$OUT")"
fakeroot dpkg-deb --build --root-owner-group "$STAGE" "$OUT" >/dev/null
echo "$OUT"
