@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
python -B demo_web.py --open-browser
if errorlevel 1 pause
