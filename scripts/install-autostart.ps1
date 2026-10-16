# Richtet Lessons Vault als geplante Aufgabe ein, die bei der Anmeldung unsichtbar startet.
# Aufruf: powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
# Entfernen: Unregister-ScheduledTask -TaskName "Lessons Vault" -Confirm:$false
$ErrorActionPreference = "Stop"
$start = Join-Path $PSScriptRoot "start.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$start`" -Log"
# 60 Sekunden Verzögerung, damit Ollama und Tailscale vorher laufen
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT60S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "Lessons Vault" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Lessons Vault Server auf 127.0.0.1:8765" -Force | Out-Null
Write-Host "Autostart eingerichtet. Jetzt starten: Start-ScheduledTask -TaskName 'Lessons Vault'"
