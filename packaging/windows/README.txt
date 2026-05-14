Windows packaging (Mason)
=========================

Prerequisites
  - Python 3.11+ with: pip install -r requirements.txt
  - PyInstaller: pip install -r requirements-windows-build.txt
  - Inno Setup 6 from https://jrsoftware.org/isinfo.php (add ISCC.exe to PATH for the installer step)

Frozen app (PyInstaller), from repo root:
  pyinstaller packaging/windows/Mason.spec

Output: dist\Mason\Mason.exe and dist\Mason\_internal\

Installer (Inno), after PyInstaller, from repo root:
  ISCC packaging\windows\Mason.iss

Output: output\installer\Mason_Setup_0.1.0.exe  (change MyAppVersion in Mason.iss when you release)

All-in-one PowerShell from repo root:
  powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1

Install location: per-user under %LocalAppData%\Programs\Mason (no admin required).
