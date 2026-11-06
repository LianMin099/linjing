@echo off
setlocal
set PYTHONUTF8=1
chcp 65001 >nul
cd /d "%~dp0"
set GIT_TERMINAL_PROMPT=1
set GCM_INTERACTIVE=Always
echo 即将上传邻境现有代码和提交历史，仓库保持私有。
echo 如浏览器要求登录，请使用 LianMin099 账号完成授权。
git -c http.sslBackend=openssl push -u origin main
if errorlevel 1 (
  echo.
  echo 上传未成功。请将本窗口的错误提示发给 Codex，不要发送密码或令牌。
) else (
  echo.
  echo 上传成功。请返回聊天告诉 Codex，以便核对远程提交。
)
pause
