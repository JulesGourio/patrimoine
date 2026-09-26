# Tâches planifiées Windows du projet Patrimoine.
#   .\scripts\taches.ps1 sync      -> synchronisation complète (tâche quotidienne)
#   .\scripts\taches.ps1 rapport   -> rapport hebdomadaire rédigé par Claude Code (tâche du dimanche)
#   .\scripts\taches.ps1 installer -> crée / met à jour les deux tâches planifiées
param([Parameter(Mandatory = $true)][ValidateSet("sync", "rapport", "installer")][string]$Action)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"
$Logs = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force $Logs | Out-Null
$Uv = (Get-Command uv).Source

function Find-Claude {
    # Claude Code ships inside the VS Code extension; take the newest installed version.
    $ext = Get-ChildItem "$env:USERPROFILE\.vscode\extensions" -Directory -Filter "anthropic.claude-code-*" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $ext) { throw "Claude Code introuvable" }
    return Join-Path $ext.FullName "resources\native-binary\claude.exe"
}

switch ($Action) {
    "sync" {
        & $Uv run patrimoine sync *>> (Join-Path $Logs "sync-$(Get-Date -Format yyyy-MM-dd).txt")
    }
    "rapport" {
        & $Uv run patrimoine sync *>> (Join-Path $Logs "sync-$(Get-Date -Format yyyy-MM-dd).txt")
        $claude = Find-Claude
        $prompt = Get-Content (Join-Path $PSScriptRoot "rapport_hebdo.md") -Raw -Encoding utf8
        & $claude -p $prompt --mcp-config (Join-Path $Root ".mcp.json") `
            --allowedTools "mcp__patrimoine__*" "WebSearch" "WebFetch" `
            *>> (Join-Path $Logs "rapport-$(Get-Date -Format yyyy-MM-dd).txt")
    }
    "installer" {
        $script = Join-Path $PSScriptRoot "taches.ps1"
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
            -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
        $daily = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" sync" -WorkingDirectory $Root
        Register-ScheduledTask -TaskName "Patrimoine - synchronisation" -Action $daily -Settings $settings `
            -Trigger (New-ScheduledTaskTrigger -Daily -At 7:30) -Force | Out-Null
        $weekly = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" rapport" -WorkingDirectory $Root
        Register-ScheduledTask -TaskName "Patrimoine - rapport hebdo" -Action $weekly -Settings $settings `
            -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 18:00) -Force | Out-Null
        Get-ScheduledTask -TaskName "Patrimoine*" | Select-Object TaskName, State
    }
}
