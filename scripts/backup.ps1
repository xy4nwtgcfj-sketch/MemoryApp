# Sicherung von Datenbank und Fotos (Windows). Ziel über LV_BACKUP_ZIEL in .env, sonst .\backups.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
& .\.venv\Scripts\python scripts\backup.py 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath "data\backup.log" -Append -Encoding utf8
exit $LASTEXITCODE
