@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
python -B run_pilot.py --open-browser
if not errorlevel 1 exit /b 0
pause
exit /b 1
