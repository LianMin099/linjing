@echo off
setlocal
set PYTHONUTF8=1
chcp 65001 >nul
cd /d "%~dp0"
if not exist "D:\python\python.exe" (
  echo 找不到 Python，请将此提示告诉 Codex。
  pause
  exit /b 1
)
"D:\python\python.exe" -B "%~dp0probe_amap.py"
echo.
pause
