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
".venv\Scripts\python.exe" -m qianniu_assistant
if errorlevel 1 pause
