@echo off
setlocal
set PYTHONUTF8=1
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 找不到 Python。请安装 Python 3.7+ 并加入 PATH，或查看 README。
  pause
  exit /b 1
)
python -B "%~dp0probe_amap.py"
echo.
pause
