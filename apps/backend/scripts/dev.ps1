$ErrorActionPreference = "Stop"

$BackendRoot = Split-Path -Parent $PSScriptRoot
$VirtualEnvironment = Join-Path $BackendRoot ".venv"
$Python = Join-Path $VirtualEnvironment "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    python -m venv $VirtualEnvironment
}

& $Python -m pip install -e "${BackendRoot}[dev]"
$env:FLASK_APP = "telemetry:create_app"
$env:FLASK_DEBUG = "1"
Set-Location $BackendRoot
& $Python -m flask run --host 0.0.0.0 --port 5000
