@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python was not found on PATH.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment in gui\.venv ...
  python -m venv .venv
  if errorlevel 1 exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo Build finished. Run scripts\run.bat to start the GUI.
endlocal
