# Startet Lessons Vault auf 127.0.0.1:8765 (Windows). Zugriff von außen nur über "tailscale serve".
# Mit -Log landet die Ausgabe in data\server.log (für den Autostart).
param([switch]$Log)
# Native Programme (pip, uvicorn) schreiben auf stderr; Windows PowerShell 5.1 würde das bei "Stop"
# als Abbruch werten. Deshalb "Continue" und Exit-Codes selbst prüfen.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
$neu = -not (Test-Path ".venv")
if ($neu) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Error "Python nicht gefunden. Python 3.11+ von python.org installieren."; exit 1 }
}
# Bei jedem Start Abhängigkeiten abgleichen (schnell, wenn nichts fehlt), damit Updates nach "git pull" laufen.
.\.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    if ($neu) { Write-Error "Installation der Abhängigkeiten fehlgeschlagen (Internet?)."; exit 1 }
    Write-Warning "Abgleich der Abhängigkeiten fehlgeschlagen (kein Internet?). Starte mit vorhandener Installation."
}
$port = if ($env:LV_PORT) { $env:LV_PORT } else { "8765" }
$uvArgs = @("-m", "uvicorn", "lessons_vault.main:app_factory", "--factory", "--host", "127.0.0.1", "--port", $port)
if ($Log) {
    New-Item -ItemType Directory -Force -Path "data" | Out-Null
    & .\.venv\Scripts\python @uvArgs *>> "data\server.log"
} else {
    & .\.venv\Scripts\python @uvArgs
}
