@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
call scripts\prepare_windows.bat diagnostics
if errorlevel 1 (
    pause
    exit /b 1
)
set PYTHONUTF8=1
set "PYTHONPATH=%CD%\src"
if not exist reports mkdir reports
echo.
echo 增强检测 v2：请先打开千牛“客服接待”，进入一个买家会话并保持窗口可见。
echo 请关闭“关于千牛”等遮挡聊天的窗口。本检测不会发消息，也不默认读取聊天正文。
echo 准备好后按任意键开始检测，最长约 25 秒；卡住时会保留已采集的部分结果。
pause >nul
".venv\Scripts\python.exe" -m qianniu_assistant --diagnose --output reports\qianniu-diagnostic.json
if errorlevel 1 (
    echo Diagnostic failed. Please keep this console output.
) else (
    echo Saved: %CD%\reports\qianniu-diagnostic.json
)
pause
