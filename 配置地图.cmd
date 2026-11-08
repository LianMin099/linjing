@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
python -B configure_map.py
set "LINJING_CONFIG_EXIT=%ERRORLEVEL%"
pause
exit /b %LINJING_CONFIG_EXIT%
