@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\activate.bat" (
  echo ERROR: Virtual environment missing. Run scripts\build.bat first.
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python led_control_gui.py
set EXITCODE=%ERRORLEVEL%
endlocal & exit /b %EXITCODE%
