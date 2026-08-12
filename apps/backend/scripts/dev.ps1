$ErrorActionPreference = "Stop"

$BackendRoot = Split-Path -Parent $PSScriptRoot
$VirtualEnvironment = Join-Path $BackendRoot ".venv"
$Python = Join-Path $VirtualEnvironment "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    python -m venv $VirtualEnvironment
}

& $Python -m pip install -e "${BackendRoot}[dev]"
$env:FLASK_DEBUG = "1"
Set-Location $BackendRoot
& $Python run.py
