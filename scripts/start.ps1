# Startet Lessons Vault auf 127.0.0.1:8765 (Windows). Zugriff von außen nur über "tailscale serve".
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    .\.venv\Scripts\pip install -q -r requirements.txt
}
$port = if ($env:LV_PORT) { $env:LV_PORT } else { "8765" }
.\.venv\Scripts\uvicorn lessons_vault.main:app_factory --factory --host 127.0.0.1 --port $port
