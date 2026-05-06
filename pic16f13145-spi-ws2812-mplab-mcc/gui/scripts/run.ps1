#Requires -Version 5.0
$ErrorActionPreference = "Stop"
$GuiRoot = Split-Path -Parent $PSScriptRoot
Set-Location $GuiRoot

$activate = Join-Path $GuiRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Error "Virtual environment missing. Run scripts\build.ps1 first."
    exit 1
}

. $activate
python (Join-Path $GuiRoot "led_control_gui.py")
