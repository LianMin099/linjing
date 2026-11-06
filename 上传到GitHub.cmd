@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
set "LINJING_REPO=%CD:\=/%"
set "GIT_TERMINAL_PROMPT=1"
set "GCM_INTERACTIVE=Always"
echo Uploading Linjing to GitHub.
echo If GitHub requests sign-in, use account LianMin099.
git -c "safe.directory=%LINJING_REPO%" -c http.sslBackend=openssl push -u origin main
if errorlevel 1 (
  echo Upload failed. Share the error text with Codex.
  pause
  exit /b 1
)
echo Upload succeeded. Tell Codex so the remote history can be checked.
pause
