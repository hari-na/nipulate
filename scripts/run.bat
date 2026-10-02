@echo off
rem Start the server in this window. -v logs every click and key (never typed text); remove it for a quieter log.
cd /d "%~dp0.."
.venv\Scripts\python -m nipulate -v %*
pause
