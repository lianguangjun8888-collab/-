@echo off
setlocal
cd /d "%~dp0.."
call scripts\prepare_windows.bat
if errorlevel 1 (
    pause
    exit /b 1
)
set PYTHONUTF8=1
set "PYTHONPATH=%CD%\src"
if not exist reports mkdir reports
".venv\Scripts\python.exe" -m qianniu_assistant --diagnose --output reports\qianniu-diagnostic.json
if errorlevel 1 (
    echo Diagnostic failed. Please keep this console output.
) else (
    echo Saved: %CD%\reports\qianniu-diagnostic.json
)
pause
