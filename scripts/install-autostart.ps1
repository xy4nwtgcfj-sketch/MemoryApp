# Richtet zwei geplante Aufgaben ein:
#   "Lessons Vault"        startet die App bei der Anmeldung unsichtbar (60 s verzögert, damit Ollama läuft)
#   "Lessons Vault Backup" sichert täglich Datenbank und Fotos (holt verpasste Läufe nach)
# Aufruf: powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
# Entfernen: Unregister-ScheduledTask -TaskName "Lessons Vault" -Confirm:$false
#            Unregister-ScheduledTask -TaskName "Lessons Vault Backup" -Confirm:$false
$ErrorActionPreference = "Stop"
$start = Join-Path $PSScriptRoot "start.ps1"
$backup = Join-Path $PSScriptRoot "backup.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$start`" -Log"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT60S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "Lessons Vault" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Lessons Vault Server auf 127.0.0.1:8765 (startet sich nach Absturz selbst neu)" -Force | Out-Null

$bAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$backup`""
$bTrigger = New-ScheduledTaskTrigger -Daily -At "12:17"
$bSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "Lessons Vault Backup" -Action $bAction -Trigger $bTrigger -Settings $bSettings `
    -Description "Tägliche Sicherung von Lessons Vault (Datenbank und Fotos)" -Force | Out-Null

Write-Host "Autostart und tägliches Backup eingerichtet. Jetzt starten: Start-ScheduledTask -TaskName 'Lessons Vault'"
