# -*- mode: python ; coding: utf-8 -*-
# Run from repo root: pyinstaller packaging/windows/Mason.spec
# Produces dist/Mason/ (onedir) with Mason.exe + _internal/.

import os

from PyInstaller.utils.hooks import collect_all

spec_dir = os.path.dirname(os.path.abspath(SPEC))
REPO_ROOT = os.path.abspath(os.path.join(spec_dir, "..", ".."))

datas_pyside, binaries_pyside, hiddenimports_pyside = collect_all("PySide6")

icon_file = os.path.join(REPO_ROOT, "assets", "icons", "Mason.ico")
datas = list(datas_pyside)
if os.path.isfile(icon_file):
    datas.append((icon_file, os.path.join("assets", "icons")))

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
    icon=icon_file if os.path.isfile(icon_file) else None,
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
