@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
python -B probe_amap.py --find-banks
pause
