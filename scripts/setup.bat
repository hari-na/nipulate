@echo off
rem One-time setup: Python environment and packages, and a desktop shortcut.
cd /d "%~dp0.."

if not exist .venv (
  python -m venv .venv || (echo Python 3.10 or newer is required: https://www.python.org/downloads/ & pause & exit /b 1)
)
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -e . || (pause & exit /b 1)

echo.
choice /M "Create a desktop shortcut"
if %errorlevel%==1 powershell -NoProfile -ExecutionPolicy Bypass -File scripts\create-shortcut.ps1

echo.
echo Setup done. Start nipulate from the desktop shortcut or scripts\run.bat
pause
