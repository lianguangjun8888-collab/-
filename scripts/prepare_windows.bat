@echo off
setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo Please install Python 3.12 x64 with the Python Launcher first.
        exit /b 1
    )
)
if "%~1"=="diagnostics" (
    ".venv\Scripts\python.exe" -c "import pywinauto" >nul 2>nul
    if not errorlevel 1 exit /b 0
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check pywinauto==0.6.9
    if errorlevel 1 exit /b 1
    exit /b 0
)
".venv\Scripts\python.exe" -c "from importlib.metadata import version; assert version('PySide6')=='6.8.3'; assert version('httpx')=='0.28.1'; import pywinauto; from PySide6 import QtWidgets" >nul 2>nul
if not errorlevel 1 exit /b 0
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 exit /b 1
exit /b 0
