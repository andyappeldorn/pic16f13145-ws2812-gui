#Requires -Version 5.0
$ErrorActionPreference = "Stop"
$GuiRoot = Split-Path -Parent $PSScriptRoot
Set-Location $GuiRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python was not found on PATH."
    exit 1
}

$venvPython = Join-Path $GuiRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment in gui\.venv ..."
    python -m venv (Join-Path $GuiRoot ".venv")
}

$activate = Join-Path $GuiRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Error "Failed to create .venv (Activate.ps1 missing)."
    exit 1
}

. $activate
python -m pip install --upgrade pip
pip install -r (Join-Path $GuiRoot "requirements.txt")

Write-Host ""
Write-Host "Build finished. Run scripts\run.ps1 to start the GUI."
