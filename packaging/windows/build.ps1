# Build frozen app (PyInstaller) then Windows installer (Inno Setup).
# Run from repo root:  powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
# Prerequisites: Python venv with PyInstaller + requirements.txt; Inno Setup 6 (ISCC on PATH).

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

Write-Host "Repo: $RepoRoot"

if (-not (Test-Path (Join-Path $RepoRoot "assets\icons\Mason.ico"))) {
    Write-Error "Missing assets\icons\Mason.ico"
}

Write-Host "Running PyInstaller..."
pyinstaller --noconfirm (Join-Path $RepoRoot "packaging\windows\Mason.spec")

$dist = Join-Path $RepoRoot "dist\Mason"
if (-not (Test-Path (Join-Path $dist "Mason.exe"))) {
    Write-Error "PyInstaller did not produce dist\Mason\Mason.exe"
}

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    Write-Warning "ISCC.exe not on PATH — skip Inno. Install Inno Setup and add to PATH, then run:"
    Write-Warning "  ISCC packaging\windows\Mason.iss"
    exit 0
}

Write-Host "Running Inno Setup..."
& ISCC.exe (Join-Path $RepoRoot "packaging\windows\Mason.iss")
Write-Host "Done. Installer: output\installer\"
