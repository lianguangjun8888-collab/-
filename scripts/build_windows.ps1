param([switch]$TestOnly)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (!(Test-Path '.venv/Scripts/python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 is required.' }
}
$python = (Resolve-Path '.venv/Scripts/python.exe').Path
& $python -m pip install --disable-pip-version-check -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
if ($TestOnly) { exit 0 }
& $python -m PyInstaller --noconfirm --clean --windowed --onedir --name QianniuLocalAssistant --paths src --collect-submodules pywinauto --collect-submodules comtypes --hidden-import win32timezone launcher.py
if ($LASTEXITCODE -ne 0) { throw 'Windows executable build failed.' }
& 'dist/QianniuLocalAssistant/QianniuLocalAssistant.exe' --diagnose --output 'dist/diagnostic-smoke.json'
if ($LASTEXITCODE -ne 0) { throw 'Frozen diagnostic launch failed.' }
if (!(Test-Path 'dist/diagnostic-smoke.json')) { throw 'Frozen app produced no diagnostic report.' }
$report = Get-Content 'dist/diagnostic-smoke.json' -Raw -Encoding UTF8 | ConvertFrom-Json
if ($report.live_ready -ne $false) { throw 'Fresh diagnostic must not claim live readiness.' }
Compress-Archive -Path 'dist/QianniuLocalAssistant' -DestinationPath 'dist/QianniuLocalAssistant-windows.zip' -Force
Write-Output 'Built dist/QianniuLocalAssistant-windows.zip. Live Qianniu compatibility still requires the Windows acceptance checklist.'
