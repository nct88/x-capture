#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$HERE/.." && pwd)"
PROJECT="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null || echo "$SRC")"
VERSION="$(sed -n 's/^Version:[[:space:]]*//p' "$HERE/x-capture.spec")"
TOP="$(mktemp -d)"
trap 'rm -rf "$TOP"' EXIT
mkdir -p "$TOP/SOURCES" "$TOP/x-capture-$VERSION"
cp -r "$SRC/xcapture" "$SRC/data" "$SRC/packaging" "$TOP/x-capture-$VERSION/"
[ -f "$SRC/x-capture" ] && cp "$SRC/x-capture" "$TOP/x-capture-$VERSION/"
find "$TOP/x-capture-$VERSION" \( -name '__pycache__' -o -name '*.pyc' \) \
    -prune -exec rm -rf {} +
tar -C "$TOP" -czf "$TOP/SOURCES/x-capture-$VERSION.tar.gz" "x-capture-$VERSION"
rpmbuild --quiet -bb --define "_topdir $TOP" "$HERE/x-capture.spec"
mkdir -p "$PROJECT/build"
for rpm in "$TOP"/RPMS/noarch/*.rpm; do
    cp "$rpm" "$PROJECT/build/"
    echo "$PROJECT/build/$(basename "$rpm")"
done
