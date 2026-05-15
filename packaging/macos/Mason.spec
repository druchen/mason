# -*- mode: python ; coding: utf-8 -*-
# Run on macOS from repo root: python3 -m PyInstaller packaging/macos/Mason.spec
# Produces dist/Mason.app (with Mason + _internal inside the bundle).

import os
import sys

from PyInstaller.utils.hooks import collect_all

spec_dir = os.path.dirname(os.path.abspath(SPEC))
REPO_ROOT = os.path.abspath(os.path.join(spec_dir, "..", ".."))

APP_VERSION = "0.1.0"
BUNDLE_ID = "org.mason.Mason"

datas_pyside, binaries_pyside, hiddenimports_pyside = collect_all("PySide6")

icon_ico = os.path.join(REPO_ROOT, "assets", "icons", "Mason.ico")
icon_icns = os.path.join(REPO_ROOT, "assets", "icons", "Mason.icns")

datas = list(datas_pyside)
if os.path.isfile(icon_ico):
    datas.append((icon_ico, os.path.join("assets", "icons")))
if os.path.isfile(icon_icns):
    datas.append((icon_icns, os.path.join("assets", "icons")))

if sys.platform != "darwin":
    raise SystemExit("This spec is for macOS only (BUNDLE + .icns). Use packaging/windows/Mason.spec on Windows.")

exe_icon = icon_icns if os.path.isfile(icon_icns) else None

a = Analysis(
    [os.path.join(REPO_ROOT, "main.py")],
    pathex=[REPO_ROOT],
    binaries=list(binaries_pyside),
    datas=datas,
    hiddenimports=list(hiddenimports_pyside),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Mason",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=exe_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Mason",
)

app = BUNDLE(
    coll,
    name="Mason.app",
    icon=exe_icon,
    bundle_identifier=BUNDLE_ID,
    version=APP_VERSION,
    info_plist={
        "CFBundleName": "Mason",
        "CFBundleDisplayName": "Mason",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "NSHighResolutionCapable": "True",
    },
)
