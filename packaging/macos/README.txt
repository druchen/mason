macOS packaging (Mason)
=====================

Prerequisites
  - macOS with Xcode command line tools (for hdiutil)
  - Python 3.9+ (python.org or Homebrew; Apple CLT Python is fine). If `pip` is not found, use `python3 -m pip` (recommended on macOS).
  - If pip warns that `pyinstaller` is not on PATH, use `python3 -m PyInstaller` (or `build.sh` below).
  - Dependencies:
      python3 -m pip install -r requirements.txt
      python3 -m pip install -r requirements-macos-build.txt
  - Icon: assets/icons/Mason.icns (required for build.sh; optional for spec-only — app icon uses .icns when present)

Frozen app (PyInstaller), from repo root:
  python3 -m PyInstaller packaging/macos/Mason.spec

Output: dist/Mason.app

DMG (UDZO) — from repo root:
  bash packaging/macos/build.sh

Optional: VERSION=1.2.3 bash packaging/macos/build.sh  (default DMG name uses 0.1.0)

Output: dist/Mason_<version>.dmg

Notes
  - This spec exits on non-macOS; use packaging/windows/Mason.spec on Windows.
  - Bump APP_VERSION in packaging/macos/Mason.spec with releases (see packaging/windows/Mason.iss MyAppVersion).
  - Distribution to other Macs usually needs code signing and notarization (not scripted here).
