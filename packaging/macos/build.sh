#!/usr/bin/env bash
# Frozen .app (PyInstaller) + compressed DMG. Run from repo root on macOS:
#   bash packaging/macos/build.sh
# Prerequisites: python3 -m pip install -r requirements.txt -r requirements-macos-build.txt

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ICNS="$ROOT/assets/icons/Mason.icns"
if [[ ! -f "$ICNS" ]]; then
  echo "error: missing $ICNS" >&2
  exit 1
fi

echo "Running PyInstaller..."
python3 -m PyInstaller --noconfirm "$ROOT/packaging/macos/Mason.spec"

APP="$ROOT/dist/Mason.app"
if [[ ! -d "$APP" ]]; then
  echo "error: PyInstaller did not produce dist/Mason.app" >&2
  exit 1
fi

DMG="$ROOT/dist/Mason_${VERSION:-0.1.0}.dmg"
echo "Creating DMG: $DMG"
rm -f "$DMG"
hdiutil create -volname "Mason" -srcfolder "$APP" -ov -format UDZO "$DMG"

echo "Done."
echo "  App: $APP"
echo "  DMG: $DMG"
