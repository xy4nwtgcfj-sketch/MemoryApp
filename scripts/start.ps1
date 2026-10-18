# Startet Lessons Vault auf 127.0.0.1:8765 (Windows). Zugriff von außen nur über "tailscale serve".
# Mit -Log landet die Ausgabe in data\server.log (für den Autostart).
# Stürzt der Server ab, startet das Skript ihn nach 10 s neu. Läuft schon eine Instanz, endet es.
param([switch]$Log)
# Native Programme (pip, uvicorn) schreiben auf stderr; Windows PowerShell 5.1 würde das bei "Stop"
# als Abbruch werten. Deshalb "Continue" und Exit-Codes selbst prüfen.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
New-Item -ItemType Directory -Force -Path "data" | Out-Null
$logDatei = "data\server.log"

function Schreibe([string]$text) {
    $zeile = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $text"
    if ($Log) { $zeile | Out-File -FilePath $logDatei -Append -Encoding utf8 } else { Write-Host $zeile }
}

# Python finden: zuerst der Launcher "py" (immer korrekt installiert), dann "python"
$neu = -not (Test-Path ".venv")
if ($neu) {
    $py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
    if ($py -eq "py") { & py -3 -m venv .venv } else { & python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { Schreibe "Python 3.11+ nicht gefunden. Von python.org installieren (Haken bei 'Add python.exe to PATH')."; exit 1 }
}
# Bei jedem Start Abhängigkeiten abgleichen (schnell, wenn nichts fehlt), damit Updates nach "git pull" laufen.
.\.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt 2>&1 | ForEach-Object { "$_" } | Out-Null
if ($LASTEXITCODE -ne 0) {
    if ($neu) { Schreibe "Installation der Abhängigkeiten fehlgeschlagen (Internet?)."; exit 1 }
    Schreibe "Abgleich der Abhängigkeiten fehlgeschlagen (kein Internet?). Starte mit vorhandener Installation."
}
# Version von Python und SQLite prüfen (Trigram-Suche braucht SQLite 3.45 oder neuer)
& .\.venv\Scripts\python -c "import sys,sqlite3; v=tuple(map(int,sqlite3.sqlite_version.split('.'))); sys.exit(0 if sys.version_info>=(3,11) and v>=(3,45) else 1)"
if ($LASTEXITCODE -ne 0) { Schreibe "Python 3.11+ mit SQLite 3.45+ nötig. Aktuelles Python von python.org installieren und .venv löschen."; exit 1 }

$port = if ($env:LV_PORT) { $env:LV_PORT } else { "8765" }
# --no-access-log: Suchbegriffe stehen sonst im Klartext im Protokoll
$uvArgs = @("-m", "uvicorn", "lessons_vault.main:app_factory", "--factory", "--host", "127.0.0.1", "--port", $port, "--no-access-log")

while ($true) {
    if ($Log -and (Test-Path $logDatei) -and (Get-Item $logDatei).Length -gt 5MB) {
        Move-Item $logDatei "$logDatei.1" -Force
    }
    Schreibe "Starte Lessons Vault auf Port $port"
    if ($Log) {
        & .\.venv\Scripts\python @uvArgs 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath $logDatei -Append -Encoding utf8
    } else {
        & .\.venv\Scripts\python @uvArgs
    }
    $code = $LASTEXITCODE
    if ($code -eq 3) { Schreibe "Start abgebrochen (läuft bereits oder Startfehler, siehe oben). Kein Neustart."; exit 3 }
    Schreibe "Server beendet (Code $code). Neustart in 10 Sekunden."
    Start-Sleep -Seconds 10
}
